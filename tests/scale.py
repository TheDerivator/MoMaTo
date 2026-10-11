"""The scale data set of REQUIREMENTS 8.5 and D-028: about 5,000 projects, 500 people and two years
of time entries (some 750,000 rows), added to the sample data deterministically."""

import random
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from momato.db.models import (
    LogEntry,
    OrgNode,
    PlannedDays,
    Project,
    ProjectMember,
    Task,
    TimeEntry,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.domain.calendar import Quarter
from momato.domain.logbook import LogField

SCALE_PEOPLE = 500
SCALE_PROJECTS = 5_000
YEARS_OF_TIME = 2
FIRST_SCALE_NUMBER = 20_000
CHUNK = 20_000

STATUSES = ["idea", "preparation", "progress", "progress", "progress", "hold", "finished"]
WORDS = [
    "coating", "roll", "furnace", "sensor", "audit", "supplier", "recipe", "defect", "vibration",
    "calibration", "trial", "report", "maintenance", "scrap", "yield", "line", "cooling", "pump",
    "gearbox", "belt", "crane", "safety", "energy", "water", "steam", "inspection",
]  # fmt: skip
FIRST = ["An", "Bo", "Cy", "Di", "El", "Fa", "Gi", "Ha", "Ik", "Jo", "Ka", "Lu", "Mo", "Ni", "Ot"]
LAST = ["Aerts", "Bos", "Claes", "Dumont", "Evers", "Fabry", "Goris", "Hendrix", "Jacobs", "Kools"]


@dataclass(frozen=True)
class ScaleReport:
    people: int
    projects: int
    time_entries: int


def _chunks(rows: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), CHUNK):
        yield rows[start : start + CHUNK]


def _weekdays(first: date, last: date) -> list[date]:
    days: list[date] = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def add_scale_data(session: Session, today: date, seed: int = 7) -> ScaleReport:
    """Add people, projects with members, tasks, planned days and a logbook, and two years of
    booked time, to a database that holds the sample data."""
    rng = random.Random(seed)
    connection = session.connection()
    nodes = list(session.scalars(select(OrgNode.id).where(OrgNode.parent_id.is_not(None))))

    # ---- people
    have = (
        session.scalar(select(func.count()).select_from(User).where(User.kind == UserKind.PERSON))
        or 0
    )
    new_people = [
        {
            "kind": UserKind.PERSON,
            "name": f"{rng.choice(FIRST)}{i} {rng.choice(LAST)}",
            "org_node_id": rng.choice(nodes),
            "hue": rng.randrange(360),
            "status": UserStatus.ACTIVE,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            "work_minutes_mon": 480,
            "work_minutes_tue": 480,
            "work_minutes_wed": 480,
            "work_minutes_thu": 480,
            "work_minutes_fri": 480,
            "must_change_password": False,
        }
        for i in range(max(SCALE_PEOPLE - have, 0))
    ]
    for chunk in _chunks(new_people):
        connection.execute(insert(User), chunk)
    people = list(session.scalars(select(User.id).where(User.kind == UserKind.PERSON)))

    # ---- projects
    now = datetime(2026, 9, 1, tzinfo=UTC)
    existing = session.scalar(select(func.count()).select_from(Project)) or 0
    wanted = max(SCALE_PROJECTS - existing, 0)
    rows: list[dict[str, Any]] = []
    for i in range(wanted):
        start = today - timedelta(days=rng.randint(0, 700))
        words = " ".join(rng.sample(WORDS, 3))
        rows.append(
            {
                "number": FIRST_SCALE_NUMBER + i,
                "name": f"Generated project {i}: {words}",
                "org_node_id": rng.choice(nodes),
                "status": rng.choice(STATUSES),
                "coordinator_id": rng.choice(people),
                "start_date": start,
                "end_date": start + timedelta(days=rng.randint(60, 540)),
                "goal": f"Improve the {words}.",
                "priority": rng.choice(["low", "medium", "high"]),
                "created_at": now,
                "updated_at": now,
                "version": 1,
            }
        )
    for chunk in _chunks(rows):
        connection.execute(insert(Project), chunk)
    projects = list(
        session.execute(
            select(Project.id, Project.coordinator_id, Project.start_date, Project.end_date).where(
                Project.number >= FIRST_SCALE_NUMBER
            )
        )
    )

    # ---- members, tasks, planned days, logbook
    members: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    by_person: dict[int, list[int]] = defaultdict(list)
    quarters = [Quarter.containing(today), Quarter.containing(today).shifted(1)]
    for project_id, coordinator, start, end in projects:
        team = {coordinator, *rng.sample(people, 2)}
        for person in sorted(team):
            members.append({"project_id": project_id, "user_id": person})
            by_person[person].append(project_id)
            for quarter in quarters:
                planned.append(
                    {
                        "project_id": project_id,
                        "user_id": person,
                        "quarter_start": quarter.start,
                        "days": Decimal(rng.choice([0, 1, 2, 3, 5, 8]) / 2),
                    }
                )
        span = (end - start).days or 1
        for position, name in enumerate(["Define", "Design", "Build", "Test", "Roll out"]):
            first = start + timedelta(days=span * position // 5)
            tasks.append(
                {
                    "project_id": project_id,
                    "position": position,
                    "name": name,
                    "planned_start": first,
                    "planned_end": max(first, start + timedelta(days=span * (position + 1) // 5)),
                    "is_milestone": False,
                    "progress": rng.choice([0, 25, 50, 100]),
                    "version": 1,
                }
            )
        for field in (LogField.CREATED, LogField.STATUS):
            log.append(
                {
                    "project_id": project_id,
                    "at": now,
                    "actor_id": coordinator,
                    "field_key": field,
                    "from_value": None,
                    "to_value": "Created" if field is LogField.CREATED else "In progress",
                }
            )
    for table, data in (
        (ProjectMember, members),
        (Task, tasks),
        (PlannedDays, planned),
        (LogEntry, log),
    ):
        for chunk in _chunks(data):
            connection.execute(insert(table), chunk)

    # ---- two years of booked time: two to four projects a day for everyone
    days = _weekdays(today - timedelta(days=365 * YEARS_OF_TIME), today - timedelta(days=1))
    total = 0
    batch: list[dict[str, Any]] = []
    for person in people:
        mine = by_person.get(person) or []
        if not mine:
            continue
        for day in days:
            picked = rng.sample(mine, min(len(mine), rng.choice((2, 3, 3, 4))))
            for project_id in picked:
                batch.append(
                    {
                        "user_id": person,
                        "work_date": day,
                        "project_id": project_id,
                        "task_id": None,
                        "category_key": None,
                        "minutes": 60 * rng.choice((1, 1, 2)),
                        "updated_at": now,
                    }
                )
            if len(batch) >= CHUNK:
                connection.execute(insert(TimeEntry), batch)
                total += len(batch)
                batch = []
    if batch:
        connection.execute(insert(TimeEntry), batch)
        total += len(batch)
    session.commit()
    return ScaleReport(people=len(people), projects=existing + len(projects), time_entries=total)
