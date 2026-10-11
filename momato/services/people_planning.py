"""People planning: planned days, time spent and the two compared, per person and bucket
(PPL-1 – PPL-7, R4.3, R4.5, R4.11).

Everything is aggregated in SQL (a few statements whatever the number of people); bucket
boundaries come from the domain. Hours privacy (D-005): Spent and Compare show a person's numbers
only to that person and to holders of `hours.view` on their node; the others are counted, not shown.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from sqlalchemy import Select, and_, case, func, literal, select
from sqlalchemy.orm import Session

from momato.db.ids import in_ids
from momato.db.models import (
    Availability,
    OrgNode,
    PlannedDays,
    Project,
    ProjectMember,
    TimeEntry,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.domain.access import Permission
from momato.domain.calendar import (
    Bucket,
    BucketSet,
    Period,
    Quarter,
    Unit,
    planned_buckets,
    spent_buckets,
)
from momato.domain.capacity import (
    WorkPattern,
    available_minutes,
    compare_class,
    load_class,
    quarter_availability_days,
    year_availability_days,
)
from momato.domain.errors import NotFoundError, PermissionDeniedError, RuleViolationError
from momato.domain.fields import CategoryKind, Profile
from momato.domain.planning import planned_in_period
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.schemas.people_planning import (
    BucketOut,
    CellOut,
    LineOut,
    PeoplePlanning,
    PersonLines,
    PersonRowOut,
    TotalOut,
)
from momato.schemas.projects import PersonRef
from momato.services import common

MINUTES_PER_HOUR = 60

# A time entry's kind, as classified in SQL.
KIND_MEMBER = "member"  # a project the person is a member of
KIND_OTHER = "other"  # a project they booked on without being a member
KIND_WORK = "other_work"
KIND_OFF = "time_off"


def _pattern(user: User) -> WorkPattern:
    return WorkPattern(
        (
            user.work_minutes_mon,
            user.work_minutes_tue,
            user.work_minutes_wed,
            user.work_minutes_thu,
            user.work_minutes_fri,
        )
    )


@dataclass(frozen=True)
class _View:
    """What a request asks for, resolved: mode, period, buckets and the unit of the numbers."""

    mode: str
    period: Period
    buckets: BucketSet
    hours: bool  # values are hours (Past week) rather than days

    @property
    def unit(self) -> str:
        return "hours" if self.hours else "days"


class PeoplePlanningService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        self.policy = AccessPolicy(principal)

    # ------------------------------------------------------------------ the request

    def _view(self, mode: str, period: str) -> _View:
        if mode not in {"planned", "spent", "compare"}:
            raise RuleViolationError(f"unknown mode {mode!r}")
        try:
            chosen = Period(period)
        except ValueError as error:
            raise RuleViolationError(f"unknown period {period!r}") from error
        if mode == "planned":
            buckets = planned_buckets(self.today)
            return _View(mode, chosen, buckets, hours=False)
        buckets = spent_buckets(chosen, self.today)
        return _View(mode, chosen, buckets, hours=buckets.unit is Unit.HOURS)

    def _bucket_out(self, bucket: Bucket) -> BucketOut:
        return BucketOut(
            key=bucket.key,
            sub=bucket.sub,
            start=bucket.start,
            end=bucket.end,
            current=bucket.start <= self.today <= bucket.end and bucket.start != bucket.end,
        )

    # ------------------------------------------------------------------ people

    def _people(self, node_id: int | None, q: str) -> list[User]:
        """Active people in the branch (all of them for the root or no node), by name."""
        query: Select[User] = select(User).where(
            User.kind == UserKind.PERSON, User.status != UserStatus.DEACTIVATED
        )
        tree = self.principal.tree
        if node_id is not None:
            if node_id not in tree:
                raise NotFoundError(f"no organisation node {node_id}")
            nodes = tree.subtree(node_id)
            if len(nodes) < len(tree):  # the whole tree includes people without a node
                query = query.where(in_ids(User.org_node_id, nodes))
        text = q.strip()
        if text:
            query = query.where(func.lower(User.name).contains(text.lower(), autoescape=True))
        return list(self.session.scalars(query.order_by(User.name, User.id)))

    def _visible_hours(self, users: list[User]) -> set[int]:
        """The people among `users` whose booked time the caller may see (PPL-6)."""
        if not users:
            return set()
        ids = [u.id for u in users]
        rows = self.session.scalars(
            select(User.id).where(in_ids(User.id, ids), self.policy.people_hours_filter())
        )
        return set(rows)

    # ------------------------------------------------------------------ the numbers

    def _availability(
        self, user_ids: list[int], years: set[int]
    ) -> dict[tuple[int, int], Fraction]:
        if not user_ids:
            return {}
        rows = self.session.execute(
            select(Availability.user_id, Availability.year, Availability.days).where(
                in_ids(Availability.user_id, user_ids), Availability.year.in_(years)
            )
        )
        return {(u, y): common.to_fraction(d) for u, y, d in rows}

    def _planned(self, user_ids: list[int]) -> dict[tuple[int, int], dict[Quarter, Fraction]]:
        """Planned days per (person, project) and quarter, summed over nothing: one dict each."""
        result: dict[tuple[int, int], dict[Quarter, Fraction]] = defaultdict(dict)
        if not user_ids:
            return result
        rows = self.session.execute(
            select(
                PlannedDays.user_id,
                PlannedDays.project_id,
                PlannedDays.quarter_start,
                PlannedDays.days,
            ).where(in_ids(PlannedDays.user_id, user_ids))
        )
        for user_id, project_id, quarter_start, days in rows:
            result[(user_id, project_id)][Quarter.containing(quarter_start)] = common.to_fraction(
                days
            )
        return result

    def _planned_by_person(self, user_ids: list[int]) -> dict[int, dict[Quarter, Fraction]]:
        """Planned days per person and quarter over all projects (aggregated in SQL)."""
        result: dict[int, dict[Quarter, Fraction]] = defaultdict(dict)
        if not user_ids:
            return result
        rows = self.session.execute(
            select(PlannedDays.user_id, PlannedDays.quarter_start, func.sum(PlannedDays.days))
            .where(in_ids(PlannedDays.user_id, user_ids))
            .group_by(PlannedDays.user_id, PlannedDays.quarter_start)
        )
        for user_id, quarter_start, days in rows:
            result[user_id][Quarter.containing(quarter_start)] = common.to_fraction(days)
        return result

    def _spent(
        self, user_ids: list[int], buckets: tuple[Bucket, ...]
    ) -> dict[tuple[int, int, str], int]:
        """Minutes per (person, bucket index, kind), aggregated in SQL."""
        result: dict[tuple[int, int, str], int] = {}
        if not user_ids or not buckets:
            return result
        off_keys = [c.key for c in self.profile.categories_of(CategoryKind.TIME_OFF)]
        index = case(
            *[
                (TimeEntry.work_date.between(b.start, b.end), literal(i))
                for i, b in enumerate(buckets)
            ],
            else_=literal(-1),
        )
        kind = case(
            (
                and_(TimeEntry.project_id.is_(None), TimeEntry.category_key.in_(off_keys)),
                literal(KIND_OFF),
            ),
            (TimeEntry.project_id.is_(None), literal(KIND_WORK)),
            (ProjectMember.user_id.is_not(None), literal(KIND_MEMBER)),
            else_=literal(KIND_OTHER),
        )
        query = (
            select(TimeEntry.user_id, index, kind, func.sum(TimeEntry.minutes))
            .select_from(TimeEntry)
            .outerjoin(
                ProjectMember,
                and_(
                    ProjectMember.project_id == TimeEntry.project_id,
                    ProjectMember.user_id == TimeEntry.user_id,
                ),
            )
            .where(
                in_ids(TimeEntry.user_id, user_ids),
                TimeEntry.work_date.between(buckets[0].start, buckets[-1].end),
            )
            .group_by(TimeEntry.user_id, index, kind)
        )
        for user_id, bucket_index, kind_value, minutes in self.session.execute(query):
            if bucket_index >= 0:
                result[(user_id, int(bucket_index), str(kind_value))] = int(minutes)
        return result

    # ------------------------------------------------------------------ overview

    def overview(self, node_id: int | None, mode: str, period: str, q: str = "") -> PeoplePlanning:
        view = self._view(mode, period)
        people = self._people(node_id, q)
        refs = {
            u.id: PersonRef(id=u.id, name=u.name, hue=u.hue, job_title=u.job_title) for u in people
        }
        node_names = dict(self.session.execute(select(OrgNode.id, OrgNode.name)).all())
        if view.mode == "planned":
            shown = people
            hidden = 0
        else:
            visible = self._visible_hours(people)
            shown = [u for u in people if u.id in visible]
            hidden = len(people) - len(shown)

        ids = [u.id for u in shown]
        rows: list[PersonRowOut] = []
        if view.mode == "planned":
            rows = self._planned_rows(view, shown, ids, refs, node_names)
        else:
            rows = self._spent_rows(view, shown, ids, refs, node_names)
        return PeoplePlanning(
            mode=view.mode,  # pyright: ignore[reportArgumentType]
            period=view.period.value,  # pyright: ignore[reportArgumentType]
            unit=view.unit,  # pyright: ignore[reportArgumentType]
            range_label=view.buckets.range_label,
            buckets=[self._bucket_out(b) for b in view.buckets.buckets],
            rows=rows,
            hidden_count=hidden,
            total_count=len(people),
        )

    def _planned_rows(
        self,
        view: _View,
        users: list[User],
        ids: list[int],
        refs: dict[int, PersonRef],
        node_names: dict[int, str],
    ) -> list[PersonRowOut]:
        buckets = view.buckets.buckets
        quarters = [Quarter.containing(b.start) for b in buckets]
        years = {q.year for q in quarters}
        overrides = self._availability(ids, years)
        planned = self._planned_by_person(ids)
        default_days = self.profile.numbers.available_days_per_year
        rows: list[PersonRowOut] = []
        for user in users:
            pattern = _pattern(user)
            cells: list[CellOut] = []
            year_sums: dict[int, Fraction] = defaultdict(Fraction)
            for quarter in quarters:
                days = planned.get(user.id, {}).get(quarter, Fraction(0))
                year_sums[quarter.year] += days
                year_days = year_availability_days(
                    overrides.get((user.id, quarter.year)), pattern, default_days
                )
                capacity = quarter_availability_days(year_days, quarter)
                cells.append(
                    CellOut(
                        value=float(days),
                        reference=float(capacity),
                        cls=load_class(days, capacity).value,
                    )
                )
            first_year = quarters[0].year
            year_days = year_availability_days(
                overrides.get((user.id, first_year)), pattern, default_days
            )
            this_year = year_sums[first_year]
            rows.append(
                PersonRowOut(
                    person=refs[user.id],
                    org_node_id=user.org_node_id,
                    org_node_name=node_names.get(user.org_node_id) if user.org_node_id else None,
                    cells=cells,
                    total=TotalOut(
                        value=float(this_year),
                        reference=float(year_days),
                        cls=load_class(this_year, year_days).value,
                        free=float(year_days - this_year),
                        percent=None,
                    ),
                )
            )
        return rows

    def _spent_rows(
        self,
        view: _View,
        users: list[User],
        ids: list[int],
        refs: dict[int, PersonRef],
        node_names: dict[int, str],
    ) -> list[PersonRowOut]:
        buckets = view.buckets.buckets
        spent = self._spent(ids, buckets)
        compare = view.mode == "compare"
        # Planned days exist for members only (D-041): they are the member projects' plan.
        member_planned = self._planned_by_person(ids) if compare else {}
        hours_per_day = self.profile.numbers.hours_per_day
        rows: list[PersonRowOut] = []
        for user in users:
            pattern = _pattern(user)
            cells: list[CellOut] = []
            total_spent = Fraction(0)
            total_reference = Fraction(0)
            for index, bucket in enumerate(buckets):
                work = (
                    spent.get((user.id, index, KIND_MEMBER), 0)
                    + (0 if compare else spent.get((user.id, index, KIND_OTHER), 0))
                    + (0 if compare else spent.get((user.id, index, KIND_WORK), 0))
                )
                value = self._to_unit(work, view, hours_per_day)
                total_spent += value
                if compare:
                    days = planned_in_period(
                        member_planned.get(user.id, {}), pattern, bucket.start, bucket.end
                    )
                    reference = days * hours_per_day if view.hours else days
                    total_reference += reference
                    cells.append(
                        CellOut(
                            value=float(value),
                            reference=float(reference),
                            cls=compare_class(value, reference).value,
                        )
                    )
                else:
                    off = spent.get((user.id, index, KIND_OFF), 0)
                    available = available_minutes(pattern, bucket.start, bucket.end, off)
                    capacity = self._to_unit(available, view, hours_per_day)
                    total_reference += capacity
                    cells.append(
                        CellOut(
                            value=float(value),
                            reference=float(capacity),
                            cls=load_class(value, capacity).value,
                        )
                    )
            if compare:
                percent = (
                    round_half_up(total_spent * 100 / total_reference) if total_reference else 0
                )
                total = TotalOut(
                    value=float(total_spent),
                    reference=float(total_reference),
                    cls=compare_class(total_spent, total_reference).value,
                    free=None,
                    percent=percent,
                )
            else:
                total = TotalOut(
                    value=float(total_spent),
                    reference=float(total_reference),
                    cls=load_class(total_spent, total_reference).value,
                    free=None,
                    percent=None,
                )
            rows.append(
                PersonRowOut(
                    person=refs[user.id],
                    org_node_id=user.org_node_id,
                    org_node_name=node_names.get(user.org_node_id) if user.org_node_id else None,
                    cells=cells,
                    total=total,
                )
            )
        return rows

    @staticmethod
    def _to_unit(minutes: int, view: _View, hours_per_day: int) -> Fraction:
        if view.hours:
            return Fraction(minutes, MINUTES_PER_HOUR)
        return Fraction(minutes, hours_per_day * MINUTES_PER_HOUR)

    # ------------------------------------------------------------------ one person's lines

    def person(self, person_id: int, mode: str, period: str) -> PersonLines:
        view = self._view(mode, period)
        user = self.session.get(User, person_id)
        if user is None or user.kind is not UserKind.PERSON:
            raise NotFoundError(f"no person {person_id}")
        if view.mode != "planned" and person_id not in self._visible_hours([user]):
            raise PermissionDeniedError("you may not see this person's hours")
        refs = {
            user.id: PersonRef(id=user.id, name=user.name, hue=user.hue, job_title=user.job_title)
        }
        lines = (
            self._planned_lines(view, user)
            if view.mode == "planned"
            else self._spent_lines(view, user)
        )
        return PersonLines(
            person=refs[user.id],
            mode=view.mode,  # pyright: ignore[reportArgumentType]
            period=view.period.value,  # pyright: ignore[reportArgumentType]
            unit=view.unit,  # pyright: ignore[reportArgumentType]
            buckets=[self._bucket_out(b) for b in view.buckets.buckets],
            lines=lines,
        )

    def _projects(self, project_ids: set[int]) -> tuple[dict[int, Project], set[int]]:
        """The projects by id and which of them the caller may see."""
        if not project_ids:
            return {}, set()
        projects = {
            p.id: p
            for p in self.session.scalars(select(Project).where(in_ids(Project.id, project_ids)))
        }
        visible = set(
            self.session.scalars(
                select(Project.id).where(
                    in_ids(Project.id, project_ids),
                    self.policy.project_filter(Permission.PROJECT_VIEW),
                )
            )
        )
        return projects, visible

    def _plain_total(self, cells: list[CellOut]) -> TotalOut:
        value = sum(c.value for c in cells)
        reference = sum(c.reference or 0 for c in cells)
        return TotalOut(value=value, reference=reference, cls="empty", free=None, percent=None)

    def _planned_lines(self, view: _View, user: User) -> list[LineOut]:
        buckets = view.buckets.buckets
        quarters = [Quarter.containing(b.start) for b in buckets]
        per_project = {
            project_id: by_quarter
            for (uid, project_id), by_quarter in self._planned([user.id]).items()
            if uid == user.id
        }
        projects, visible = self._projects(set(per_project))
        lines: list[LineOut] = []
        other: list[Fraction] = [Fraction(0)] * len(quarters)
        for project_id, by_quarter in sorted(
            per_project.items(), key=lambda kv: -projects[kv[0]].number
        ):
            values = [by_quarter.get(q, Fraction(0)) for q in quarters]
            if not any(values):
                continue
            if project_id in visible:
                project = projects[project_id]
                cells = _plain_cells(float(v) for v in values)
                lines.append(
                    LineOut(
                        kind="project",
                        number=project.number,
                        name=project.name,
                        status=project.status.value,
                        cells=cells,
                        total=self._plain_total(cells),
                    )
                )
            else:
                other = [a + b for a, b in zip(other, values, strict=True)]
        if any(other):
            cells = _plain_cells(float(v) for v in other)
            lines.append(
                LineOut(
                    kind="other_projects",
                    number=None,
                    name="Other projects",
                    status=None,
                    cells=cells,
                    total=self._plain_total(cells),
                )
            )
        return lines

    def _spent_lines(self, view: _View, user: User) -> list[LineOut]:
        buckets = view.buckets.buckets
        compare = view.mode == "compare"
        hours_per_day = self.profile.numbers.hours_per_day
        pattern = _pattern(user)
        off_keys = [c.key for c in self.profile.categories_of(CategoryKind.TIME_OFF)]
        index = case(
            *[
                (TimeEntry.work_date.between(b.start, b.end), literal(i))
                for i, b in enumerate(buckets)
            ],
            else_=literal(-1),
        )
        rows = self.session.execute(
            select(
                TimeEntry.project_id,
                case((TimeEntry.category_key.in_(off_keys), literal(1)), else_=literal(0)),
                index,
                func.sum(TimeEntry.minutes),
            )
            .where(
                TimeEntry.user_id == user.id,
                TimeEntry.work_date.between(buckets[0].start, buckets[-1].end),
            )
            .group_by(
                TimeEntry.project_id,
                case((TimeEntry.category_key.in_(off_keys), literal(1)), else_=literal(0)),
                index,
            )
        ).all()
        members = set(
            self.session.scalars(
                select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
            )
        )
        per_project: dict[int, list[int]] = defaultdict(lambda: [0] * len(buckets))
        work = [0] * len(buckets)
        off = [0] * len(buckets)
        for project_id, is_off, bucket_index, minutes in rows:
            if bucket_index < 0:
                continue
            if project_id is not None:
                per_project[project_id][int(bucket_index)] += int(minutes)
            elif is_off:
                off[int(bucket_index)] += int(minutes)
            else:
                work[int(bucket_index)] += int(minutes)

        planned = self._planned([user.id])
        member_planned: dict[int, dict[Quarter, Fraction]] = (
            {pid: q for (uid, pid), q in planned.items() if uid == user.id} if compare else {}
        )
        project_ids = set(per_project) | set(member_planned)
        projects, visible = self._projects(project_ids)

        def unit(minutes: int) -> Fraction:
            return self._to_unit(minutes, view, hours_per_day)

        def planned_cells(project_id: int, spent_minutes: list[int]) -> list[CellOut]:
            result: list[CellOut] = []
            by_quarter = member_planned.get(project_id, {})
            for i, bucket in enumerate(buckets):
                days = planned_in_period(by_quarter, pattern, bucket.start, bucket.end)
                reference = days * hours_per_day if view.hours else days
                value = unit(spent_minutes[i])
                cls = compare_class(value, reference).value
                result.append(CellOut(value=float(value), reference=float(reference), cls=cls))
            return result

        def total_of(cells: list[CellOut]) -> TotalOut:
            value = sum(c.value for c in cells)
            reference = sum(c.reference or 0 for c in cells)
            if compare:
                cls = compare_class(
                    Fraction(value).limit_denominator(10**6),
                    Fraction(reference).limit_denominator(10**6),
                ).value
                percent = round(value * 100 / reference) if reference else 0
                return TotalOut(
                    value=value, reference=reference, cls=cls, free=None, percent=percent
                )
            return TotalOut(value=value, reference=None, cls="empty", free=None, percent=None)

        lines: list[LineOut] = []
        hidden_cells: dict[bool, list[int]] = {}
        for project_id in sorted(project_ids, key=lambda i: -projects[i].number):
            spent_minutes = per_project.get(project_id, [0] * len(buckets))
            is_member = project_id in members
            if compare and is_member:
                cells = planned_cells(project_id, spent_minutes)
            elif compare:
                cells = [
                    CellOut(
                        value=float(unit(m)),
                        reference=0.0,
                        cls=compare_class(unit(m), 0).value,
                    )
                    for m in spent_minutes
                ]
            else:
                cells = _plain_cells(float(unit(m)) for m in spent_minutes)
            if not any(c.value or c.reference for c in cells):
                continue
            if project_id not in visible:
                bucket = hidden_cells.setdefault(is_member, [0] * len(buckets))
                for i, m in enumerate(spent_minutes):
                    bucket[i] += m
                continue
            project = projects[project_id]
            lines.append(
                LineOut(
                    kind="project" if (is_member or not compare) else "non_member",
                    number=project.number,
                    name=project.name,
                    status=project.status.value,
                    cells=cells,
                    total=total_of(cells),
                )
            )
        if hidden_cells:
            merged = [sum(col) for col in zip(*hidden_cells.values(), strict=True)]
            cells = _plain_cells(float(unit(m)) for m in merged)
            lines.append(
                LineOut(
                    kind="other_projects",
                    number=None,
                    name="Other projects",
                    status=None,
                    cells=cells,
                    total=TotalOut(
                        value=sum(c.value for c in cells),
                        reference=None,
                        cls="empty",
                        free=None,
                        percent=None,
                    ),
                )
            )
        for kind, name, minutes in (
            ("other_work", "Other work (meetings, training, admin)", work),
            ("time_off", "Time off", off),
        ):
            if any(minutes):
                cells = _plain_cells(float(unit(m)) for m in minutes)
                lines.append(
                    LineOut(
                        kind=kind,  # pyright: ignore[reportArgumentType]
                        number=None,
                        name=name,
                        status=None,
                        cells=cells,
                        total=TotalOut(
                            value=sum(c.value for c in cells),
                            reference=None,
                            cls="empty",
                            free=None,
                            percent=None,
                        ),
                    )
                )
        return lines


def _plain_cells(values: Iterable[float]) -> list[CellOut]:
    """Cells that carry only a number: the lines of a drill-down (no capacity to colour by)."""
    return [CellOut(value=v, reference=None, cls="empty") for v in values]


def round_half_up(value: Fraction) -> int:
    return int((value + Fraction(1, 2)) // 1)
