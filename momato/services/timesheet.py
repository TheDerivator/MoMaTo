"""My timesheet: a week's lines, cells and state; setting a cell; submitting (TS-1 – TS-15).

A person books only their own time (TS-13). A cell is (line, task): a line is a project
(`project:4102`), `other_work` or `time_off`; a task is `general`, `task:12`, or a profile
category of the line's kind. Writes set a cell's minutes to an absolute value (TS-9), so a
repeated request changes nothing. R4.8's rules are enforced here as well as in the browser.
"""

from collections import defaultdict
from datetime import date
from fractions import Fraction

from sqlalchemy import Select, delete, false, func, or_, select
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.ids import in_ids
from momato.db.models import PlannedDays, Project, Task, TimeEntry, User, WeekSubmission
from momato.db.models.people import UserKind
from momato.domain import timesheet as ts
from momato.domain.access import Permission
from momato.domain.calendar import WORKDAYS_PER_WEEK, IsoWeek, Quarter
from momato.domain.capacity import WorkPattern
from momato.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from momato.domain.fields import CategoryKind, Profile
from momato.domain.planning import other_work_planned_minutes, weekly_planned_hours
from momato.domain.tasks import task_status
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.schemas.timesheet import (
    CellSet,
    DayOut,
    LineOut,
    TaskChoice,
    TimesheetOut,
    WeekCard,
    WeekStateOut,
)
from momato.services import common

GENERAL = "general"
OTHER_WORK = "other_work"
TIME_OFF = "time_off"
PROJECT_PREFIX = "project:"
TASK_PREFIX = "task:"
GENERAL_POSITION = 10_000  # after every task of the project


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


def _today_index(week: IsoWeek, today: date) -> int:
    """Monday 0 in the current week (4 on a weekend); 7 for a past week (R4.9)."""
    current = IsoWeek.of(today)
    if week < current:
        return ts.PAST_WEEK
    return min(today.weekday(), WORKDAYS_PER_WEEK - 1)


def week_state_out(view: ts.WeekView) -> WeekStateOut:
    return WeekStateOut(
        state=view.state.value,  # pyright: ignore[reportArgumentType]
        full_days=view.full_days,
        working_days=view.working_days,
        open_days=list(view.open_days),
        total_minutes=view.total_minutes,
        target_minutes=view.target_minutes,
        title=view.title,
        cta=view.cta,
        headline=view.headline,
        subline=view.subline,
    )


def days_out(week: IsoWeek, view: ts.WeekView) -> list[DayOut]:
    return [
        DayOut(
            index=d.index,
            date=week.days[d.index],
            target_minutes=d.target,
            minutes=d.minutes,
            full=d.full,
            open=d.open,
            tag=d.tag.value,  # pyright: ignore[reportArgumentType]
            fill=float(d.fill),
        )
        for d in view.days
    ]


class TimesheetService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        self.policy = AccessPolicy(principal)

    # ------------------------------------------------------------------ who

    def _person(self) -> User:
        """The caller's own account; only people have a timesheet (TS-13)."""
        if self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to see your timesheet")
        user = self.session.get(User, self.principal.user_id)
        if user is None or user.kind is not UserKind.PERSON:
            raise PermissionDeniedError("this account has no timesheet")
        return user

    def _week(self, label: str | None) -> IsoWeek:
        current = IsoWeek.of(self.today)
        if label is None:
            return current
        try:
            week = IsoWeek.parse(label)
        except ValueError as error:
            raise RuleViolationError(str(error)) from error
        if week > current:
            raise RuleViolationError("a week that has not started cannot be booked")
        return week

    # ------------------------------------------------------------------ reading

    def _booked(self, user_id: int, week: IsoWeek) -> dict[tuple[str, str], list[int]]:
        """Minutes per (line, task) and weekday of the week."""
        return self._booked_via(user_id, week)[0]

    def _booked_via(
        self, user_id: int, week: IsoWeek
    ) -> tuple[dict[tuple[str, str], list[int]], dict[tuple[str, str], list[str | None]]]:
        """Minutes per (line, task) and weekday, and the API token each cell was last written
        through (its name; None for what was booked by hand), the same shape (TOK-3)."""
        rows = self.session.execute(
            select(
                TimeEntry.work_date,
                TimeEntry.project_id,
                TimeEntry.task_id,
                TimeEntry.category_key,
                TimeEntry.minutes,
                TimeEntry.api_token_id,
            ).where(
                TimeEntry.user_id == user_id,
                TimeEntry.work_date.between(week.monday, week.friday),
            )
        ).all()
        project_ids = {r.project_id for r in rows if r.project_id is not None}
        numbers = (
            dict(
                self.session.execute(
                    select(Project.id, Project.number).where(in_ids(Project.id, project_ids))
                ).all()
            )
            if project_ids
            else {}
        )
        kinds = {c.key: c.kind for c in self.profile.categories}
        cells: dict[tuple[str, str], list[int]] = {}
        via: dict[tuple[str, str], list[str | None]] = {}
        names = common.token_names(self.session, [r.api_token_id for r in rows])
        for work_date, project_id, task_id, category_key, minutes, token_id in rows:
            if project_id is not None:
                line = f"{PROJECT_PREFIX}{numbers[project_id]}"
                task = f"{TASK_PREFIX}{task_id}" if task_id is not None else GENERAL
            else:
                kind = kinds.get(category_key or "")
                line = TIME_OFF if kind is CategoryKind.TIME_OFF else OTHER_WORK
                task = category_key or ""
            cells.setdefault((line, task), [0] * WORKDAYS_PER_WEEK)[work_date.weekday()] += minutes
            if token_id is not None:
                marks = via.setdefault((line, task), [None] * WORKDAYS_PER_WEEK)
                marks[work_date.weekday()] = names.get(token_id)
        return cells, via

    def _planned_minutes(self, user: User, week: IsoWeek) -> dict[int, Fraction]:
        """The person's planned minutes this week per project id (exact)."""
        pattern = _pattern(user)
        by_project: dict[int, dict[Quarter, Fraction]] = defaultdict(dict)
        for project_id, quarter_start, days in self.session.execute(
            select(PlannedDays.project_id, PlannedDays.quarter_start, PlannedDays.days).where(
                PlannedDays.user_id == user.id
            )
        ):
            by_project[project_id][Quarter.containing(quarter_start)] = common.to_fraction(days)
        hours_per_day = self.profile.numbers.hours_per_day
        result: dict[int, Fraction] = {}
        for project_id, planned in by_project.items():
            hours = weekly_planned_hours(planned, pattern, week, hours_per_day)
            if hours > 0:
                result[project_id] = hours * 60
        return result

    def _submitted(self, user_id: int, week: IsoWeek) -> WeekSubmission | None:
        return self.session.get(WeekSubmission, (user_id, week.year, week.week))

    def _view(
        self,
        user: User,
        week: IsoWeek,
        booked: dict[tuple[str, str], list[int]],
        *,
        submitted: bool,
    ) -> ts.WeekView:
        pattern = _pattern(user)
        targets = list(pattern.minutes)
        per_day = [sum(cells[d] for cells in booked.values()) for d in range(WORKDAYS_PER_WEEK)]
        return ts.week_view(
            targets,
            per_day,
            today_index=_today_index(week, self.today),
            submitted=submitted,
            week_number=week.week,
        )

    def week_card(self) -> WeekCard | None:
        """The sidebar's card for the current week; None for accounts without a timesheet."""
        if self.principal.is_anonymous or self.principal.is_system:
            return None
        user = self.session.get(User, self.principal.user_id)
        if user is None or user.kind is not UserKind.PERSON:
            return None
        week = IsoWeek.of(self.today)
        booked = self._booked(user.id, week)
        submission = self._submitted(user.id, week)
        view = self._view(user, week, booked, submitted=submission is not None)
        return WeekCard(
            week=week.label,
            week_number=week.week,
            today_index=_today_index(week, self.today),
            days=days_out(week, view),
            submitted=submission is not None,
            state=week_state_out(view),
        )

    def week(self, label: str | None = None) -> TimesheetOut:
        user = self._person()
        week = self._week(label)
        return self._build(user, week)

    def _build(self, user: User, week: IsoWeek) -> TimesheetOut:
        numbers = self.profile.numbers
        booked, via = self._booked_via(user.id, week)
        submission = self._submitted(user.id, week)
        view = self._view(user, week, booked, submitted=submission is not None)
        planned = self._planned_minutes(user, week)

        # Lines of the week: planned projects and projects with time (TS-4).
        numbers_booked = {
            int(line.removeprefix(PROJECT_PREFIX))
            for line, _ in booked
            if line.startswith(PROJECT_PREFIX)
        }
        wanted = set(planned)
        projects: dict[int, Project] = {}
        if wanted or numbers_booked:
            query = select(Project).where(
                or_(
                    in_ids(Project.id, wanted) if wanted else false(),
                    Project.number.in_(numbers_booked) if numbers_booked else false(),
                )
            )
            projects = {p.id: p for p in self.session.scalars(query)}
        visible = self._visible(set(projects))
        project_lines: list[LineOut] = []
        tasks_by_project = self._tasks(set(projects))
        for project in projects.values():
            if project.id not in visible:
                continue
            key = f"{PROJECT_PREFIX}{project.number}"
            cells = {t: m for (line, t), m in booked.items() if line == key}
            marks = {t: m for (line, t), m in via.items() if line == key}
            plan = planned.get(project.id)
            choices = [
                TaskChoice(
                    key=f"{TASK_PREFIX}{task.id}",
                    name=task.name,
                    status=task_status(task.progress, task.planned_start, self.today).value,  # pyright: ignore[reportArgumentType]
                    position=task.position,
                )
                for task in tasks_by_project.get(project.id, [])
            ] + [TaskChoice(key=GENERAL, name="General", status=None, position=GENERAL_POSITION)]
            project_lines.append(
                LineOut(
                    key=key,
                    kind="project",
                    number=project.number,
                    name=project.name,
                    status=project.status.value,
                    planned_minutes=float(plan) if plan is not None else None,
                    unplanned=plan is None,
                    choices=choices,
                    minutes=cells,
                    via=marks,
                )
            )
        project_lines.sort(
            key=lambda line: (
                line.unplanned,
                -(line.planned_minutes or 0),
                -sum(sum(m) for m in line.minutes.values()),
                -(line.number or 0),
            )
        )

        pattern = _pattern(user)
        other_planned = other_work_planned_minutes(pattern, numbers.other_work_share)
        lines = [
            *project_lines,
            self._category_line(
                OTHER_WORK, "Other work", CategoryKind.OTHER_WORK, (booked, via), other_planned
            ),
            self._category_line(TIME_OFF, "Time off", CategoryKind.TIME_OFF, (booked, via), None),
        ]
        current = IsoWeek.of(self.today)
        return TimesheetOut(
            week=week.label,
            iso_year=week.year,
            iso_week=week.week,
            monday=week.monday,
            friday=week.friday,
            is_current=week == current,
            today_index=_today_index(week, self.today),
            previous=week.shifted(-1).label,
            next=week.shifted(1).label if week < current else None,
            days=days_out(week, view),
            lines=lines,
            submitted=submission is not None,
            submitted_at=submission.submitted_at if submission else None,
            state=week_state_out(view),
            step_minutes=numbers.timesheet_step_minutes,
            cap_minutes=numbers.day_cap_minutes,
            hours_per_day=numbers.hours_per_day,
            other_work_share=float(numbers.other_work_share),
        )

    def _category_line(
        self,
        key: str,
        name: str,
        kind: CategoryKind,
        booked_via: tuple[
            dict[tuple[str, str], list[int]], dict[tuple[str, str], list[str | None]]
        ],
        planned: Fraction | None,
    ) -> LineOut:
        booked, via = booked_via
        choices = [
            TaskChoice(key=c.key, name=c.label, status=None, position=index)
            for index, c in enumerate(self.profile.categories_of(kind))
        ]
        return LineOut(
            key=key,
            kind=kind.value,  # pyright: ignore[reportArgumentType]
            number=None,
            name=name,
            status=None,
            planned_minutes=float(planned) if planned is not None else None,
            unplanned=False,
            choices=choices,
            minutes={t: m for (line, t), m in booked.items() if line == key},
            via={t: m for (line, t), m in via.items() if line == key},
        )

    def _tasks(self, project_ids: set[int]) -> dict[int, list[Task]]:
        if not project_ids:
            return {}
        result: dict[int, list[Task]] = defaultdict(list)
        for task in self.session.scalars(
            select(Task)
            .where(in_ids(Task.project_id, project_ids))
            .order_by(Task.position, Task.id)
        ):
            result[task.project_id].append(task)
        return result

    def _visible(self, project_ids: set[int]) -> set[int]:
        """The projects among `project_ids` that the caller may see (own time on a project the
        caller can no longer see is simply not listed)."""
        if not project_ids:
            return set()
        rows = self.session.scalars(
            select(Project.id).where(
                in_ids(Project.id, project_ids), self.policy.project_filter(Permission.PROJECT_VIEW)
            )
        )
        return set(rows)

    # ------------------------------------------------------------------ writing

    def set_cell(self, label: str | None, data: CellSet) -> TimesheetOut:
        user = self._person()
        week = self._week(label)
        numbers = self.profile.numbers
        pattern = _pattern(user)

        if not week.monday <= data.day <= week.friday:
            raise RuleViolationError("that day is not in this week")
        if pattern.target_minutes(data.day) <= 0:
            raise RuleViolationError("time is booked on working days only")
        step = numbers.timesheet_step_minutes
        if data.minutes % step:
            raise RuleViolationError(f"time goes in steps of {step} minutes")

        project_id, task_id, category_key = self._target(data.line, data.task)

        existing = self.session.scalars(
            self._cell_query(user.id, data.day, project_id, task_id, category_key)
        ).one_or_none()
        old = existing.minutes if existing is not None else 0
        if data.minutes > old:
            others = (
                self.session.scalar(
                    select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(
                        TimeEntry.user_id == user.id, TimeEntry.work_date == data.day
                    )
                )
                or 0
            ) - old
            if others + data.minutes > numbers.day_cap_minutes:
                raise RuleViolationError(
                    f"a day holds at most {numbers.day_cap_minutes // 60} hours"
                )

        if data.minutes == old:
            return self._build(user, week)  # nothing changes, so a submitted week stays submitted
        if data.minutes == 0:
            if existing is not None:
                self.session.delete(existing)
        elif existing is None:
            self.session.add(
                TimeEntry(
                    user_id=user.id,
                    work_date=data.day,
                    project_id=project_id,
                    task_id=task_id,
                    category_key=category_key,
                    minutes=data.minutes,
                    api_token_id=self.principal.token_id,
                )
            )
        else:
            existing.minutes = data.minutes
            existing.updated_at = utcnow()
            existing.api_token_id = self.principal.token_id
        # Changing a submitted week reopens it (TS-10).
        self.session.execute(
            delete(WeekSubmission).where(
                WeekSubmission.user_id == user.id,
                WeekSubmission.iso_year == week.year,
                WeekSubmission.iso_week == week.week,
            )
        )
        self.session.flush()
        result = self._build(user, week)
        self.session.commit()
        return result

    def _cell_query(
        self,
        user_id: int,
        day: date,
        project_id: int | None,
        task_id: int | None,
        category_key: str | None,
    ) -> Select[TimeEntry]:
        query = select(TimeEntry).where(TimeEntry.user_id == user_id, TimeEntry.work_date == day)
        if project_id is not None:
            query = query.where(TimeEntry.project_id == project_id)
            query = query.where(
                TimeEntry.task_id == task_id if task_id is not None else TimeEntry.task_id.is_(None)
            )
        else:
            query = query.where(TimeEntry.category_key == category_key)
        return query

    def _target(self, line: str, task: str) -> tuple[int | None, int | None, str | None]:
        """(project id, task id, category key) of a cell; refuses what cannot be booked."""
        if line.startswith(PROJECT_PREFIX):
            try:
                number = int(line.removeprefix(PROJECT_PREFIX))
            except ValueError as error:
                raise RuleViolationError(f"unknown line {line!r}") from error
            project = self.session.scalar(
                select(Project).where(
                    Project.number == number,
                    self.policy.project_filter(Permission.PROJECT_VIEW),
                )
            )
            if project is None:
                raise NotFoundError(f"no project {number}")
            if task == GENERAL:
                return project.id, None, None
            if task.startswith(TASK_PREFIX):
                try:
                    task_id = int(task.removeprefix(TASK_PREFIX))
                except ValueError as error:
                    raise RuleViolationError(f"unknown task {task!r}") from error
                found = self.session.scalar(
                    select(Task.id).where(Task.id == task_id, Task.project_id == project.id)
                )
                if found is None:
                    raise NotFoundError("that task is not in this project")
                return project.id, task_id, None
            raise RuleViolationError(f"unknown task {task!r}")
        kinds = {OTHER_WORK: CategoryKind.OTHER_WORK, TIME_OFF: CategoryKind.TIME_OFF}
        kind = kinds.get(line)
        if kind is None:
            raise RuleViolationError(f"unknown line {line!r}")
        if task not in {c.key for c in self.profile.categories_of(kind)}:
            raise RuleViolationError(f"{task!r} is not a category of {line}")
        return None, None, task

    def submit(self, label: str | None) -> TimesheetOut:
        """Mark the week submitted (D-007): a soft marker, no lock, no approval."""
        user = self._person()
        week = self._week(label)
        if self._submitted(user.id, week) is None:
            self.session.add(
                WeekSubmission(user_id=user.id, iso_year=week.year, iso_week=week.week)
            )
            self.session.flush()
        result = self._build(user, week)
        self.session.commit()
        return result
