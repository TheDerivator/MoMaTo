"""Projects: the paged list with counts, one project, creating, editing, members, plans, delete.

Every read goes through the access policy (invisible is 404); every change to a core field writes
its logbook entries in the same transaction (LB-1). Editing scalar fields needs the version the
editor loaded (PP-6). Members and plan links are set operations: adding twice or removing a
missing one changes nothing, so they carry no version.
"""

import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    Select,
    Unicode,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session, aliased

from momato.db.base import utcnow
from momato.db.ids import in_ids
from momato.db.models import (
    ActionPlan,
    ActionPlanProject,
    Attachment,
    LogEntry,
    OrgNode,
    PlannedDays,
    Post,
    PostRevision,
    Project,
    ProjectDetail,
    ProjectMember,
    Task,
    TimeEntry,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.db.session import PROJECT_NUMBER_LOCK, acquire_lock
from momato.db.text import contains_ci
from momato.domain import logbook as lb
from momato.domain.access import Permission
from momato.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
    StaleVersionError,
)
from momato.domain.fields import FieldType, FieldValueError, Profile, validate_value
from momato.domain.numbering import next_project_number
from momato.domain.projects import ProjectStatus
from momato.domain.tasks import tasks_from_template, timeline_text
from momato.identity.principal import Principal
from momato.schemas.projects import (
    LogEntryOut,
    LogPage,
    Neighbours,
    ProjectCounts,
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectRow,
    ProjectUpdate,
)
from momato.services import common
from momato.services.projects_access import ProjectAccess
from momato.services.tasks import tasks_of

PAGE_SIZE = 50
ROW_MEMBERS = 3  # avatars shown next to the coordinator (PL-4)


@dataclass(frozen=True)
class ProjectFilters:
    """The list's filters, all in the URL (PL-7)."""

    node: int | None = None
    status: ProjectStatus | None = None
    q: str = ""  # searches name, number, coordinator and org node name (SH-6)
    name: str = ""  # the Project header's filter (PL-3)
    coordinator: str = ""  # the Coordinator header's filter


class ProjectService:
    def __init__(
        self,
        session: Session,
        principal: Principal,
        profile: Profile,
        *,
        today: date,
        uploads_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        self.uploads_dir = uploads_dir
        self.access = ProjectAccess(session, principal)
        self.policy = self.access.policy
        self._coordinator = aliased(User)

    # ------------------------------------------------------------ list, counts, neighbours

    def _conditions(
        self, filters: ProjectFilters, *, node: bool = True, status: bool = True
    ) -> list[ColumnElement[bool]]:
        """The WHERE conditions of the list; `node`/`status` leave that filter out of counts."""
        conditions = [self.policy.project_filter(Permission.PROJECT_VIEW)]
        tree = self.principal.tree
        if node and filters.node is not None:
            if filters.node not in tree:
                raise NotFoundError(f"no org node {filters.node}")
            conditions.append(in_ids(Project.org_node_id, tree.subtree(filters.node)))
        if status:
            if filters.status is not None:
                conditions.append(Project.status == filters.status)
            elif self.profile.hidden_statuses:
                conditions.append(Project.status.not_in(self.profile.hidden_statuses))
        needle = filters.q.strip().lstrip("#").strip()
        if filters.q.strip():
            parts: list[ColumnElement[bool]] = [
                contains_ci(Project.name, filters.q.strip()),
                contains_ci(self._coordinator.name, filters.q.strip()),
                contains_ci(OrgNode.name, filters.q.strip()),
            ]
            if needle.isdigit():
                parts.append(sql_cast(Project.number, Unicode(20)).contains(needle))
            conditions.append(or_(*parts))
        if filters.name.strip():
            conditions.append(contains_ci(Project.name, filters.name.strip()))
        if filters.coordinator.strip():
            conditions.append(contains_ci(self._coordinator.name, filters.coordinator.strip()))
        return conditions

    def _joined[*Ts](self, query: Select[*Ts]) -> Select[*Ts]:
        """Add the coordinator and org node joins the filters need to any projects query."""
        return (
            query.select_from(Project)
            .join(self._coordinator, self._coordinator.id == Project.coordinator_id)
            .join(OrgNode, OrgNode.id == Project.org_node_id)
        )

    def page(
        self, filters: ProjectFilters, after: int | None = None, limit: int = PAGE_SIZE
    ) -> ProjectPage:
        """Keyset paging on the number, highest first: rows added meanwhile never repeat (PL-7)."""
        conditions = self._conditions(filters)
        total = self.session.scalar(self._joined(select(func.count())).where(*conditions)) or 0
        query = self._joined(select(Project, OrgNode.name)).where(*conditions)
        if after is not None:
            query = query.where(Project.number < after)
        rows = list(self.session.execute(query.order_by(Project.number.desc()).limit(limit + 1)))
        more = len(rows) > limit
        rows = rows[:limit]
        projects = [(p, node_name) for p, node_name in rows]
        ids = [p.id for p, _ in projects]
        members: dict[int, list[int]] = defaultdict(list)
        if ids:
            for project_id, user_id in self.session.execute(
                select(ProjectMember.project_id, ProjectMember.user_id)
                .where(in_ids(ProjectMember.project_id, ids))
                .order_by(ProjectMember.user_id)
            ):
                members[project_id].append(user_id)
        wanted = {p.coordinator_id for p, _ in projects} | {
            u for p, _ in projects for u in members[p.id] if u != p.coordinator_id
        }
        people = common.person_refs(self.session, wanted)
        items = [
            ProjectRow(
                number=p.number,
                name=p.name,
                org_node_id=p.org_node_id,
                org_node_name=node_name,
                status=p.status,
                start_date=p.start_date,
                end_date=p.end_date,
                coordinator=people[p.coordinator_id],
                members=[people[u] for u in members[p.id] if u != p.coordinator_id and u in people][
                    :ROW_MEMBERS
                ],
            )
            for p, node_name in projects
        ]
        return ProjectPage(
            items=items, total=total, next_after=items[-1].number if more and items else None
        )

    def export_batches(
        self, filters: ProjectFilters, size: int
    ) -> Iterator[list[tuple[Project, str]]]:
        """Every project of the list as the caller sees it, highest number first, `size` at a
        time with their organisation node's name (EXP-1)."""
        conditions = self._conditions(filters)
        after: int | None = None
        while True:
            query = self._joined(select(Project, OrgNode.name)).where(*conditions)
            if after is not None:
                query = query.where(Project.number < after)
            rows = list(self.session.execute(query.order_by(Project.number.desc()).limit(size)))
            if rows:
                yield [(project, node_name) for project, node_name in rows]
            if len(rows) < size:
                return
            after = rows[-1][0].number

    def counts(self, filters: ProjectFilters) -> ProjectCounts:
        """Status counts (not narrowed by status) and rolled-up node counts (not by node)."""
        by_status: dict[ProjectStatus, int] = dict.fromkeys(ProjectStatus, 0)
        for status, count in self.session.execute(
            self._joined(select(Project.status, func.count()))
            .where(*self._conditions(filters, status=False))
            .group_by(Project.status)
        ):
            by_status[status] = count

        direct = dict(
            self.session.execute(
                self._joined(select(Project.org_node_id, func.count()))
                .where(*self._conditions(filters, node=False))
                .group_by(Project.org_node_id)
            ).all()
        )
        tree = self.principal.tree
        rolled: dict[int, int] = defaultdict(int)
        for node_id, count in direct.items():
            for ancestor in tree.ancestors_or_self(node_id):
                rolled[ancestor] += count
        if filters.node is not None:
            if filters.node not in tree:
                raise NotFoundError(f"no org node {filters.node}")
            total = rolled.get(filters.node, 0)
        else:
            total = sum(direct.values())
        return ProjectCounts(statuses=by_status, nodes=dict(rolled), total=total)

    def neighbours(self, number: int, filters: ProjectFilters) -> Neighbours:
        project = self.access.visible(number)
        conditions = self._conditions(filters)
        in_list = bool(
            self.session.scalar(
                self._joined(select(func.count())).where(*conditions, Project.id == project.id)
            )
        )
        total = self.session.scalar(self._joined(select(func.count())).where(*conditions)) or 0
        above = (
            self.session.scalar(
                self._joined(select(func.count())).where(*conditions, Project.number > number)
            )
            or 0
        )
        previous = self.session.scalar(
            self._joined(select(func.min(Project.number))).where(
                *conditions, Project.number > number
            )
        )
        following = self.session.scalar(
            self._joined(select(func.max(Project.number))).where(
                *conditions, Project.number < number
            )
        )
        return Neighbours(
            position=above + 1 if in_list else None,
            total=total,
            previous=previous,
            next=following,
            in_list=in_list,
        )

    # ------------------------------------------------------------ one project

    def get(self, number: int) -> ProjectOut:
        return self._out(self.access.visible(number))

    def _out(self, project: Project) -> ProjectOut:
        session = self.session
        member_list = list(
            session.scalars(
                select(ProjectMember.user_id).where(ProjectMember.project_id == project.id)
            )
        )
        refs = common.person_refs(session, {project.coordinator_id, *member_list})
        others = sorted(
            (u for u in member_list if u != project.coordinator_id),
            key=lambda u: (refs[u].name.casefold(), u),
        )
        plan_ids = list(
            session.scalars(
                select(ActionPlanProject.plan_id)
                .where(ActionPlanProject.project_id == project.id)
                .order_by(ActionPlanProject.plan_id)
            )
        )
        details = {
            key: json.loads(value)
            for key, value in session.execute(
                select(ProjectDetail.field_key, ProjectDetail.value).where(
                    ProjectDetail.project_id == project.id
                )
            )
        }
        known = self.profile.detail_fields
        details = {k: v for k, v in details.items() if k in known}  # dropped fields stay hidden
        summary = common.day_summaries(
            session, [project.id], self.today, self.profile.numbers.hours_per_day
        )[project.id]
        remark_count = (
            session.scalar(
                select(func.count())
                .select_from(Post)
                .where(
                    Post.project_id == project.id,
                    Post.parent_id.is_(None),
                    Post.deleted_at.is_(None),
                )
            )
            or 0
        )
        log_count = (
            session.scalar(
                select(func.count()).select_from(LogEntry).where(LogEntry.project_id == project.id)
            )
            or 0
        )
        node_name = session.scalar(select(OrgNode.name).where(OrgNode.id == project.org_node_id))
        members = set(member_list)
        return ProjectOut(
            number=project.number,
            name=project.name,
            org_node_id=project.org_node_id,
            org_node_name=node_name or "",
            status=project.status,
            start_date=project.start_date,
            end_date=project.end_date,
            goal=project.goal,
            priority=project.priority,
            coordinator=refs[project.coordinator_id],
            members=[refs[project.coordinator_id], *(refs[u] for u in others)],
            plan_ids=plan_ids,
            details=details,
            timeline_text=timeline_text(project.start_date, project.end_date, self.today),
            tasks=tasks_of(session, project.id, self.today),
            days=common.days_out(summary),
            remark_count=remark_count,
            log_count=log_count,
            created_at=project.created_at,
            updated_at=project.updated_at,
            version=project.version,
            can_edit=self._can(project, members, Permission.PROJECT_EDIT),
            can_comment=self._can(project, members, Permission.PROJECT_COMMENT),
            can_delete=self._can(project, members, Permission.PROJECT_DELETE),
        )

    def _can(self, project: Project, members: set[int], permission: Permission) -> bool:
        return self.policy.can_on_project(
            permission,
            node_id=project.org_node_id,
            coordinator_id=project.coordinator_id,
            member_ids=members,
        )

    # ------------------------------------------------------------ create

    def _person(self, user_id: int, *, what: str = "person") -> User:
        user = self.session.get(User, user_id)
        if user is None or user.kind is not UserKind.PERSON:
            raise RuleViolationError(f"no such {what}")
        if user.status is UserStatus.DEACTIVATED:
            raise RuleViolationError(f"{user.name} is no longer active")
        return user

    def _node(self, node_id: int) -> OrgNode:
        node = self.session.get(OrgNode, node_id)
        if node is None:
            raise RuleViolationError(f"no org node {node_id}")
        return node

    def create(self, data: ProjectCreate) -> ProjectOut:
        node = self._node(data.org_node_id)
        self.principal.require(Permission.PROJECT_EDIT, node.id)
        if data.end_date < data.start_date:
            raise RuleViolationError("the end date cannot be before the start date")
        coordinator_id = data.coordinator_id
        if coordinator_id is None:
            if self.principal.is_system or self.principal.is_anonymous:
                raise RuleViolationError("choose a coordinator")
            coordinator_id = self.principal.user_id
        coordinator = self._person(coordinator_id, what="coordinator")

        acquire_lock(self.session, PROJECT_NUMBER_LOCK)
        highest = self.session.scalar(select(func.max(Project.number)))
        number = next_project_number(highest, self.profile.numbers.first_project_number)
        now = utcnow()
        project = Project(
            number=number,
            name=data.name,
            org_node_id=node.id,
            status=data.status,
            coordinator_id=coordinator.id,
            start_date=data.start_date,
            end_date=data.end_date,
            goal=data.goal,
            priority=data.priority,
            created_at=now,
            updated_at=now,
        )
        self.session.add(project)
        self.session.flush()
        self.session.add(ProjectMember(project_id=project.id, user_id=coordinator.id))
        if data.use_template:
            planned = tasks_from_template(
                self.profile.task_template, project.start_date, project.end_date
            )
            self.session.add_all(
                Task(
                    project_id=project.id,
                    position=position,
                    name=item.name,
                    planned_start=item.planned_start,
                    planned_end=item.planned_end,
                    is_milestone=item.is_milestone,
                )
                for position, item in enumerate(planned)
            )
        common.write_log(
            self.session,
            project,
            self.principal.user_id,
            [lb.creation_entry()],
            via=self.principal.token_id,
        )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    # ------------------------------------------------------------ update

    def _validated_details(self, details: dict[str, Any]) -> dict[str, object]:
        known = self.profile.detail_fields
        cleaned: dict[str, object] = {}
        for key, value in details.items():
            definition = known.get(key)
            if definition is None:
                raise RuleViolationError(f"unknown detail field {key!r}")
            try:
                normalised = validate_value(definition, value)
            except FieldValueError as error:
                raise RuleViolationError(f"{definition.label}: {error}") from error
            if normalised is not None:
                self._check_reference(definition.type, normalised, definition.label)
            cleaned[key] = normalised
        return cleaned

    def _check_reference(self, kind: FieldType | None, value: object, label: str) -> None:
        if (
            kind is FieldType.PERSON
            and isinstance(value, int)
            and self.session.get(User, value) is None
        ):
            raise RuleViolationError(f"{label}: no such person")
        if kind is FieldType.PROJECT and isinstance(value, int):
            exists = self.session.scalar(select(Project.id).where(Project.number == value))
            if exists is None:
                raise RuleViolationError(f"{label}: no project #{value}")

    def update(self, number: int, data: ProjectUpdate) -> ProjectOut:
        project = self.access.editable(number)
        sent = data.model_fields_set - {"version"}
        values: dict[str, object] = {}
        if "name" in sent and data.name is not None:
            title = data.name.strip()
            if not title:
                raise RuleViolationError("a title is required")
            if title != project.name:
                values["name"] = title
        if data.status is not None and data.status is not project.status:
            values["status"] = data.status
        start = data.start_date or project.start_date
        end = data.end_date or project.end_date
        if end < start:
            raise RuleViolationError("the end date cannot be before the start date")
        if start != project.start_date:
            values["start_date"] = start
        if end != project.end_date:
            values["end_date"] = end
        if data.goal is not None and data.goal != project.goal:
            values["goal"] = data.goal
        if data.priority is not None and data.priority is not project.priority:
            values["priority"] = data.priority
        if data.org_node_id is not None and data.org_node_id != project.org_node_id:
            node = self._node(data.org_node_id)
            self.principal.require(Permission.PROJECT_EDIT, node.id)  # on the new branch too
            values["org_node_id"] = node.id
        new_coordinator: User | None = None
        if data.coordinator_id is not None and data.coordinator_id != project.coordinator_id:
            new_coordinator = self._person(data.coordinator_id, what="coordinator")
            values["coordinator_id"] = new_coordinator.id
        details = self._validated_details(data.details or {})
        stored: dict[str, object] = {}
        if details:
            stored = {
                key: json.loads(value)
                for key, value in self.session.execute(
                    select(ProjectDetail.field_key, ProjectDetail.value).where(
                        ProjectDetail.project_id == project.id,
                        ProjectDetail.field_key.in_(list(details)),
                    )
                )
            }
        changed_details = {k: v for k, v in details.items() if stored.get(k) != v}
        if not values and not changed_details:
            return self._out(project)  # nothing changes: no version, no logbook (PP-3)

        before = common.snapshot(self.session, project)
        result = self.session.execute(
            update(Project)
            .where(Project.id == project.id, Project.version == data.version)
            .values(**values, version=Project.version + 1, updated_at=utcnow())
        )
        if cast(CursorResult[object], result).rowcount != 1:
            raise StaleVersionError("Someone else changed this project")
        self.session.refresh(project)
        if new_coordinator is not None:
            already = self.session.get(ProjectMember, (project.id, new_coordinator.id))
            if already is None:
                self.session.add(ProjectMember(project_id=project.id, user_id=new_coordinator.id))
                self.session.flush()
        for key, value in changed_details.items():
            row = self.session.get(ProjectDetail, (project.id, key))
            if value is None:
                if row is not None:
                    self.session.delete(row)
            elif row is None:
                self.session.add(
                    ProjectDetail(
                        project_id=project.id,
                        field_key=key,
                        value=json.dumps(value, ensure_ascii=False),
                    )
                )
            else:
                row.value = json.dumps(value, ensure_ascii=False)
        self.session.flush()
        after = common.snapshot(self.session, project)
        common.write_log(
            self.session,
            project,
            self.principal.user_id,
            lb.diff_core(before, after),
            via=self.principal.token_id,
        )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    # ------------------------------------------------------------ members

    def add_member(self, number: int, user_id: int) -> ProjectOut:
        project = self.access.editable(number)
        user = self._person(user_id)
        if self.session.get(ProjectMember, (project.id, user.id)) is None:
            before = common.snapshot(self.session, project)
            self.session.add(ProjectMember(project_id=project.id, user_id=user.id))
            self.session.flush()
            after = common.snapshot(self.session, project)
            common.write_log(
                self.session,
                project,
                self.principal.user_id,
                lb.diff_core(before, after),
                via=self.principal.token_id,
            )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    def remove_member(self, number: int, user_id: int) -> ProjectOut:
        """Removing a member also removes their planned days; their booked time stays (PD-4)."""
        project = self.access.editable(number)
        if user_id == project.coordinator_id:
            raise RuleViolationError(
                "the coordinator cannot be removed: change the coordinator first"
            )
        member = self.session.get(ProjectMember, (project.id, user_id))
        if member is None:
            raise NotFoundError("that person is not involved in this project")
        before = common.snapshot(self.session, project)
        self.session.execute(
            delete(PlannedDays).where(
                PlannedDays.project_id == project.id, PlannedDays.user_id == user_id
            )
        )
        self.session.delete(member)
        self.session.flush()
        after = common.snapshot(self.session, project)
        common.write_log(
            self.session,
            project,
            self.principal.user_id,
            lb.diff_core(before, after),
            via=self.principal.token_id,
        )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    # ------------------------------------------------------------ action plans

    def _plan(self, plan_id: int) -> ActionPlan:
        plan = self.session.get(ActionPlan, plan_id)
        if plan is None:
            raise NotFoundError(f"no action plan {plan_id}")
        return plan

    def _may_link(self, project: Project, plan: ActionPlan) -> None:
        """`project.edit` on the project or `plan.manage` on the plan's owner (D-031)."""
        if self.access.can(project, Permission.PROJECT_EDIT):
            return
        if self.principal.can(Permission.PLAN_MANAGE, plan.owner_org_node_id):
            return
        if self.principal.is_anonymous:
            self.principal.require(Permission.PROJECT_EDIT, project.org_node_id)
        raise PermissionDeniedError("missing permission project.edit or plan.manage")

    def link_plan(self, number: int, plan_id: int) -> ProjectOut:
        project = self.access.visible(number)
        plan = self._plan(plan_id)
        self._may_link(project, plan)
        link = self.session.get(ActionPlanProject, (plan.id, project.id))
        if link is None:
            before = common.snapshot(self.session, project)
            self.session.add(ActionPlanProject(plan_id=plan.id, project_id=project.id))
            self.session.flush()
            after = common.snapshot(self.session, project)
            common.write_log(
                self.session,
                project,
                self.principal.user_id,
                lb.diff_core(before, after),
                via=self.principal.token_id,
            )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    def unlink_plan(self, number: int, plan_id: int) -> ProjectOut:
        project = self.access.visible(number)
        plan = self._plan(plan_id)
        self._may_link(project, plan)
        link = self.session.get(ActionPlanProject, (plan.id, project.id))
        if link is not None:
            before = common.snapshot(self.session, project)
            self.session.delete(link)
            self.session.flush()
            after = common.snapshot(self.session, project)
            common.write_log(
                self.session,
                project,
                self.principal.user_id,
                lb.diff_core(before, after),
                via=self.principal.token_id,
            )
        self.session.flush()
        out = self._out(project)
        self.session.commit()
        return out

    # ------------------------------------------------------------ delete

    def delete(self, number: int) -> None:
        """Delete a project and what hangs on it; refused when time is booked on it (D-018)."""
        project = self.access.deletable(number)
        booked = self.session.scalar(
            select(func.count()).select_from(TimeEntry).where(TimeEntry.project_id == project.id)
        )
        if booked:
            raise ConflictError("time is booked on this project, so it cannot be deleted")
        session = self.session
        keys = list(
            session.scalars(select(Attachment.public_id).where(Attachment.project_id == project.id))
        )
        session.execute(delete(Attachment).where(Attachment.project_id == project.id))
        post_ids = list(session.scalars(select(Post.id).where(Post.project_id == project.id)))
        if post_ids:
            session.execute(delete(PostRevision).where(in_ids(PostRevision.post_id, post_ids)))
        session.execute(
            delete(Post).where(Post.project_id == project.id, Post.parent_id.is_not(None))
        )
        session.execute(delete(Post).where(Post.project_id == project.id))
        for model in (LogEntry, ActionPlanProject, PlannedDays, ProjectDetail, Task, ProjectMember):
            session.execute(delete(model).where(model.project_id == project.id))
        session.execute(delete(Project).where(Project.id == project.id))
        session.commit()
        if self.uploads_dir is not None:
            for key in keys:
                (self.uploads_dir / key).unlink(missing_ok=True)

    # ------------------------------------------------------------ logbook

    def log(self, number: int, group: str | None = None) -> LogPage:
        project = self.access.visible(number)
        try:
            fields = lb.filter_fields(group)
        except ValueError as error:
            raise RuleViolationError(str(error)) from error
        count = (
            self.session.scalar(
                select(func.count()).select_from(LogEntry).where(LogEntry.project_id == project.id)
            )
            or 0
        )
        query = select(LogEntry).where(LogEntry.project_id == project.id)
        if fields is not None:
            query = query.where(LogEntry.field_key.in_(sorted(fields)))
        entries = list(self.session.scalars(query.order_by(LogEntry.at.desc(), LogEntry.id.desc())))
        refs = common.person_refs(self.session, {e.actor_id for e in entries})
        via = common.token_names(self.session, [e.api_token_id for e in entries])
        items = [
            LogEntryOut(
                id=e.id,
                at=e.at,
                actor=refs[e.actor_id],
                field=e.field_key.value,
                field_label=lb.FIELD_LABELS[e.field_key],
                hue=lb.FIELD_HUES.get(e.field_key, lb.DEFAULT_HUE),
                from_value=e.from_value,
                to_value=e.to_value,
                via=via.get(e.api_token_id or 0),
            )
            for e in entries
        ]
        return LogPage(items=items, total=len(items), count=count)
