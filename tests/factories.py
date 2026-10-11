"""Small builders of database rows for tests: each adds to the session and flushes."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from momato.db.models import (
    OrgNode,
    PlannedDays,
    Project,
    ProjectMember,
    Task,
    TimeEntry,
    User,
)
from momato.domain.projects import ProjectStatus
from momato.identity.passwords import hash_password


def make_org(
    session: Session,
    name: str = "Brightwater",
    parent: OrgNode | None = None,
    *,
    department: bool = False,
) -> OrgNode:
    node = OrgNode(name=name, parent_id=parent.id if parent else None, is_department=department)
    session.add(node)
    session.flush()
    return node


def make_user(
    session: Session,
    name: str = "Anna Claes",
    org: OrgNode | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
) -> User:
    user = User(
        name=name,
        org_node_id=org.id if org else None,
        username=username,
        password_hash=hash_password(password) if password else None,
    )
    session.add(user)
    session.flush()
    return user


def make_project(
    session: Session,
    *,
    number: int = 4102,
    org: OrgNode,
    coordinator: User,
    status: ProjectStatus = ProjectStatus.PROGRESS,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 12, 31),
    members: tuple[User, ...] = (),
) -> Project:
    project = Project(
        number=number,
        name=f"Project {number}",
        org_node_id=org.id,
        coordinator_id=coordinator.id,
        status=status,
        start_date=start,
        end_date=end,
    )
    session.add(project)
    session.flush()
    for member in {coordinator.id: coordinator, **{m.id: m for m in members}}.values():
        session.add(ProjectMember(project_id=project.id, user_id=member.id))
    session.flush()
    return project


def make_task(session: Session, project: Project, name: str = "Study") -> Task:
    task = Task(
        project_id=project.id,
        name=name,
        planned_start=project.start_date,
        planned_end=project.end_date,
    )
    session.add(task)
    session.flush()
    return task


def book(
    session: Session,
    user: User,
    day: date,
    minutes: int = 60,
    *,
    project: Project | None = None,
    task: Task | None = None,
    category: str | None = None,
) -> TimeEntry:
    entry = TimeEntry(
        user_id=user.id,
        work_date=day,
        project_id=project.id if project else None,
        task_id=task.id if task else None,
        category_key=category,
        minutes=minutes,
    )
    session.add(entry)
    session.flush()
    return entry


def plan(
    session: Session, project: Project, user: User, quarter_start: date, days: str = "10"
) -> PlannedDays:
    cell = PlannedDays(
        project_id=project.id,
        user_id=user.id,
        quarter_start=quarter_start,
        days=Decimal(days),
    )
    session.add(cell)
    session.flush()
    return cell
