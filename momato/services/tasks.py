"""Tasks (the gantt rows of a project): list, create, edit, move, delete (PG-4, PG-5, D-032)."""

from datetime import date
from typing import cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.orm import Session

from momato.db.models import Project, Task, TimeEntry
from momato.domain.errors import NotFoundError, RuleViolationError, StaleVersionError
from momato.domain.tasks import (
    effective_end,
    is_slipped,
    status_text,
    task_status,
    validate_task_dates,
)
from momato.identity.principal import Principal
from momato.schemas.projects import TaskCreate, TaskDeleted, TaskOut, TaskUpdate
from momato.services.projects_access import ProjectAccess


def task_out(task: Task, today: date, booked_minutes: int = 0) -> TaskOut:
    status = task_status(task.progress, task.planned_start, today)
    return TaskOut(
        id=task.id,
        position=task.position,
        name=task.name,
        planned_start=task.planned_start,
        planned_end=task.planned_end,
        revised_end=task.revised_end,
        is_milestone=task.is_milestone,
        progress=task.progress,
        status=status.value,
        status_text=status_text(status, task.progress),
        slipped=is_slipped(task.planned_end, task.revised_end),
        effective_end=effective_end(task.planned_end, task.revised_end),
        booked_minutes=booked_minutes,
        version=task.version,
    )


def booked_by_task(session: Session, project_id: int) -> dict[int, int]:
    rows = session.execute(
        select(TimeEntry.task_id, func.sum(TimeEntry.minutes))
        .where(TimeEntry.project_id == project_id, TimeEntry.task_id.is_not(None))
        .group_by(TimeEntry.task_id)
    )
    return {task_id: int(minutes) for task_id, minutes in rows if task_id is not None}


def tasks_of(session: Session, project_id: int, today: date) -> list[TaskOut]:
    booked = booked_by_task(session, project_id)
    tasks = session.scalars(
        select(Task).where(Task.project_id == project_id).order_by(Task.position, Task.id)
    )
    return [task_out(t, today, booked.get(t.id, 0)) for t in tasks]


class TaskService:
    def __init__(self, session: Session, principal: Principal, *, today: date) -> None:
        self.session = session
        self.today = today
        self.access = ProjectAccess(session, principal)

    def _task(self, project: Project, task_id: int) -> Task:
        task = self.session.get(Task, task_id)
        if task is None or task.project_id != project.id:
            raise NotFoundError(f"no task {task_id} in this project")
        return task

    def for_project(self, number: int) -> list[TaskOut]:
        project = self.access.visible(number)
        return tasks_of(self.session, project.id, self.today)

    def create(self, number: int, data: TaskCreate) -> TaskOut:
        project = self.access.editable(number)
        _validate(data.planned_start, data.planned_end, data.revised_end)
        position = (
            self.session.scalar(
                select(func.max(Task.position)).where(Task.project_id == project.id)
            )
            or 0
        )
        has_tasks = self.session.scalar(
            select(func.count()).select_from(Task).where(Task.project_id == project.id)
        )
        task = Task(
            project_id=project.id,
            position=position + 1 if has_tasks else 0,
            name=data.name.strip(),
            planned_start=data.planned_start,
            planned_end=data.planned_end,
            revised_end=data.revised_end,
            is_milestone=data.is_milestone,
            progress=data.progress,
        )
        self.session.add(task)
        self.session.flush()
        out = task_out(task, self.today)
        self.session.commit()
        return out

    def update(self, number: int, task_id: int, data: TaskUpdate) -> TaskOut:
        project = self.access.editable(number)
        task = self._task(project, task_id)
        start = data.planned_start or task.planned_start
        end = data.planned_end or task.planned_end
        revised = None if data.clear_revised_end else (data.revised_end or task.revised_end)
        _validate(start, end, revised)
        values: dict[str, object] = {
            "planned_start": start,
            "planned_end": end,
            "revised_end": revised,
            "version": Task.version + 1,
        }
        if data.name is not None:
            values["name"] = data.name.strip()
        if data.is_milestone is not None:
            values["is_milestone"] = data.is_milestone
        if data.progress is not None:
            values["progress"] = data.progress
        result = self.session.execute(
            update(Task).where(Task.id == task.id, Task.version == data.version).values(**values)
        )
        if cast(CursorResult[object], result).rowcount != 1:
            raise StaleVersionError("someone else changed this task; reload and try again")
        self.session.refresh(task)
        out = task_out(task, self.today, booked_by_task(self.session, project.id).get(task.id, 0))
        self.session.commit()
        return out

    def move(self, number: int, task_id: int, direction: str) -> list[TaskOut]:
        """Swap the task with its neighbour; the others keep their order (PG-4)."""
        project = self.access.editable(number)
        task = self._task(project, task_id)
        ordered = list(
            self.session.scalars(
                select(Task).where(Task.project_id == project.id).order_by(Task.position, Task.id)
            )
        )
        index = ordered.index(task)
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(ordered):
            ordered[index], ordered[target] = ordered[target], ordered[index]
        for position, item in enumerate(ordered):
            item.position = position
        self.session.flush()
        out = tasks_of(self.session, project.id, self.today)
        self.session.commit()
        return out

    def delete(self, number: int, task_id: int) -> TaskDeleted:
        """Delete a task; its booked time moves to *General* (D-032), merging into what is there."""
        project = self.access.editable(number)
        task = self._task(project, task_id)
        moved = 0
        entries = list(
            self.session.scalars(
                select(TimeEntry).where(
                    TimeEntry.project_id == project.id, TimeEntry.task_id == task.id
                )
            )
        )
        for entry in entries:
            moved += entry.minutes
            general = self.session.scalar(
                select(TimeEntry).where(
                    TimeEntry.project_id == project.id,
                    TimeEntry.task_id.is_(None),
                    TimeEntry.user_id == entry.user_id,
                    TimeEntry.work_date == entry.work_date,
                )
            )
            if general is not None:
                general.minutes += entry.minutes
                self.session.delete(entry)
            else:
                entry.task_id = None
        self.session.flush()
        self.session.execute(delete(Task).where(Task.id == task.id))
        self.session.commit()
        return TaskDeleted(moved_minutes=moved)


def _validate(start: date, end: date, revised: date | None) -> None:
    try:
        validate_task_dates(start, end, revised)
    except ValueError as error:
        raise RuleViolationError(str(error)) from error
