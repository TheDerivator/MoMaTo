"""The sample data loads completely, matches its own source, and looks like a used system. [D-037]

Expected numbers come from the JSON and the generator's specs (the `sample` fixture), never from
the database under test.
"""

import json
from collections import Counter
from collections.abc import Iterator
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from momato.config import Settings
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
    UserKind,
    WeekSubmission,
)
from momato.db.session import Database
from momato.domain.calendar import IsoWeek, Quarter
from momato.domain.capacity import WorkPattern
from momato.domain.fields import FieldType, Profile, validate_value
from momato.domain.formatting import round_half_up
from momato.domain.logbook import LogField
from momato.domain.planning import other_work_planned_minutes, weekly_planned_hours
from momato.domain.projects import ProjectStatus
from momato.services.profile import load_profile
from momato.services.sample_data import (
    SAMPLE_FILE,
    SAMPLE_TODAY,
    Sample,
    build_sample,
    load_sample_data,
)

PROFILE = load_profile("default")


@pytest.fixture
def session(sample_database: Database) -> Iterator[Session]:
    with sample_database.new_session() as read_session:
        yield read_session


def ancestors_to_top(nodes: dict[int, OrgNode], node_id: int) -> str:
    """The name of the top-level department a node belongs to."""
    node = nodes[node_id]
    while node.parent_id is not None and nodes[node.parent_id].parent_id is not None:
        node = nodes[node.parent_id]
    return node.name


# ---------------------------------------------------------------- size and shape


def test_the_sample_is_big_enough_to_look_used(sample: Sample) -> None:
    departments = [o for o in sample.org if o.is_department]
    sections = [o for o in sample.org if not o.is_department]
    assert len(departments) >= 10
    assert 28 <= len(sections) <= 36
    assert len(sample.people) >= 60
    assert len(sample.projects) >= 180
    assert len(sample.plans) >= 10
    statuses = {p.status for p in sample.projects}
    assert statuses == set(ProjectStatus)  # every status, Stopped included
    years = {p.start.year for p in sample.projects} | {p.end.year for p in sample.projects}
    assert {2024, 2025, 2026, 2027, 2028} <= years


def test_the_json_holds_the_taskboard_organisation_and_people() -> None:
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    top = {item["name"]: item["children"] for item in data["org"]}
    assert top["STL"] == ["Quality", "Process", "Maintenance"]
    assert top["R&D"][0] == "Coatings"
    names = {p["name"] for p in data["people"]}
    assert {
        "Anna Claes",
        "Bram Peeters",
        "Chloé Martens",
        "Dries Wouters",
        "Eva Janssens",
        "Filip Maes",
    } <= names
    assert len(names) == len(data["people"])  # no duplicates


# ---------------------------------------------------------------- the database matches its source


def test_counts_in_the_database_equal_the_specs(session: Session, sample: Sample) -> None:
    def count(model: type) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    assert count(OrgNode) == len(sample.org) + 1  # and the root
    people = session.scalar(
        select(func.count()).select_from(User).where(User.kind == UserKind.PERSON)
    )
    assert people == len(sample.people)  # admin and anonymous are system accounts, not people
    assert count(User) == len(sample.people) + 2
    assert count(Project) == len(sample.projects)
    assert count(Task) == sum(len(p.tasks) for p in sample.projects)
    assert count(ProjectMember) == sum(len(p.members) for p in sample.projects)
    assert count(PlannedDays) == sum(len(p.planned) for p in sample.projects)
    assert count(LogEntry) == sum(len(p.log) for p in sample.projects)
    posts = sum(len(r.replies) + 1 for p in sample.projects for r in p.remarks)
    assert count(Post) == posts
    assert count(ActionPlan) == len(sample.plans)
    assert count(ActionPlanProject) == sum(len(p.projects) for p in sample.plans)
    assert count(TimeEntry) == len(sample.entries)
    assert count(WeekSubmission) == len(sample.submissions)
    assert count(Availability) == sum(len(p.availability) for p in sample.people)
    assert count(ProjectDetail) == sum(len(p.details) for p in sample.projects)


def test_projects_per_department_status_and_person_equal_the_specs(
    session: Session, sample: Sample
) -> None:
    nodes = {n.id: n for n in session.scalars(select(OrgNode))}
    in_db = Counter(
        ancestors_to_top(nodes, p.org_node_id) for p in session.scalars(select(Project))
    )
    assert in_db == Counter(p.node.split("/")[0] for p in sample.projects)

    by_status = dict(
        session.execute(select(Project.status, func.count()).group_by(Project.status)).all()
    )
    assert {s.value: n for s, n in by_status.items()} == Counter(
        p.status.value for p in sample.projects
    )

    names = {u.id: u.name for u in session.scalars(select(User))}
    members = Counter(
        names[user_id] for (user_id,) in session.execute(select(ProjectMember.user_id)).all()
    )
    assert members == Counter(m for p in sample.projects for m in p.members)

    booked: Counter[str] = Counter()
    for user_id, minutes in session.execute(select(TimeEntry.user_id, TimeEntry.minutes)):
        booked[names[user_id]] += minutes
    expected: Counter[str] = Counter()
    for entry in sample.entries:
        expected[entry.person] += entry.minutes
    assert booked == expected


def test_loading_twice_changes_nothing(
    sample_database: Database, sample_settings: Settings
) -> None:
    with sample_database.session(write=True) as session:
        before = session.scalar(select(func.count()).select_from(TimeEntry))
        again = load_sample_data(
            session, today=SAMPLE_TODAY, profile=PROFILE, uploads_dir=sample_settings.uploads_dir
        )
        after = session.scalar(select(func.count()).select_from(TimeEntry))
        projects = session.scalar(select(func.count()).select_from(Project))
    assert again is False
    assert before == after
    assert projects == 200


def test_the_sample_is_the_same_every_time() -> None:
    first = build_sample(SAMPLE_TODAY, PROFILE)
    second = build_sample(SAMPLE_TODAY, PROFILE)
    assert [p.name for p in first.projects] == [p.name for p in second.projects]
    assert first.entries == second.entries
    assert [p.planned for p in first.projects] == [p.planned for p in second.projects]


# ---------------------------------------------------------------- the design's own data


def test_the_designs_projects_are_there_with_their_numbers_and_dates(session: Session) -> None:
    project = session.scalar(select(Project).where(Project.number == 4102))
    assert project is not None
    assert project.name == "Sensor retrofit on conveyor 4"
    assert project.status is ProjectStatus.PROGRESS
    assert (project.start_date, project.end_date) == (date(2025, 11, 3), date(2027, 3, 31))
    assert project.goal.startswith("Replace the end-of-life sensors on conveyor 4")
    coordinator = session.get(User, project.coordinator_id)
    assert coordinator is not None
    assert coordinator.name == "Tomás Rivera"
    numbers = set(session.scalars(select(Project.number)))
    assert {
        4102,
        3876,
        4231,
        3910,
        3655,
        4307,
        3788,
        3502,
        4015,
        4288,
        3590,
        4340,
        4120,
        4066,
        4199,
        3961,
    } <= numbers
    assert max(numbers) == 4340  # a new project becomes 4341


def test_project_4102_has_the_designs_remarks_logbook_and_image(
    session: Session, sample_settings: Settings
) -> None:
    project = session.scalar(select(Project).where(Project.number == 4102))
    assert project is not None
    remarks = list(
        session.scalars(
            select(Post)
            .where(Post.project_id == project.id, Post.parent_id.is_(None))
            .order_by(Post.created_at.desc())
        )
    )
    assert [p.body_md.split("\n")[0] for p in remarks][1:] == [
        "Installation on sections 1 to 3 finished during the planned stop. Section 4 moves to "
        "the October stop because of a clash with a cable tray.",
        "Supplier confirmed delivery for week 34. Budget still on track.",
        "Done:",
    ]
    assert remarks[0].body_md.startswith(
        "Done:\n- First full week of live data from the 12 new sensors"
    )
    replies = list(session.scalars(select(Post).where(Post.parent_id == remarks[0].id)))
    assert len(replies) == 2
    image = session.scalar(select(Attachment).where(Attachment.project_id == project.id))
    assert image is not None
    assert image.post_id == remarks[0].id
    assert (sample_settings.uploads_dir / image.public_id).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert f"api/attachments/{image.public_id}/{image.filename}" in remarks[0].body_md

    log = list(
        session.scalars(
            select(LogEntry).where(LogEntry.project_id == project.id).order_by(LogEntry.at)
        )
    )
    assert [e.field_key for e in log] == [
        LogField.CREATED,
        LogField.STATUS,
        LogField.PEOPLE,
        LogField.COORDINATOR,
        LogField.TITLE,
        LogField.STATUS,
        LogField.END_DATE,
    ]
    assert (log[-1].from_value, log[-1].to_value) == ("29 Jan 2027", "31 Mar 2027")


def test_anna_claes_has_the_designs_week_41(session: Session) -> None:
    """Four project lines planned at 14, 10, 8 and 4 h plus Other work at 4 h; Monday and Tuesday
    full (16 h). Planned hours come from her planned days through the domain rules."""
    anna = session.scalar(select(User).where(User.name == "Anna Claes"))
    assert anna is not None
    pattern = WorkPattern(
        (
            anna.work_minutes_mon,
            anna.work_minutes_tue,
            anna.work_minutes_wed,
            anna.work_minutes_thu,
            anna.work_minutes_fri,
        )
    )
    week = IsoWeek.of(SAMPLE_TODAY)
    assert week.label == "2026-W41"

    planned_by_project: dict[int, dict[Quarter, Fraction]] = {}
    rows = session.execute(
        select(Project.number, PlannedDays.quarter_start, PlannedDays.days)
        .join(PlannedDays, PlannedDays.project_id == Project.id)
        .where(PlannedDays.user_id == anna.id)
    )
    for number, quarter_start, days in rows:
        planned_by_project.setdefault(number, {})[Quarter.starting(quarter_start)] = Fraction(days)
    hours = {
        number: round_half_up(weekly_planned_hours(planned, pattern, week, 8))
        for number, planned in planned_by_project.items()
    }
    assert {n: h for n, h in hours.items() if h} == {4102: 14, 4120: 10, 4231: 8, 4307: 4}
    assert other_work_planned_minutes(pattern, PROFILE.numbers.other_work_share) == 4 * 60

    entries = session.execute(
        select(
            TimeEntry.work_date, TimeEntry.project_id, TimeEntry.category_key, TimeEntry.minutes
        ).where(TimeEntry.user_id == anna.id, TimeEntry.work_date >= week.monday)
    ).all()
    numbers = dict(session.execute(select(Project.id, Project.number)).all())
    per_line: dict[tuple[date, str], int] = {}
    for day, project_id, category, minutes in entries:
        line = f"#{numbers[project_id]}" if project_id else str(category)
        per_line[(day, line)] = per_line.get((day, line), 0) + minutes
    monday, tuesday = week.days[0], week.days[1]
    assert per_line == {
        (monday, "#4102"): 180,
        (tuesday, "#4102"): 240,
        (monday, "#4120"): 120,
        (tuesday, "#4120"): 120,
        (monday, "#4231"): 120,
        (tuesday, "#4231"): 60,
        (monday, "meetings"): 60,
        (tuesday, "meetings"): 60,
    }
    assert sum(per_line.values()) == 16 * 60
    assert not session.scalars(
        select(WeekSubmission).where(
            WeekSubmission.user_id == anna.id,
            WeekSubmission.iso_year == 2026,
            WeekSubmission.iso_week == 41,
        )
    ).all()


def test_eva_janssens_works_four_days_and_anna_has_an_availability_override(
    session: Session,
) -> None:
    eva = session.scalar(select(User).where(User.name == "Eva Janssens"))
    assert eva is not None
    assert (
        WorkPattern(
            (
                eva.work_minutes_mon,
                eva.work_minutes_tue,
                eva.work_minutes_wed,
                eva.work_minutes_thu,
                eva.work_minutes_fri,
            )
        ).weekly_target_minutes
        == 4 * 480
    )
    anna = session.scalar(select(User).where(User.name == "Anna Claes"))
    assert anna is not None
    days = session.scalar(
        select(Availability.days).where(Availability.user_id == anna.id, Availability.year == 2026)
    )
    assert days is not None
    assert Fraction(days) == 245


# ---------------------------------------------------------------- invariants of the data


def test_every_project_is_consistent(sample: Sample) -> None:
    profile_tasks = [t.name for t in PROFILE.task_template]
    numbers = [p.number for p in sample.projects]
    assert len(set(numbers)) == len(numbers)
    for project in sample.projects:
        assert project.start <= project.end
        assert 2 <= len(project.members) <= 6, project.number
        assert project.members[0] == project.coordinator
        assert len(set(project.members)) == len(project.members)
        assert [t.name for t in project.tasks] == profile_tasks
        for task in project.tasks:
            assert task.planned_start <= task.planned_end
            assert 0 <= task.progress <= 100
            if task.revised_end is not None:
                assert task.revised_end > task.planned_end
        if project.status is ProjectStatus.FINISHED:
            assert all(t.progress == 100 for t in project.tasks)
        if project.status in (ProjectStatus.IDEA, ProjectStatus.REJECTED):
            assert all(t.progress == 0 for t in project.tasks)
        for (person, quarter_start), days in project.planned.items():
            assert person in project.members
            assert Quarter.containing(quarter_start).start == quarter_start
            assert days > 0
            assert days * 2 == int(days * 2)  # steps of 0.5
        assert project.log[0].field is LogField.CREATED
        assert project.log == sorted(project.log, key=lambda e: e.at)
        assert all(e.at.date() < SAMPLE_TODAY for e in project.log)


def test_booked_time_follows_the_rules_of_the_timesheet(sample: Sample) -> None:
    patterns = {p.name: WorkPattern(p.pattern) for p in sample.people}
    per_day: Counter[tuple[str, date]] = Counter()
    seen: set[tuple[str, date, int | None, int | None, str | None]] = set()
    oldest = SAMPLE_TODAY - timedelta(days=760)
    for entry in sample.entries:
        assert entry.minutes > 0
        assert entry.minutes % 60 == 0  # the profile's step
        assert oldest <= entry.day < SAMPLE_TODAY  # two years, up to yesterday
        assert patterns[entry.person].is_working_day(entry.day), (entry.person, entry.day)
        assert (entry.project is None) != (entry.category is None)
        cell = (entry.person, entry.day, entry.project, entry.task, entry.category)
        assert cell not in seen
        seen.add(cell)
        per_day[(entry.person, entry.day)] += entry.minutes
    assert max(per_day.values()) <= PROFILE.numbers.day_cap_minutes
    categories = {c.key for c in PROFILE.categories}
    assert {e.category for e in sample.entries if e.category} <= categories
    assert {"vacation", "meetings"} <= {e.category for e in sample.entries}
    members = {(p.number, m) for p in sample.projects for m in p.members}
    assert all((e.project, e.person) in members for e in sample.entries if e.project is not None)


def test_submitted_weeks_are_past_weeks_with_booked_time(sample: Sample) -> None:
    this_week = IsoWeek.of(SAMPLE_TODAY)
    booked = {(e.person, IsoWeek.of(e.day)) for e in sample.entries}
    assert sample.submissions
    assert len(set(sample.submissions)) == len(sample.submissions)
    for person, week in sample.submissions:
        assert week < this_week
        assert (person, week) in booked


def test_action_plans_mix_departments_and_have_different_owners(sample: Sample) -> None:
    by_number = {p.number: p for p in sample.projects}
    owners = {p.owner_node for p in sample.plans}
    assert len(owners) >= 8
    for plan in sample.plans:
        departments = {by_number[n].node.split("/")[0] for n in plan.projects}
        assert len(departments) >= 3, plan.name
        assert len(plan.projects) >= 5
    assert {p.name for p in sample.plans} >= {
        "Digital plant",
        "Energy & resources 2027",
        "Safe workplace",
        "Line performance 2026",
    }


def test_detail_values_fit_the_profile(session: Session) -> None:
    details = PROFILE.detail_fields
    users = set(session.scalars(select(User.id)))
    projects = set(session.scalars(select(Project.number)))
    seen: Counter[str] = Counter()
    for key, value in session.execute(select(ProjectDetail.field_key, ProjectDetail.value)):
        assert key in details
        parsed = json.loads(value)
        assert validate_value(details[key], parsed) == parsed
        if details[key].type is FieldType.PERSON:
            assert parsed in users
        if details[key].type is FieldType.PROJECT:
            assert parsed in projects
        seen[key] += 1
    assert set(seen) == set(details)  # every field is used by some project


# ---------------------------------------------------------------- relative to today (D-027)


@pytest.mark.parametrize(
    "today",
    [
        date(2026, 10, 8),
        date(2026, 10, 12),
        date(2026, 10, 10),
        date(2027, 1, 4),
        date(2028, 2, 29),
    ],
    ids=lambda d: d.strftime("%a %Y-%m-%d"),
)
def test_the_sample_moves_with_today(today: date) -> None:
    moved = build_sample(today, PROFILE)
    patterns = {p.name: WorkPattern(p.pattern) for p in moved.people}
    assert all(e.day < today for e in moved.entries)
    assert all(patterns[e.person].is_working_day(e.day) for e in moved.entries)
    by_number = {p.number: p for p in moved.projects}
    delta = (today - SAMPLE_TODAY).days
    assert by_number[4102].start == date(2025, 11, 3) + timedelta(days=delta)
    assert by_number[4102].end == date(2027, 3, 31) + timedelta(days=delta)
    assert max(e.day for e in moved.entries) >= today - timedelta(days=4)
    week = IsoWeek.of(today)
    anna_this_week = [
        e for e in moved.entries if e.person == "Anna Claes" and IsoWeek.of(e.day) == week
    ]
    expected_days = [d for d in week.days[:2] if d < today]
    assert sorted({e.day for e in anna_this_week}) == expected_days


def test_a_profile_variant_with_one_category_per_kind_still_builds(tmp_path: Path) -> None:
    (tmp_path / "small.toml").write_text(
        "\n".join(
            [
                "[[categories]]",
                'key = "work"',
                'label = "Work"',
                'kind = "other_work"',
                "[[categories]]",
                'key = "off"',
                'label = "Off"',
                'kind = "time_off"',
                "[[cards]]",
                'key = "c"',
                'title = "C"',
                "[[cards.fields]]",
                'key = "cost"',
                'label = "Cost"',
                'type = "number"',
                "[[task_template]]",
                'name = "Only"',
                "start = 0.0",
                "end = 1.0",
            ]
        ),
        encoding="utf-8",
    )
    profile: Profile = load_profile("small", tmp_path)
    built = build_sample(SAMPLE_TODAY, profile)
    assert {e.category for e in built.entries if e.category} <= {"work", "off"}
    assert all(len(p.tasks) == 1 for p in built.projects)
    cells = Counter((e.person, e.day, e.project, e.task, e.category) for e in built.entries)
    assert max(cells.values()) == 1


# ---------------------------------------------------------------- a root created at first sign-in


def test_the_sample_takes_over_a_root_created_at_first_sign_in(
    database: Database, settings: Settings
) -> None:
    """[ADM-1] An administrator who named the organisation before seeding keeps one root."""
    with database.session(write=True) as session:
        root = OrgNode(name="Acme Corp", position=0, is_department=False)
        session.add(root)
        session.flush()
        root_id = root.id
        loaded = load_sample_data(
            session, today=SAMPLE_TODAY, profile=PROFILE, uploads_dir=settings.uploads_dir
        )
    assert loaded is True
    with database.new_session() as read_session:
        roots = list(read_session.scalars(select(OrgNode).where(OrgNode.parent_id.is_(None))))
        assert [r.id for r in roots] == [root_id]
        assert roots[0].name == build_sample(SAMPLE_TODAY, PROFILE).root
        assert read_session.scalar(select(func.count()).select_from(Project)) == 200


def test_the_sample_is_not_loaded_into_an_organisation_that_has_branches(
    database: Database, settings: Settings
) -> None:
    with database.session(write=True) as session:
        root = OrgNode(name="Acme Corp", position=0, is_department=False)
        session.add(root)
        session.flush()
        session.add(OrgNode(name="Plant", parent_id=root.id, position=0, is_department=True))
        session.flush()
        loaded = load_sample_data(
            session, today=SAMPLE_TODAY, profile=PROFILE, uploads_dir=settings.uploads_dir
        )
        assert loaded is False
        assert session.scalar(select(func.count()).select_from(Project)) == 0
        assert session.scalar(select(func.count()).select_from(OrgNode)) == 2
