"""Helpers shared by the project, planning and plan services: people, days, snapshots, logbook."""

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.ids import in_ids
from momato.db.models import (
    ActionPlan,
    ActionPlanProject,
    ApiToken,
    LogEntry,
    OrgNode,
    PlannedDays,
    Project,
    ProjectMember,
    TimeEntry,
    User,
)
from momato.domain import logbook as lb
from momato.domain.calendar import Quarter
from momato.domain.planning import DaysSummary, days_summary
from momato.domain.projects import PRIORITY_LABELS, STATUS_LABELS
from momato.schemas.plans import DaysMeter
from momato.schemas.projects import DaysOut, PersonRef


def person_refs(session: Session, ids: Collection[int]) -> dict[int, PersonRef]:
    """Name, colour and job title of people by id (also deactivated ones: history keeps names)."""
    if not ids:
        return {}
    rows = session.execute(
        select(User.id, User.name, User.hue, User.job_title).where(in_ids(User.id, ids))
    )
    return {
        user_id: PersonRef(id=user_id, name=name, hue=hue, job_title=title)
        for user_id, name, hue, title in rows
    }


def to_fraction(value: Decimal | int | None) -> Fraction:
    return Fraction(value) if value is not None else Fraction(0)


def planned_by_quarter(
    session: Session, project_ids: Collection[int]
) -> dict[int, dict[Quarter, Fraction]]:
    """Planned days per project and quarter, summed over all members."""
    result: dict[int, dict[Quarter, Fraction]] = defaultdict(dict)
    if not project_ids:
        return result
    rows = session.execute(
        select(PlannedDays.project_id, PlannedDays.quarter_start, func.sum(PlannedDays.days))
        .where(in_ids(PlannedDays.project_id, project_ids))
        .group_by(PlannedDays.project_id, PlannedDays.quarter_start)
    )
    for project_id, quarter_start, days in rows:
        result[project_id][Quarter.containing(quarter_start)] = to_fraction(days)
    return result


def logged_minutes(session: Session, project_ids: Collection[int]) -> dict[int, int]:
    """Minutes booked on each project by anyone (members or not)."""
    if not project_ids:
        return {}
    rows = session.execute(
        select(TimeEntry.project_id, func.sum(TimeEntry.minutes))
        .where(in_ids(TimeEntry.project_id, project_ids))
        .group_by(TimeEntry.project_id)
    )
    return {project_id: int(minutes) for project_id, minutes in rows if project_id is not None}


def day_summaries(
    session: Session, project_ids: Collection[int], today: date, hours_per_day: int
) -> dict[int, DaysSummary]:
    planned = planned_by_quarter(session, project_ids)
    logged = logged_minutes(session, project_ids)
    return {
        project_id: days_summary(
            planned.get(project_id, {}), logged.get(project_id, 0), today, hours_per_day
        )
        for project_id in project_ids
    }


def days_out(summary: DaysSummary) -> DaysOut:
    return DaysOut(
        planned=float(summary.planned),
        logged=float(summary.logged),
        expected=float(summary.expected),
        logged_percent=float(summary.logged_percent),
        expected_percent=float(summary.expected_percent),
    )


def meter(summary: DaysSummary) -> DaysMeter:
    return DaysMeter(**days_out(summary).model_dump())


def sum_summaries(summaries: Iterable[DaysSummary]) -> DaysSummary:
    """Combine projects into one total (an action plan, a department group), clamping percents."""
    planned = logged = expected = Fraction(0)
    for s in summaries:
        planned += s.planned
        logged += s.logged
        expected += s.expected

    def percent(part: Fraction) -> Fraction:
        return (
            min(Fraction(100), max(Fraction(0), part * 100 / planned))
            if planned > 0
            else Fraction(0)
        )

    return DaysSummary(planned, logged, expected, percent(logged), percent(expected))


def snapshot(session: Session, project: Project) -> lb.CoreSnapshot:
    """The project's core fields as shown to users, for comparing before and after (LB-1)."""
    coordinator = session.scalar(select(User.name).where(User.id == project.coordinator_id))
    node = session.scalar(select(OrgNode.name).where(OrgNode.id == project.org_node_id))
    members = dict(
        session.execute(
            select(User.id, User.name)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project.id)
        ).all()
    )
    plans = dict(
        session.execute(
            select(ActionPlan.id, ActionPlan.name)
            .join(ActionPlanProject, ActionPlanProject.plan_id == ActionPlan.id)
            .where(ActionPlanProject.project_id == project.id)
        ).all()
    )
    return lb.CoreSnapshot(
        title=project.name,
        status=STATUS_LABELS[project.status],
        start_date=project.start_date,
        end_date=project.end_date,
        coordinator=coordinator or "",
        org_node=node or "",
        priority=PRIORITY_LABELS[project.priority],
        goal=project.goal,
        people=members,
        action_plans=plans,
    )


def token_names(session: Session, ids: Iterable[int | None]) -> dict[int, str]:
    """The names of the API tokens things were done through ("via", TOK-3), by token id."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = session.execute(select(ApiToken.id, ApiToken.name).where(in_ids(ApiToken.id, wanted)))
    return {row.id: row.name for row in rows}


def write_log(
    session: Session,
    project: Project,
    actor_id: int,
    entries: Iterable[lb.LogEntry],
    *,
    via: int | None = None,
) -> None:
    """Add logbook entries in the current transaction, so they commit with the change (LB-1).
    `via` is the API token the change was made through, if any (TOK-3)."""
    now = utcnow()
    for entry in entries:
        session.add(
            LogEntry(
                project_id=project.id,
                at=now,
                actor_id=actor_id,
                field_key=entry.field,
                from_value=entry.from_value,
                to_value=entry.to_value,
                api_token_id=via,
            )
        )


def member_ids(session: Session, project_id: int) -> set[int]:
    return set(
        session.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id))
    )


def group_by_project(pairs: Iterable[tuple[int, int]]) -> Mapping[int, list[int]]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for project_id, other in pairs:
        grouped[project_id].append(other)
    return grouped
