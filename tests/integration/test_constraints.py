"""The database itself refuses what the rules forbid, whatever the application does."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from momato.db.models import (
    Attachment,
    OrgNode,
    Post,
    Project,
    ProjectMember,
    Task,
    TimeEntry,
    User,
)
from tests.factories import book, make_org, make_project, make_task, make_user, plan

DAY = date(2026, 10, 8)
Q4 = date(2026, 10, 1)


@pytest.fixture
def world(session: Session) -> dict[str, object]:
    org = make_org(session)
    anna = make_user(session, "Anna Claes", org)
    bram = make_user(session, "Bram Peeters", org)
    one = make_project(session, number=4102, org=org, coordinator=anna)
    two = make_project(session, number=4103, org=org, coordinator=anna, members=(bram,))
    return {
        "org": org,
        "anna": anna,
        "bram": bram,
        "one": one,
        "two": two,
        "one_task": make_task(session, one),
        "two_task": make_task(session, two),
    }


def refuses() -> pytest.RaisesExc[IntegrityError]:
    """The block must be refused by the database with an IntegrityError."""
    return pytest.raises(IntegrityError)


# ---------------------------------------------------------------- planned days


def test_a_second_planned_days_cell_for_the_same_project_person_and_quarter_is_refused(
    session: Session, world: dict[str, object]
) -> None:
    project, anna = world["one"], world["anna"]
    assert isinstance(project, Project)
    assert isinstance(anna, User)
    plan(session, project, anna, Q4, "12")
    with refuses():
        plan(session, project, anna, Q4, "5")


def test_the_same_person_can_have_planned_days_in_other_quarters_and_projects(
    session: Session, world: dict[str, object]
) -> None:
    one, two, anna = world["one"], world["two"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(two, Project)
    assert isinstance(anna, User)
    plan(session, one, anna, Q4)
    plan(session, one, anna, date(2027, 1, 1))
    plan(session, two, anna, Q4)  # no error


def test_planned_days_exist_only_for_members(session: Session, world: dict[str, object]) -> None:
    one, bram = world["one"], world["bram"]
    assert isinstance(one, Project)
    assert isinstance(bram, User)  # Bram is a member of project two, not of one
    with refuses():
        plan(session, one, bram, Q4)


def test_planned_days_cannot_be_negative(session: Session, world: dict[str, object]) -> None:
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    with refuses():
        plan(session, one, anna, Q4, "-0.5")


def test_a_member_with_planned_days_cannot_be_removed_before_their_days(
    session: Session, world: dict[str, object]
) -> None:
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    plan(session, one, anna, Q4)
    member = session.get(ProjectMember, (one.id, anna.id))
    assert member is not None
    with refuses():
        session.delete(member)
        session.flush()


# ---------------------------------------------------------------- time entries


def test_a_time_entry_whose_task_belongs_to_another_project_is_refused(
    session: Session, world: dict[str, object]
) -> None:
    one, two_task, anna = world["one"], world["two_task"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(two_task, Task)
    assert isinstance(anna, User)
    with refuses():
        book(session, anna, DAY, project=one, task=two_task)


def test_a_time_entry_on_its_projects_task_is_accepted(
    session: Session, world: dict[str, object]
) -> None:
    one, one_task, anna = world["one"], world["one_task"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(one_task, Task)
    assert isinstance(anna, User)
    assert book(session, anna, DAY, 120, project=one, task=one_task).id is not None


def test_a_time_entry_with_both_project_and_category_is_refused(
    session: Session, world: dict[str, object]
) -> None:
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    with refuses():
        book(session, anna, DAY, project=one, category="meetings")


def test_a_time_entry_with_neither_project_nor_category_is_refused(
    session: Session, world: dict[str, object]
) -> None:
    anna = world["anna"]
    assert isinstance(anna, User)
    with refuses():
        book(session, anna, DAY)


def test_a_category_entry_cannot_carry_a_task(session: Session, world: dict[str, object]) -> None:
    one_task, anna = world["one_task"], world["anna"]
    assert isinstance(one_task, Task)
    assert isinstance(anna, User)
    with refuses():
        book(session, anna, DAY, category="meetings", task=one_task)


def test_negative_minutes_are_refused(session: Session, world: dict[str, object]) -> None:
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    with refuses():
        book(session, anna, DAY, -60, project=one)


def test_a_duplicate_general_entry_is_refused(session: Session, world: dict[str, object]) -> None:
    """General has no task, so a plain unique index would let NULL tasks repeat."""
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    book(session, anna, DAY, project=one)
    with refuses():
        book(session, anna, DAY, project=one)


def test_a_duplicate_task_entry_is_refused(session: Session, world: dict[str, object]) -> None:
    one, one_task, anna = world["one"], world["one_task"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(one_task, Task)
    assert isinstance(anna, User)
    book(session, anna, DAY, project=one, task=one_task)
    with refuses():
        book(session, anna, DAY, project=one, task=one_task)


def test_a_duplicate_category_entry_is_refused(session: Session, world: dict[str, object]) -> None:
    anna = world["anna"]
    assert isinstance(anna, User)
    book(session, anna, DAY, category="vacation")
    with refuses():
        book(session, anna, DAY, category="vacation")


def test_distinct_cells_of_one_day_are_all_accepted(
    session: Session, world: dict[str, object]
) -> None:
    one, two, one_task, anna, bram = (
        world["one"],
        world["two"],
        world["one_task"],
        world["anna"],
        world["bram"],
    )
    assert isinstance(one, Project)
    assert isinstance(two, Project)
    assert isinstance(one_task, Task)
    assert isinstance(anna, User)
    assert isinstance(bram, User)
    book(session, anna, DAY, project=one)  # General
    book(session, anna, DAY, project=one, task=one_task)  # a task of the same project
    book(session, anna, DAY, project=two)  # General of another project
    book(session, anna, DAY, category="meetings")
    book(session, anna, DAY, category="vacation")
    book(session, anna, date(2026, 10, 9), project=one)  # another day
    book(session, bram, DAY, project=one)  # another person
    assert session.query(TimeEntry).count() == 7


def test_a_task_with_booked_time_cannot_be_deleted(
    session: Session, world: dict[str, object]
) -> None:
    """Deleting a task first moves its hours to General (D-032); the database insists."""
    one, one_task, anna = world["one"], world["one_task"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(one_task, Task)
    assert isinstance(anna, User)
    book(session, anna, DAY, project=one, task=one_task)
    with refuses():
        session.delete(one_task)
        session.flush()


def test_a_project_with_booked_time_cannot_be_deleted(
    session: Session, world: dict[str, object]
) -> None:
    one, anna = world["one"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(anna, User)
    book(session, anna, DAY, project=one)
    session.query(ProjectMember).filter(ProjectMember.project_id == one.id).delete()
    session.query(Task).filter(Task.project_id == one.id).delete()
    session.flush()  # only the booked time still refers to the project
    with refuses():
        session.delete(one)
        session.flush()


# ---------------------------------------------------------------- projects, tasks, posts


def test_a_duplicate_project_number_is_refused(session: Session, world: dict[str, object]) -> None:
    org, anna = world["org"], world["anna"]
    assert isinstance(org, OrgNode)
    assert isinstance(anna, User)
    with refuses():
        make_project(session, number=4102, org=org, coordinator=anna)


def test_a_project_cannot_end_before_it_starts(session: Session, world: dict[str, object]) -> None:
    org, anna = world["org"], world["anna"]
    assert isinstance(org, OrgNode)
    assert isinstance(anna, User)
    with refuses():
        make_project(
            session,
            number=5000,
            org=org,
            coordinator=anna,
            start=date(2026, 5, 1),
            end=date(2026, 4, 1),
        )


@pytest.mark.parametrize(
    "values",
    [
        {"progress": 101},
        {"progress": -1},
        {"planned_end": date(2025, 12, 31)},  # before the start
        {"revised_end": date(2026, 12, 31)},  # not after the planned end
    ],
    ids=["progress over 100", "progress below 0", "end before start", "revised not after end"],
)
def test_a_task_must_keep_its_dates_and_progress_in_range(
    session: Session, world: dict[str, object], values: dict[str, object]
) -> None:
    one = world["one"]
    assert isinstance(one, Project)
    columns: dict[str, object] = {
        "project_id": one.id,
        "name": "Bad",
        "planned_start": date(2026, 1, 1),
        "planned_end": date(2026, 12, 31),
        **values,
    }
    task = Task(**columns)
    session.add(task)
    with refuses():
        session.flush()


def test_a_reply_must_belong_to_the_same_project_as_its_remark(
    session: Session, world: dict[str, object]
) -> None:
    one, two, anna = world["one"], world["two"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(two, Project)
    assert isinstance(anna, User)
    remark = Post(project_id=one.id, author_id=anna.id, body_md="Hello")
    session.add(remark)
    session.flush()
    session.add(Post(project_id=one.id, parent_id=remark.id, author_id=anna.id, body_md="Reply"))
    session.flush()  # the same project: fine
    session.add(Post(project_id=two.id, parent_id=remark.id, author_id=anna.id, body_md="Wrong"))
    with refuses():
        session.flush()


def test_an_image_must_belong_to_a_remark_of_its_own_project(
    session: Session, world: dict[str, object]
) -> None:
    one, two, anna = world["one"], world["two"], world["anna"]
    assert isinstance(one, Project)
    assert isinstance(two, Project)
    assert isinstance(anna, User)
    remark = Post(project_id=one.id, author_id=anna.id, body_md="Hello")
    session.add(remark)
    session.flush()
    draft = Attachment(  # a draft has no post yet
        project_id=two.id,
        uploader_id=anna.id,
        filename="a.png",
        content_type="image/png",
        size=10,
        public_id="k1",
        created_at=datetime.now(UTC),
    )
    session.add(draft)
    session.flush()
    wrong = Attachment(
        project_id=two.id,
        post_id=remark.id,
        uploader_id=anna.id,
        filename="b.png",
        content_type="image/png",
        size=10,
        public_id="k2",
        created_at=datetime.now(UTC),
    )
    session.add(wrong)
    with refuses():
        session.flush()
