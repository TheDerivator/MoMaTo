"""Exports, a proof of concept (EXP-1 – EXP-4, D-033): the project list as shown, and booked time
for a period and branch, each as CSV or XLSX. Exactly what the caller may see on screen.

The file is written completely (to a spooled temporary file, in batches of rows) before the
response starts, so the database session is done with when the bytes stream out.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import IO, cast

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from momato.db.ids import in_ids
from momato.db.models import (
    OrgNode,
    Project,
    ProjectDetail,
    Task,
    TimeEntry,
    User,
    WeekSubmission,
)
from momato.db.models.people import UserKind
from momato.domain.errors import NotFoundError, RuleViolationError
from momato.domain.fields import FieldDef, FieldType, Profile
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.services import common
from momato.services.export_files import Cell, ExportFormat, write_table
from momato.services.projects import ProjectFilters, ProjectService

BATCH = 500  # rows read from the database at a time
MAX_DAYS = 366 * 3  # the longest period of a time export

PROJECT_COLUMNS = [
    "Number",
    "Project",
    "Organisation",
    "Status",
    "Priority",
    "Coordinator",
    "Start date",
    "End date",
    "Goal",
]
TIME_COLUMNS = [
    "Date",
    "Week",
    "Person",
    "Organisation",
    "Project number",
    "Project",
    "Task",
    "Category",
    "Hours",
    "Week submitted",
]


@dataclass(frozen=True)
class Download:
    """A file to send: its bytes (a spooled file, closed by whoever streams it), type and name."""

    file: IO[bytes]
    media_type: str
    filename: str


@dataclass(frozen=True)
class _Names:
    """Names that detail values of the person and project types refer to."""

    people: dict[int, str]
    projects: dict[int, str]


def _iso(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso.year, iso.week


class ExportService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today

    # ------------------------------------------------------------------ the project list (EXP-1)

    @staticmethod
    def _detail_cell(field_type: FieldType | None, value: object, names: _Names) -> Cell:
        if value is None or value == "" or value == []:
            return None
        if field_type is FieldType.NUMBER and isinstance(value, int | float):
            return value
        if field_type is FieldType.DATE and isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
        if field_type is FieldType.YES_NO and isinstance(value, bool):
            return value
        if field_type is FieldType.TAGS and isinstance(value, list):
            return "; ".join(str(v) for v in cast("list[object]", value))
        if field_type is FieldType.PERSON and isinstance(value, int):
            return names.people.get(value, "")
        if field_type is FieldType.PROJECT and isinstance(value, int):
            return names.projects.get(value, "")
        return str(value)

    def projects(self, filters: ProjectFilters, kind: ExportFormat) -> Download:
        """The list with its filters: core fields, then every detail field of the profile."""
        service = ProjectService(self.session, self.principal, self.profile, today=self.today)
        fields = [f for card in self.profile.cards for f in card.fields if f.core is None]
        header = [*PROJECT_COLUMNS, *(f.label for f in fields)]

        def rows() -> Iterator[list[Cell]]:
            for batch in service.export_batches(filters, BATCH):
                ids = [p.id for p, _ in batch]
                details: dict[int, dict[str, object]] = {i: {} for i in ids}
                for project_id, key, value in self.session.execute(
                    select(
                        ProjectDetail.project_id, ProjectDetail.field_key, ProjectDetail.value
                    ).where(in_ids(ProjectDetail.project_id, ids))
                ):
                    details[project_id][key] = json.loads(value)
                names = self._names(details, fields)
                coordinators = common.person_refs(
                    self.session, {p.coordinator_id for p, _ in batch}
                )
                for project, node_name in batch:
                    yield [
                        project.number,
                        project.name,
                        node_name,
                        project.status.value,
                        project.priority.value,
                        coordinators[project.coordinator_id].name,
                        project.start_date,
                        project.end_date,
                        project.goal,
                        *(
                            self._detail_cell(f.type, details[project.id].get(f.key), names)
                            for f in fields
                        ),
                    ]

        file = write_table(kind, header, rows(), sheet="Projects")
        return Download(file, kind.media_type, f"projects-{self.today.isoformat()}.{kind.value}")

    def _names(self, details: dict[int, dict[str, object]], fields: list[FieldDef]) -> _Names:
        people: set[int] = set()
        numbers: set[int] = set()
        for values in details.values():
            for f in fields:
                value = values.get(f.key)
                if f.type is FieldType.PERSON and isinstance(value, int):
                    people.add(value)
                if f.type is FieldType.PROJECT and isinstance(value, int):
                    numbers.add(value)
        rows = self.session.execute(
            select(Project.number, Project.name).where(in_ids(Project.number, numbers))
        )
        return _Names(
            people={u: r.name for u, r in common.person_refs(self.session, people).items()},
            projects={row.number: f"#{row.number} {row.name}" for row in rows},
        )

    # ------------------------------------------------------------------ booked time (EXP-2)

    def time_entries(
        self, start: date, end: date, node: int | None, kind: ExportFormat
    ) -> Download:
        """Time booked in a period by the people of a branch, as far as the caller may see it."""
        if end < start:
            raise RuleViolationError("the period ends before it starts")
        if (end - start).days > MAX_DAYS:
            raise RuleViolationError("a period of at most three years can be exported")
        tree = self.principal.tree
        if node is not None and node not in tree:
            raise NotFoundError(f"no org node {node}")
        visible = AccessPolicy(self.principal).people_hours_filter()
        categories = {c.key: c.label for c in self.profile.categories}
        person_node = aliased(OrgNode)

        def rows() -> Iterator[list[Cell]]:
            # Keyset paging on (date, person, id): the file is in that order throughout.
            after: tuple[date, int, int] | None = None
            while True:
                query = (
                    select(
                        TimeEntry,
                        User.name,
                        person_node.name,
                        Project.number,
                        Project.name,
                        Task.name,
                    )
                    .join(User, User.id == TimeEntry.user_id)
                    .outerjoin(person_node, person_node.id == User.org_node_id)
                    .outerjoin(Project, Project.id == TimeEntry.project_id)
                    .outerjoin(Task, Task.id == TimeEntry.task_id)
                    .where(
                        User.kind == UserKind.PERSON,
                        TimeEntry.work_date >= start,
                        TimeEntry.work_date <= end,
                        visible,
                    )
                    .order_by(TimeEntry.work_date, TimeEntry.user_id, TimeEntry.id)
                    .limit(BATCH)
                )
                if after is not None:
                    day, user_id, entry_id = after
                    query = query.where(
                        or_(
                            TimeEntry.work_date > day,
                            and_(TimeEntry.work_date == day, TimeEntry.user_id > user_id),
                            and_(
                                TimeEntry.work_date == day,
                                TimeEntry.user_id == user_id,
                                TimeEntry.id > entry_id,
                            ),
                        )
                    )
                if node is not None:
                    query = query.where(in_ids(User.org_node_id, tree.subtree(node)))
                found = list(self.session.execute(query))
                if not found:
                    return
                last = found[-1][0]
                after = (last.work_date, last.user_id, last.id)
                submitted = self._submitted({(e.user_id, *_iso(e.work_date)) for e, *_ in found})
                for entry, person, org, number, project, task in found:
                    year, week = _iso(entry.work_date)
                    yield [
                        entry.work_date,
                        f"{year}-W{week:02d}",
                        person,
                        org,
                        number,
                        project,
                        task,
                        categories.get(entry.category_key or "") if entry.category_key else None,
                        round(entry.minutes / 60, 2),
                        (entry.user_id, year, week) in submitted,
                    ]

        file = write_table(kind, TIME_COLUMNS, rows(), sheet="Time entries")
        name = f"time-entries-{start.isoformat()}-{end.isoformat()}.{kind.value}"
        return Download(file, kind.media_type, name)

    def _submitted(self, weeks: set[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
        users = {u for u, _, _ in weeks}
        rows = self.session.execute(
            select(WeekSubmission.user_id, WeekSubmission.iso_year, WeekSubmission.iso_week).where(
                in_ids(WeekSubmission.user_id, users)
            )
        )
        return {(row.user_id, row.iso_year, row.iso_week) for row in rows} & weeks
