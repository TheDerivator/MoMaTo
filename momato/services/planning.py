"""People & days: planned days per member and quarter, and the time logged (PD-1 to PD-5)."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import case, delete, func, literal, select
from sqlalchemy.orm import Session

from momato.db.models import PlannedDays, Project, ProjectMember, TimeEntry
from momato.domain.calendar import Quarter, quarters_overlapping
from momato.domain.errors import RuleViolationError
from momato.domain.fields import Profile
from momato.domain.planning import days_from_minutes
from momato.identity.principal import Principal
from momato.schemas.projects import (
    PlanCell,
    PlannedCellSet,
    PlannedDaysGrid,
    PlanRow,
)
from momato.services import common
from momato.services.projects_access import ProjectAccess

HALF_DAY = Fraction(1, 2)


class PlanningService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.profile = profile
        self.today = today
        self.access = ProjectAccess(session, principal)

    def grid(self, number: int) -> PlannedDaysGrid:
        return self._grid(self.access.visible(number))

    def _grid(self, project: Project) -> PlannedDaysGrid:
        session = self.session
        hours_per_day = self.profile.numbers.hours_per_day
        planned: dict[tuple[int, Quarter], Fraction] = {}
        for user_id, quarter_start, days in session.execute(
            select(PlannedDays.user_id, PlannedDays.quarter_start, PlannedDays.days).where(
                PlannedDays.project_id == project.id
            )
        ):
            planned[(user_id, Quarter.containing(quarter_start))] = common.to_fraction(days)

        first_booked = session.scalar(
            select(func.min(TimeEntry.work_date)).where(TimeEntry.project_id == project.id)
        )
        last_booked = session.scalar(
            select(func.max(TimeEntry.work_date)).where(TimeEntry.project_id == project.id)
        )
        quarters = set(quarters_overlapping(project.start_date, project.end_date))
        quarters |= {q for _, q in planned}
        if first_booked is not None and last_booked is not None:
            quarters |= set(quarters_overlapping(first_booked, last_booked))
        columns = sorted(quarters)

        logged_minutes: dict[tuple[int, Quarter], int] = {}
        if columns:
            bucket = case(
                *[
                    (TimeEntry.work_date.between(q.start, q.end), literal(index))
                    for index, q in enumerate(columns)
                ],
                else_=literal(-1),
            )
            for user_id, index, minutes in session.execute(
                select(TimeEntry.user_id, bucket, func.sum(TimeEntry.minutes))
                .where(TimeEntry.project_id == project.id)
                .group_by(TimeEntry.user_id, bucket)
            ):
                if index >= 0:
                    logged_minutes[(user_id, columns[index])] = int(minutes)

        member_ids = set(
            session.scalars(
                select(ProjectMember.user_id).where(ProjectMember.project_id == project.id)
            )
        )
        booked_by = {user_id for user_id, _ in logged_minutes}
        refs = common.person_refs(session, member_ids | booked_by | {project.coordinator_id})

        def row(user_id: int, *, is_member: bool) -> PlanRow:
            cells = [
                PlanCell(
                    quarter_start=q.start,
                    planned=float(planned.get((user_id, q), 0)),
                    logged=float(
                        days_from_minutes(logged_minutes.get((user_id, q), 0), hours_per_day)
                    ),
                    upcoming=q.start > self.today,
                )
                for q in columns
            ]
            return PlanRow(
                person=refs[user_id],
                is_coordinator=user_id == project.coordinator_id,
                is_member=is_member,
                cells=cells,
                planned_total=sum(c.planned for c in cells),
                logged_total=sum(c.logged for c in cells),
            )

        ordered = sorted(
            member_ids, key=lambda u: (u != project.coordinator_id, refs[u].name.casefold(), u)
        )
        rows = [row(u, is_member=True) for u in ordered]
        extra = sorted(booked_by - member_ids, key=lambda u: (refs[u].name.casefold(), u))
        also = [row(u, is_member=False) for u in extra]
        return PlannedDaysGrid(
            quarters=[q.start for q in columns],
            workdays=[q.workdays for q in columns],
            rows=rows,
            also_booked=also,
            total_planned=sum(r.planned_total for r in rows),
            total_logged=sum(r.logged_total for r in [*rows, *also]),
            hours_per_day=hours_per_day,
        )

    def set_cell(self, number: int, data: PlannedCellSet) -> PlannedDaysGrid:
        """Set planned days of a member in a quarter: steps of 0.5, up to the quarter's workdays."""
        project = self.access.editable(number)
        try:
            quarter = Quarter.starting(data.quarter_start)
        except ValueError as error:
            raise RuleViolationError("quarter_start must be the first day of a quarter") from error
        days = Fraction(str(data.days))
        if days % HALF_DAY != 0:
            raise RuleViolationError("planned days go in steps of 0.5")
        if days > quarter.workdays:
            raise RuleViolationError(f"{quarter.label} has only {quarter.workdays} workdays")
        member = self.session.get(ProjectMember, (project.id, data.user_id))
        if member is None:
            raise RuleViolationError("only people involved in the project have planned days")
        cell = self.session.get(PlannedDays, (project.id, data.user_id, quarter.start))
        if days == 0:
            if cell is not None:
                self.session.execute(
                    delete(PlannedDays).where(
                        PlannedDays.project_id == project.id,
                        PlannedDays.user_id == data.user_id,
                        PlannedDays.quarter_start == quarter.start,
                    )
                )
        elif cell is None:
            self.session.add(
                PlannedDays(
                    project_id=project.id,
                    user_id=data.user_id,
                    quarter_start=quarter.start,
                    days=Decimal(str(data.days)),
                )
            )
        else:
            cell.days = Decimal(str(data.days))
        self.session.flush()
        grid = self._grid(project)
        self.session.commit()
        return grid
