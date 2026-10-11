"""Sample data that looks well used (D-037): curated JSON plus a seeded generator, then the loader.

`build_sample` turns `data/sample-data.json` and a seeded random generator into plain specs (the
organisation, people, projects with tasks, planned days, remarks and logbook, action plans and two
years of booked time) without touching a database, so tests can derive their expectations from the
same specs. `load_sample_data` inserts them.

Everything is built relative to `today` (D-027): with today = Thursday 8 October 2026 the result is
the design's data; with another date it is the same story, moved. Time is booked on working days
only, up to yesterday.
"""

import hashlib
import json
import random
import struct
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from momato.db.models import (
    ActionPlan,
    ActionPlanProject,
    Attachment,
    Availability,
    LogEntry,
    OrgNode,
    PlannedDays,
    Post,
    Project,
    ProjectDetail,
    ProjectMember,
    Task,
    TimeEntry,
    User,
    WeekSubmission,
)
from momato.domain import logbook as lb
from momato.domain.calendar import IsoWeek, Quarter, quarters_overlapping
from momato.domain.capacity import WorkPattern, quarter_availability_days, year_availability_days
from momato.domain.fields import CategoryKind, FieldType, Profile
from momato.domain.formatting import format_date
from momato.domain.projects import STATUS_LABELS, Priority, ProjectStatus
from momato.domain.tasks import effective_end, tasks_from_template
from momato.domain.usernames import unique_username
from momato.identity.passwords import hash_password

SAMPLE_FILE = Path(__file__).resolve().parent / "data" / "sample-data.json"
SAMPLE_TODAY = date(2026, 10, 8)  # "today" in the design and its mockups
SEED = "momato-sample-1"

GENERATED_PROJECTS = 184  # with the design's 16: about 200
HISTORY_DAYS = 730  # two years of booked time
STEP = 60  # minutes
HUES = (285, 200, 330, 30, 140, 60, 250, 170, 100, 220, 10, 350, 310, 120, 190, 45)
DESIGN_HUES = {
    "Anouk Smit": 285,
    "Tomás Rivera": 200,
    "Sofia Lind": 330,
    "Ines Okafor": 30,
    "Lukas Brandt": 140,
    "Noor Haddad": 60,
    "Pieter Kools": 250,
    "Ravi Menon": 170,
    "Elena Duarte": 10,
    "Jonas Weber": 100,
    "Hana Sato": 220,
    "Mira Halden": 350,
}
# What Anna Claes booked on Monday and Tuesday of the design's week 41, in hours: (#4102, #4120,
# #4231, #4307, other work) per day.
DESIGN_WEEK = {0: (3, 2, 2, 0, 1), 1: (4, 2, 1, 0, 1)}
DESIGN_PERSON = "Anna Claes"


# ---------------------------------------------------------------- specs


@dataclass(frozen=True)
class PersonRef:
    """A detail value that points at a person, resolved to an id when loading."""

    name: str


@dataclass
class OrgSpec:
    path: str  # "STL/Quality"
    name: str
    parent: str | None
    is_department: bool
    position: int


@dataclass
class PersonSpec:
    name: str
    title: str
    node: str
    hue: int
    pattern: tuple[int, int, int, int, int]
    availability: dict[int, Decimal] = field(default_factory=dict[int, Decimal])  # year → days

    @property
    def department(self) -> str:
        return self.node.split("/")[0]


@dataclass
class TaskSpec:
    name: str
    planned_start: date
    planned_end: date
    revised_end: date | None
    is_milestone: bool
    progress: int


@dataclass
class ReplySpec:
    author: str
    at: datetime
    body: str


@dataclass
class RemarkSpec:
    author: str
    at: datetime
    body: str
    replies: list[ReplySpec] = field(default_factory=list[ReplySpec])
    image: str | None = None  # the key of a generated picture


@dataclass
class LogSpec:
    at: datetime
    actor: str
    field: lb.LogField
    from_value: str | None
    to_value: str | None


@dataclass
class ProjectSpec:
    number: int
    name: str
    node: str
    status: ProjectStatus
    coordinator: str
    members: list[str]  # including the coordinator, who comes first
    start: date
    end: date
    goal: str
    priority: Priority
    created_at: datetime
    tasks: list[TaskSpec] = field(default_factory=list[TaskSpec])
    planned: dict[tuple[str, date], Decimal] = field(
        default_factory=dict[tuple[str, date], Decimal]
    )  # (person, quarter)
    details: dict[str, object] = field(default_factory=dict[str, object])
    plans: list[str] = field(default_factory=list[str])
    remarks: list[RemarkSpec] = field(default_factory=list[RemarkSpec])
    log: list[LogSpec] = field(default_factory=list[LogSpec])


@dataclass
class EntrySpec:
    person: str
    day: date
    minutes: int
    project: int | None = None  # a project number
    task: int | None = None  # index into the project's tasks; None is General
    category: str | None = None


@dataclass
class PlanSpec:
    name: str
    owner_node: str
    coordinator: str
    hue: int
    description: str
    projects: list[int]
    position: int


@dataclass
class Sample:
    today: date
    root: str
    org: list[OrgSpec]
    people: list[PersonSpec]
    projects: list[ProjectSpec]
    plans: list[PlanSpec]
    entries: list[EntrySpec]
    submissions: list[tuple[str, IsoWeek]]  # (person, week)


# ---------------------------------------------------------------- building


def _rng(*parts: object) -> random.Random:
    return random.Random(":".join([SEED, *map(str, parts)]))  # noqa: S311  (sample data, not secrets)


def _at(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(8 + rng.randint(0, 8), rng.randint(0, 59)), tzinfo=UTC)


def _half(value: float | Fraction) -> Decimal:
    """Round to the nearest half day, at least 0.5."""
    halves = max(1, int(float(value) * 2 + 0.5))
    return Decimal(halves) / 2


def _flatten_org(spec: list[Any]) -> list[OrgSpec]:
    nodes: list[OrgSpec] = []

    def add(item: str | dict[str, Any], parent: str | None, position: int, depth: int) -> None:
        name = item if isinstance(item, str) else item["name"]
        path = f"{parent}/{name}" if parent else name
        nodes.append(OrgSpec(path, name, parent, depth == 0, position))
        if isinstance(item, dict):
            for index, child in enumerate(item["children"]):
                add(child, path, index, depth + 1)

    for index, top in enumerate(spec):
        add(top, None, index, 0)
    return nodes


def _people(raw: list[dict[str, Any]], today: date) -> list[PersonSpec]:
    people: list[PersonSpec] = []
    for index, item in enumerate(raw):
        pattern = tuple(item.get("pattern", [480] * 5))
        availability = {
            today.year + int(offset): Decimal(str(days))
            for offset, days in item.get("availability", {}).items()
        }
        people.append(
            PersonSpec(
                name=item["name"],
                title=item["title"],
                node=item["node"],
                hue=DESIGN_HUES.get(item["name"], HUES[index % len(HUES)]),
                pattern=pattern,  # pyright: ignore[reportArgumentType]
                availability=availability,
            )
        )
    return people


def _shift(day: str, delta: int) -> date:
    return date.fromisoformat(day) + timedelta(days=delta)


def _status_for(start: date, end: date, today: date, rng: random.Random) -> ProjectStatus:
    def pick(weights: dict[ProjectStatus, float]) -> ProjectStatus:
        return rng.choices(list(weights), weights=list(weights.values()))[0]

    if start > today:
        if (start - today).days > 120:
            return pick(
                {ProjectStatus.IDEA: 5, ProjectStatus.REJECTED: 1.5, ProjectStatus.PREPARATION: 3.5}
            )
        return pick(
            {ProjectStatus.PREPARATION: 5, ProjectStatus.IDEA: 2, ProjectStatus.REJECTED: 1}
        )
    if end < today:
        return pick(
            {
                ProjectStatus.FINISHED: 0.72,
                ProjectStatus.STOPPED: 0.18,
                ProjectStatus.HOLD: 0.03,
                ProjectStatus.PROGRESS: 0.07,
            }
        )
    return pick(
        {
            ProjectStatus.PROGRESS: 0.74,
            ProjectStatus.HOLD: 0.12,
            ProjectStatus.STOPPED: 0.08,
            ProjectStatus.PREPARATION: 0.06,
        }
    )


def _tasks(
    profile: Profile, project: ProjectSpec, today: date, rng: random.Random, slip: str | None = None
) -> list[TaskSpec]:
    planned = tasks_from_template(profile.task_template, project.start, project.end)
    slipping = None
    if project.status in (ProjectStatus.PROGRESS, ProjectStatus.HOLD):
        if slip is not None:
            slipping = slip
        elif rng.random() < 0.35:
            running = [
                t.name
                for t in planned
                if t.planned_start <= today <= t.planned_end and not t.is_milestone
            ]
            slipping = running[0] if running else None
    tasks: list[TaskSpec] = []
    for item in planned:
        revised = None
        if slipping == item.name:
            revised = item.planned_end + timedelta(days=rng.randint(7, 40))
        end = effective_end(item.planned_end, revised)
        if project.status in (ProjectStatus.IDEA, ProjectStatus.REJECTED):
            progress = 0
        elif project.status is ProjectStatus.FINISHED or end < today:
            progress = 100
        elif item.planned_start > today:
            progress = 0
        else:
            length = max((end - item.planned_start).days, 1)
            done = (today - item.planned_start).days / length
            progress = min(95, max(5, round(done * 100 * rng.uniform(0.8, 1.05) / 5) * 5))
        tasks.append(
            TaskSpec(
                item.name,
                item.planned_start,
                item.planned_end,
                revised,
                item.is_milestone,
                progress,
            )
        )
    return tasks


def _details(
    profile: Profile, project: ProjectSpec, others: list[int], people: list[str], rng: random.Random
) -> dict[str, object]:
    tags = ["quick win", "safety", "energy", "sensors, data", "utilities", "quality", "reliability"]
    values: dict[str, object] = {}
    for key, definition in profile.detail_fields.items():
        if rng.random() < 0.25:
            continue
        match definition.type:
            case FieldType.TEXT:
                values[key] = (
                    f"EO-{rng.randint(1000, 9999)}-{project.number}"
                    if "erp" in key
                    else f"{definition.label} {rng.randint(100, 999)}"
                )
            case FieldType.LONG_TEXT:
                values[key] = f"Notes on {definition.label.lower()} for {project.name}."
            case FieldType.NUMBER:
                values[key] = rng.randint(1, 100)
            case FieldType.DATE:
                values[key] = (project.start + timedelta(days=rng.randint(0, 60))).isoformat()
            case FieldType.CHOICE:
                values[key] = rng.choice(definition.choices)
            case FieldType.TAGS:
                values[key] = rng.sample(tags, rng.randint(1, 3))
            case FieldType.PERSON:
                values[key] = PersonRef(rng.choice(people))
            case FieldType.PROJECT:
                if others:
                    values[key] = rng.choice(others)
            case FieldType.YES_NO:
                values[key] = rng.random() < 0.5
            case _:
                pass
    return values


def _quarter_start(day: date) -> date:
    return Quarter.containing(day).start


def _plan_days(
    projects: list[ProjectSpec],
    people: dict[str, PersonSpec],
    overrides: dict[tuple[int, str], Decimal],
    profile: Profile,
    today: date,
) -> None:
    """Fill each project's planned days: raw numbers per member and quarter, scaled down so that
    nobody is planned far beyond their availability, with the pinned cells set last."""
    raw: dict[tuple[str, date], list[tuple[ProjectSpec, Decimal]]] = defaultdict(list)
    for project in projects:
        if project.status is ProjectStatus.REJECTED:
            continue
        for quarter in quarters_overlapping(project.start, project.end):
            rng = _rng("planned", project.number, quarter.label)
            for person in project.members:
                base = 20 if person == project.coordinator else 12
                raw[(person, quarter.start)].append(
                    (project, Decimal(str(base * (0.6 + rng.random() * 0.8))))
                )
    current = Quarter.containing(today).start
    pinned_people = {person for (_, person) in overrides}
    for (person, quarter_start), cells in raw.items():
        if person in pinned_people and quarter_start == current:
            continue  # their current quarter is set by hand, below
        spec = people[person]
        quarter = Quarter.starting(quarter_start)
        year_days = year_availability_days(
            Fraction(spec.availability[quarter.year])
            if quarter.year in spec.availability
            else None,
            WorkPattern(spec.pattern),
            profile.numbers.available_days_per_year,
        )
        capacity = float(quarter_availability_days(year_days, quarter))
        target = capacity * (0.60 + _rng("load", person, quarter.label).random() * 0.45)
        total = float(sum(value for _, value in cells))
        scale = min(1.0, target / total) if total else 1.0
        for project, value in cells:
            project.planned[(person, quarter_start)] = _half(float(value) * scale)
    for (number, person), days in overrides.items():
        project = next(p for p in projects if p.number == number)
        project.planned[(person, current)] = days


def _log_for(
    project: ProjectSpec, today: date, plan_names: list[str], rng: random.Random
) -> list[LogSpec]:
    created = project.created_at
    last = datetime.combine(today - timedelta(days=1), time(17, 0), tzinfo=UTC)

    def between(low: datetime, high: datetime) -> datetime:
        low = max(low, created)  # nothing happens to a project before it exists
        low, high = min(low, last), min(max(high, low), last)
        return low + (high - low) * rng.random() if high > low else low

    who = project.coordinator
    entries = [LogSpec(created, who, lb.LogField.CREATED, None, "Created")]
    path = {
        ProjectStatus.IDEA: [],
        ProjectStatus.REJECTED: [ProjectStatus.REJECTED],
        ProjectStatus.PREPARATION: [ProjectStatus.PREPARATION],
        ProjectStatus.PROGRESS: [ProjectStatus.PREPARATION, ProjectStatus.PROGRESS],
        ProjectStatus.HOLD: [ProjectStatus.PREPARATION, ProjectStatus.PROGRESS, ProjectStatus.HOLD],
        ProjectStatus.STOPPED: [
            ProjectStatus.PREPARATION,
            ProjectStatus.PROGRESS,
            ProjectStatus.STOPPED,
        ],
        ProjectStatus.FINISHED: [
            ProjectStatus.PREPARATION,
            ProjectStatus.PROGRESS,
            ProjectStatus.FINISHED,
        ],
    }[project.status]
    previous = ProjectStatus.IDEA
    moment = created
    start_at = datetime.combine(project.start, time(9, 0), tzinfo=UTC)
    for status in path:
        moment = between(moment + timedelta(days=3), max(moment + timedelta(days=20), start_at))
        entries.append(
            LogSpec(moment, who, lb.LogField.STATUS, STATUS_LABELS[previous], STATUS_LABELS[status])
        )
        previous = status
    if rng.random() < 0.45:
        words = project.name.split(" ")
        old = " ".join(words[: max(2, len(words) - 2)])
        if old != project.name:
            entries.append(
                LogSpec(
                    between(created + timedelta(days=5), created + timedelta(days=40)),
                    who,
                    lb.LogField.TITLE,
                    old,
                    project.name,
                )
            )
    if project.status in (ProjectStatus.PROGRESS, ProjectStatus.HOLD) and rng.random() < 0.4:
        entries.append(
            LogSpec(
                between(last - timedelta(days=120), last - timedelta(days=15)),
                who,
                lb.LogField.END_DATE,
                format_date(project.end - timedelta(days=rng.randint(30, 90))),
                format_date(project.end),
            )
        )
    for member in project.members[1:]:
        if rng.random() < 0.5:
            entries.append(
                LogSpec(between(created, last), who, lb.LogField.PEOPLE, None, f"Added {member}")
            )
    for plan in plan_names:
        entries.append(
            LogSpec(between(created, last), who, lb.LogField.ACTION_PLANS, None, f"Added to {plan}")
        )
    return sorted(entries, key=lambda e: e.at)


def _remarks(
    project: ProjectSpec, today: date, texts: dict[str, list[str]], rng: random.Random
) -> list[RemarkSpec]:
    if project.status is ProjectStatus.IDEA:
        return []
    last = today - timedelta(days=1)
    first = max(project.start, today - timedelta(days=200))
    if project.status is ProjectStatus.REJECTED or first >= last:
        first = max(last - timedelta(days=60), project.created_at.date())
    if first >= last:
        return []
    names = [t.name for t in project.tasks] or ["the work"]
    remarks: list[RemarkSpec] = []
    count = rng.randint(1, 4)
    for index in range(count):
        day = first + timedelta(
            days=int((last - first).days * (index + 0.2 + rng.random() * 0.6) / count)
        )
        running = next(
            (i for i, t in enumerate(project.tasks) if t.planned_end > day), len(names) - 1
        )
        body = rng.choice(texts["remarks"]).format(
            a=names[running], b=names[min(running + 1, len(names) - 1)]
        )
        author = rng.choice(project.members)
        replies: list[ReplySpec] = []
        if rng.random() < 0.45:
            for _ in range(rng.randint(1, 2)):
                replier = rng.choice([m for m in project.members if m != author] or [author])
                reply_day = min(day + timedelta(days=rng.randint(0, 3)), last)
                replies.append(
                    ReplySpec(replier, _at(reply_day, rng), rng.choice(texts["replies"]))
                )
        remarks.append(RemarkSpec(author, _at(day, rng), body, replies))
    return remarks


def build_sample(today: date, profile: Profile) -> Sample:
    """Everything of the sample as plain specs, relative to `today`."""
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    delta = (today - SAMPLE_TODAY).days
    org = _flatten_org(data["org"])
    people = _people(data["people"], today)
    by_name = {p.name: p for p in people}
    names = [p.name for p in people]
    texts = {"remarks": data["remarks"], "replies": data["replies"]}

    projects: list[ProjectSpec] = []
    overrides: dict[tuple[int, str], Decimal] = {}
    featured_slip: dict[int, str] = {}
    for item in data["featured_projects"]:
        number = int(item["number"])
        created_rng = _rng("created", number)
        start, end = _shift(item["start"], delta), _shift(item["end"], delta)
        project = ProjectSpec(
            number=number,
            name=item["name"],
            node=item["node"],
            status=ProjectStatus(item["status"]),
            coordinator=item["coordinator"],
            members=[item["coordinator"], *item["members"]],
            start=start,
            end=end,
            goal=item["goal"],
            priority=Priority(item.get("priority", "medium")),
            created_at=_at(
                min(
                    start - timedelta(days=20 + created_rng.randint(0, 40)),
                    today - timedelta(days=30),
                ),
                created_rng,
            ),
            plans=list(item["plans"]),
        )
        projects.append(project)
        if "slip_task" in item:
            featured_slip[number] = item["slip_task"]
        for person, days in item.get("current_quarter_days", {}).items():
            overrides[(number, person)] = Decimal(str(days))

    # Generated projects: every department gets the same share, objects and actions never repeat.
    actions = data["actions"]
    departments = [o.name for o in org if o.is_department]
    combos: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for department in departments:
        pairs = [(obj, action) for obj in data["objects"][department] for action in actions]
        _rng("combos", department).shuffle(pairs)
        combos[department] = pairs
    sections = {
        d: [o.path for o in org if o.parent and o.path.startswith(d + "/")] for d in departments
    }
    people_of = {d: [p.name for p in people if p.department == d] for d in departments}
    taken = {p.number for p in projects}
    pool = [n for n in range(3200, 4340) if n not in taken]
    numbers = sorted(_rng("numbers").sample(pool, GENERATED_PROJECTS))
    drafts: list[tuple[date, ProjectSpec]] = []
    for index in range(GENERATED_PROJECTS):
        rng = _rng("project", index)
        department = departments[index % len(departments)]
        obj, action = combos[department][index // len(departments)]
        # Mostly around today, some far back (2024) and some far ahead (2028).
        start = today + timedelta(days=int(rng.triangular(-760, 520, -120)))
        end = start + timedelta(days=rng.randint(150, 700))
        coordinator = rng.choice(people_of[department] or names)
        crew = {coordinator}
        wanted = 1 + rng.choices([1, 2, 3, 4, 5], weights=[3, 4, 3, 2, 1])[0]
        while len(crew) < wanted:
            pool_for = people_of[department] if rng.random() < 0.6 else names
            crew.add(rng.choice(pool_for or names))
        members = [coordinator, *sorted(crew - {coordinator})]
        status = _status_for(start, end, today, rng)
        drafts.append(
            (
                start,
                ProjectSpec(
                    number=0,
                    name=action["name"].format(object=obj)[0].upper()
                    + action["name"].format(object=obj)[1:],
                    node=rng.choice(sections[department]),
                    status=status,
                    coordinator=coordinator,
                    members=members,
                    start=start,
                    end=end,
                    goal=action["goal"].format(object=obj),
                    priority=rng.choices(list(Priority), weights=[25, 55, 20])[0],
                    created_at=_at(
                        min(start - timedelta(days=rng.randint(20, 90)), today - timedelta(days=1)),
                        rng,
                    ),
                ),
            )
        )
    for number, (_, project) in zip(numbers, sorted(drafts, key=lambda d: d[0]), strict=True):
        project.number = number
        projects.append(project)

    all_numbers = sorted(p.number for p in projects)
    for project in projects:
        rng = _rng("body", project.number)
        project.tasks = _tasks(profile, project, today, rng, featured_slip.get(project.number))
        older = [n for n in all_numbers if n < project.number]
        project.details = _details(profile, project, older, names, rng)

    # Action plans: the design's projects keep their plans; every plan then draws more projects
    # from the departments it mixes.
    plans: list[PlanSpec] = []
    for position, item in enumerate(data["plans"]):
        chosen = [p.number for p in projects if item["name"] in p.plans]
        rng = _rng("plan", item["name"])
        by_department: dict[str, list[ProjectSpec]] = defaultdict(list)
        for p in projects:
            department = p.node.split("/")[0]
            if (
                department in item["from"]
                and item["name"] not in p.plans
                and p.status is not ProjectStatus.REJECTED
            ):
                by_department[department].append(p)
        for group in by_department.values():
            rng.shuffle(group)
        # One project from each department in turn, so a plan really mixes departments.
        added = 0
        while added < item["extra"] and any(by_department.values()):
            for department in item["from"]:
                if by_department[department] and added < item["extra"]:
                    project = by_department[department].pop()
                    project.plans.append(item["name"])
                    chosen.append(project.number)
                    added += 1
        plans.append(
            PlanSpec(
                item["name"],
                item["owner"],
                item["coordinator"],
                item["hue"],
                item["description"],
                sorted(chosen),
                position,
            )
        )

    _plan_days(projects, by_name, overrides, profile, today)
    for project in projects:
        rng = _rng("history", project.number)
        project.log = _log_for(project, today, project.plans, rng)
        project.remarks = _remarks(project, today, texts, rng)

    # The design's own remarks and logbook for #4102 replace the generated ones.
    for key, items in data["featured_remarks"].items():
        project = next(p for p in projects if p.number == int(key))
        project.remarks = []
        for entry in items:
            day = today - timedelta(days=entry["days_ago"])
            remark = RemarkSpec(
                entry["who"],
                _at(day, _rng("featured", key, entry["id"])),
                entry["text"],
                image=entry.get("image"),
            )
            for number, reply in enumerate(entry["replies"]):
                reply_day = today - timedelta(days=reply["days_ago"])
                remark.replies.append(
                    ReplySpec(
                        reply["who"],
                        _at(reply_day, _rng("reply", key, entry["id"], number)),
                        reply["text"],
                    )
                )
            project.remarks.append(remark)
    for key, items in data["featured_logbook"].items():
        project = next(p for p in projects if p.number == int(key))
        project.log = [
            LogSpec(
                _at(_shift(e["date"], delta), _rng("featured-log", key, i)),
                e["who"],
                lb.LogField(e["field"]),
                e["from"],
                e["to"],
            )
            for i, e in enumerate(items)
        ]
        project.created_at = project.log[0].at

    entries, submissions = _time(projects, people, profile, today)
    return Sample(today, data["root"], org, people, projects, plans, entries, submissions)


# ---------------------------------------------------------------- booked time


def _time(
    projects: list[ProjectSpec], people: list[PersonSpec], profile: Profile, today: date
) -> tuple[list[EntrySpec], list[tuple[str, IsoWeek]]]:
    entries: list[EntrySpec] = []
    submissions: list[tuple[str, IsoWeek]] = []
    other_keys = [c.key for c in profile.categories_of(CategoryKind.OTHER_WORK)]
    off_keys = [c.key for c in profile.categories_of(CategoryKind.TIME_OFF)]
    this_week = IsoWeek.of(today)
    first_week = IsoWeek.of(today - timedelta(days=HISTORY_DAYS))
    mine: dict[str, list[ProjectSpec]] = defaultdict(list)
    for project in projects:
        if project.status in (ProjectStatus.IDEA, ProjectStatus.REJECTED):
            continue
        for member in project.members:
            mine[member].append(project)

    def task_index(project: ProjectSpec, day: date, rng: random.Random) -> int | None:
        if rng.random() < 0.15:
            return None
        for index, task in enumerate(project.tasks):
            if task.planned_start <= day <= effective_end(task.planned_end, task.revised_end):
                return index
        return None

    for person in people:
        spec_pattern = WorkPattern(person.pattern)
        week = first_week
        while week <= this_week:
            rng = _rng("time", person.name, week.label)
            booked_week = 0
            vacation = rng.random() < 0.06 and week < this_week.shifted(-1)
            active = [
                p for p in mine[person.name] if p.start <= week.friday and p.end >= week.monday
            ]
            weights = [
                max(
                    float(p.planned.get((person.name, _quarter_start(week.monday)), Decimal(0))),
                    1.0,
                )
                for p in active
            ]
            for day in week.days:
                target = spec_pattern.target_minutes(day)
                if target == 0 or day >= today:
                    continue
                if person.name == DESIGN_PERSON and week == this_week:
                    continue  # the design's week is set below
                if not vacation and week < this_week.shifted(-8) and rng.random() < 0.03:
                    continue  # a day nobody booked
                if vacation:
                    entries.append(EntrySpec(person.name, day, target, category=off_keys[0]))
                    booked_week += target
                    continue
                if rng.random() < 0.012:
                    entries.append(EntrySpec(person.name, day, target, category=off_keys[-1]))
                    booked_week += target
                    continue
                other: dict[str, int] = {}
                if day.weekday() in (0, 2) and rng.random() < 0.6 and target > STEP:
                    other[other_keys[0]] = STEP
                if rng.random() < 0.05 and target - sum(other.values()) > 2 * STEP:
                    key = other_keys[-1] if len(other_keys) > 1 else other_keys[0]
                    other[key] = other.get(key, 0) + 2 * STEP
                steps = (target - sum(other.values())) // STEP
                if not active and steps:
                    key = other_keys[-1]
                    other[key] = other.get(key, 0) + steps * STEP
                entries.extend(
                    EntrySpec(person.name, day, minutes, category=key)
                    for key, minutes in other.items()
                )
                if not active:
                    booked_week += target
                    continue
                chosen = rng.sample(range(len(active)), min(len(active), rng.randint(1, 3)))
                total = sum(weights[i] for i in chosen)
                shares = {i: int(steps * weights[i] / total) for i in chosen}
                for i in sorted(chosen, key=lambda i: -weights[i])[: steps - sum(shares.values())]:
                    shares[i] += 1
                for i in chosen:
                    if shares[i]:
                        project = active[i]
                        entries.append(
                            EntrySpec(
                                person.name,
                                day,
                                shares[i] * STEP,
                                project.number,
                                task_index(project, day, rng),
                            )
                        )
                booked_week += target
            if booked_week and week < this_week:
                chance = 0.9 if week < this_week.shifted(-1) else 0.6
                if rng.random() < chance:
                    submissions.append((person.name, week))
            week = week.shifted(1)

    # The design's week 41 for Anna Claes: Monday and Tuesday full, nothing after.
    me = next((p for p in people if p.name == DESIGN_PERSON), None)
    if me is not None:
        lines = [
            next(p for p in projects if p.number == number) for number in (4102, 4120, 4231, 4307)
        ]
        for weekday, hours in DESIGN_WEEK.items():
            day = this_week.days[weekday]
            if day >= today:
                continue
            for project, amount in zip(lines, hours[:4], strict=True):
                if amount:
                    entries.append(
                        EntrySpec(
                            me.name, day, amount * STEP, project.number, _running_task(project, day)
                        )
                    )
            entries.append(EntrySpec(me.name, day, hours[4] * STEP, category=other_keys[0]))
    return entries, submissions


def _running_task(project: ProjectSpec, day: date) -> int | None:
    for index, task in enumerate(project.tasks):
        if task.progress < 100 and task.planned_start <= day:
            return index
    return None


# ---------------------------------------------------------------- pictures


def png_image(width: int, height: int, seed: int) -> bytes:
    """A small PNG (bars on a gradient) so the sample's remarks have a real image to show."""
    rng = random.Random(seed)  # noqa: S311
    bars = [(rng.randint(20, 200), rng.randint(40, height - 20)) for _ in range(width // 40)]
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type: none
        for x in range(width):
            height_of_bar = next(
                (h for i, (_, h) in enumerate(bars) if x // 40 == i and x % 40 < 28), 0
            )
            on_bar = height_of_bar and y > height - height_of_bar
            rows += bytes(
                (90 + (x * 40) // width, 100 + (y * 60) // height, 200 if on_bar else 235)
            )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------- loading


def load_sample_data(
    session: Session,
    *,
    today: date,
    profile: Profile,
    uploads_dir: Path | None = None,
    demo_password: str | None = None,
) -> bool:
    """Insert the sample into an empty database; False (nothing done) when it holds projects or
    an organisation beyond its root (a root created at the first sign-in is taken over and
    renamed).

    With `demo_password` every sample person can sign in as `anna.claes` and so on (demos only).
    """
    if session.scalar(select(func.count()).select_from(Project)):
        return False
    existing = list(session.scalars(select(OrgNode)))
    if len(existing) > 1:
        return False
    sample = build_sample(today, profile)

    nodes: dict[str, OrgNode] = {}
    root = existing[0] if existing else OrgNode(position=0, is_department=False, name=sample.root)
    root.name = sample.root
    session.add(root)
    session.flush()
    for spec in sample.org:  # parents come before their children
        parent = nodes[spec.parent] if spec.parent else root
        node = OrgNode(
            name=spec.name,
            parent_id=parent.id,
            position=spec.position,
            is_department=spec.is_department,
        )
        session.add(node)
        session.flush()
        nodes[spec.path] = node

    users: dict[str, User] = {}
    taken = {u for u in session.scalars(select(User.username)) if u is not None}
    demo_hash = hash_password(demo_password) if demo_password else None  # one hash for everyone
    for person in sample.people:
        username = unique_username(person.name, taken) if demo_hash else None
        if username:
            taken.add(username)
        user = User(
            username=username,
            password_hash=demo_hash,
            name=person.name,
            job_title=person.title,
            org_node_id=nodes[person.node].id,
            hue=person.hue,
            work_minutes_mon=person.pattern[0],
            work_minutes_tue=person.pattern[1],
            work_minutes_wed=person.pattern[2],
            work_minutes_thu=person.pattern[3],
            work_minutes_fri=person.pattern[4],
        )
        session.add(user)
        users[person.name] = user
    session.flush()
    session.add_all(
        Availability(user_id=users[p.name].id, year=year, days=days)
        for p in sample.people
        for year, days in p.availability.items()
    )

    projects: dict[int, Project] = {}
    tasks: dict[tuple[int, int], Task] = {}
    for spec in sample.projects:
        project = Project(
            number=spec.number,
            name=spec.name,
            org_node_id=nodes[spec.node].id,
            status=spec.status,
            coordinator_id=users[spec.coordinator].id,
            start_date=spec.start,
            end_date=spec.end,
            goal=spec.goal,
            priority=spec.priority,
            created_at=spec.created_at,
            updated_at=spec.log[-1].at if spec.log else spec.created_at,
        )
        session.add(project)
        projects[spec.number] = project
    session.flush()
    for spec in sample.projects:
        project = projects[spec.number]
        session.add_all(
            ProjectMember(project_id=project.id, user_id=users[member].id)
            for member in spec.members
        )
        for position, task_spec in enumerate(spec.tasks):
            task = Task(
                project_id=project.id,
                position=position,
                name=task_spec.name,
                planned_start=task_spec.planned_start,
                planned_end=task_spec.planned_end,
                revised_end=task_spec.revised_end,
                is_milestone=task_spec.is_milestone,
                progress=task_spec.progress,
            )
            session.add(task)
            tasks[(spec.number, position)] = task
        for key, value in spec.details.items():
            stored = users[value.name].id if isinstance(value, PersonRef) else value
            session.add(
                ProjectDetail(
                    project_id=project.id,
                    field_key=key,
                    value=json.dumps(stored, ensure_ascii=False),
                )
            )
    session.flush()
    session.add_all(
        PlannedDays(
            project_id=projects[spec.number].id,
            user_id=users[person].id,
            quarter_start=quarter_start,
            days=days,
        )
        for spec in sample.projects
        for (person, quarter_start), days in spec.planned.items()
    )
    session.add_all(
        LogEntry(
            project_id=projects[spec.number].id,
            at=entry.at,
            actor_id=users[entry.actor].id,
            field_key=entry.field,
            from_value=entry.from_value,
            to_value=entry.to_value,
        )
        for spec in sample.projects
        for entry in spec.log
    )

    _load_remarks(session, sample, projects, users, uploads_dir)

    plans: dict[str, ActionPlan] = {}
    for spec in sample.plans:
        plan = ActionPlan(
            name=spec.name,
            description=spec.description,
            owner_org_node_id=nodes[spec.owner_node].id,
            coordinator_id=users[spec.coordinator].id,
            hue=spec.hue,
            position=spec.position,
        )
        session.add(plan)
        plans[spec.name] = plan
    session.flush()
    session.add_all(
        ActionPlanProject(plan_id=plans[spec.name].id, project_id=projects[number].id)
        for spec in sample.plans
        for number in spec.projects
    )

    session.execute(
        insert(TimeEntry),
        [
            {
                "user_id": users[e.person].id,
                "work_date": e.day,
                "project_id": projects[e.project].id if e.project is not None else None,
                "task_id": (
                    tasks[(e.project, e.task)].id
                    if e.project is not None and e.task is not None
                    else None
                ),
                "category_key": e.category,
                "minutes": e.minutes,
                "updated_at": datetime.combine(e.day, time(17, 0), tzinfo=UTC),
            }
            for e in sample.entries
        ],
    )
    session.add_all(
        WeekSubmission(
            user_id=users[person].id,
            iso_year=week.year,
            iso_week=week.week,
            submitted_at=datetime.combine(week.sunday, time(18, 0), tzinfo=UTC),
        )
        for person, week in sample.submissions
    )
    session.flush()
    return True


def _load_remarks(
    session: Session,
    sample: Sample,
    projects: dict[int, Project],
    users: dict[str, User],
    uploads_dir: Path | None,
) -> None:
    for spec in sample.projects:
        project = projects[spec.number]
        for index, remark in enumerate(spec.remarks):
            body = remark.body
            attachment: Attachment | None = None
            if remark.image and uploads_dir is not None:
                # A fixed id per picture (the sample is the same every time), like an upload's.
                key = hashlib.sha256(f"sample-{spec.number}-{remark.image}".encode()).hexdigest()[
                    :32
                ]
                uploads_dir.mkdir(parents=True, exist_ok=True)
                data = png_image(480, 270, spec.number + index)
                (uploads_dir / key).write_bytes(data)
                attachment = Attachment(
                    project_id=project.id,
                    uploader_id=users[remark.author].id,
                    filename=f"{remark.image}.png",
                    content_type="image/png",
                    size=len(data),
                    public_id=key,
                    created_at=remark.at,
                )
                session.add(attachment)
                session.flush()
                body = f"{body}\n\n![{remark.image}](api/attachments/{key}/{attachment.filename})"
            post = Post(
                project_id=project.id,
                author_id=users[remark.author].id,
                body_md=body,
                created_at=remark.at,
            )
            session.add(post)
            session.flush()
            if attachment is not None:
                attachment.post_id = post.id
            session.add_all(
                Post(
                    project_id=project.id,
                    parent_id=post.id,
                    author_id=users[reply.author].id,
                    body_md=reply.body,
                    created_at=reply.at,
                )
                for reply in remark.replies
            )
