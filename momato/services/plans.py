"""Action plans: owned by one org node, grouping projects from any department (AP-1..AP-8)."""

from collections import defaultdict
from datetime import date
from typing import cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.ids import in_ids
from momato.db.models import (
    ActionPlan,
    ActionPlanProject,
    LogEntry,
    OrgNode,
    Post,
    Project,
    User,
)
from momato.db.models.people import UserKind, UserStatus
from momato.domain import logbook as lb
from momato.domain.access import Permission
from momato.domain.errors import NotFoundError, RuleViolationError, StaleVersionError
from momato.domain.fields import Profile
from momato.domain.projects import ProjectStatus
from momato.domain.text import plain_excerpt
from momato.identity.policy import AccessPolicy
from momato.identity.principal import Principal
from momato.schemas.plans import (
    FeedItem,
    PlanCreate,
    PlanFeed,
    PlanGroup,
    PlanOverview,
    PlanProject,
    PlanUpdate,
)
from momato.schemas.reference import PlanSummary
from momato.services import common
from momato.services.projects_access import ProjectAccess

FEED_LIMIT = 8


def plan_summaries(
    session: Session, principal: Principal, plans: list[ActionPlan]
) -> list[PlanSummary]:
    """Plans with the number of projects the caller may see in each (AP-8)."""
    counts: dict[int, int] = {}
    if plans:
        policy = AccessPolicy(principal)
        counts = dict(
            session.execute(
                select(ActionPlanProject.plan_id, func.count())
                .join(Project, Project.id == ActionPlanProject.project_id)
                .where(
                    in_ids(ActionPlanProject.plan_id, [p.id for p in plans]),
                    policy.project_filter(Permission.PROJECT_VIEW),
                )
                .group_by(ActionPlanProject.plan_id)
            ).all()
        )
    return [
        PlanSummary(
            id=p.id,
            name=p.name,
            description=p.description,
            owner_org_node_id=p.owner_org_node_id,
            coordinator_id=p.coordinator_id,
            hue=p.hue,
            position=p.position,
            project_count=counts.get(p.id, 0),
            version=p.version,
        )
        for p in plans
    ]


class PlanService:
    def __init__(
        self, session: Session, principal: Principal, profile: Profile, *, today: date
    ) -> None:
        self.session = session
        self.principal = principal
        self.profile = profile
        self.today = today
        self.access = ProjectAccess(session, principal)
        self.policy = self.access.policy

    def _plan(self, plan_id: int) -> ActionPlan:
        plan = self.session.get(ActionPlan, plan_id)
        if plan is None:
            raise NotFoundError(f"no action plan {plan_id}")
        return plan

    def _summary(self, plan: ActionPlan) -> PlanSummary:
        return plan_summaries(self.session, self.principal, [plan])[0]

    def _coordinator(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None or user.kind is not UserKind.PERSON:
            raise RuleViolationError("no such coordinator")
        if user.status is UserStatus.DEACTIVATED:
            raise RuleViolationError(f"{user.name} is no longer active")
        return user

    def _node(self, node_id: int) -> OrgNode:
        node = self.session.get(OrgNode, node_id)
        if node is None:
            raise RuleViolationError(f"no org node {node_id}")
        return node

    # ------------------------------------------------------------ list and manage

    def list(self) -> list[PlanSummary]:
        plans = list(
            self.session.scalars(select(ActionPlan).order_by(ActionPlan.position, ActionPlan.id))
        )
        return plan_summaries(self.session, self.principal, plans)

    def create(self, data: PlanCreate) -> PlanSummary:
        node = self._node(data.owner_org_node_id)
        self.principal.require(Permission.PLAN_MANAGE, node.id)
        coordinator = self._coordinator(data.coordinator_id)
        position = (self.session.scalar(select(func.max(ActionPlan.position))) or 0) + 1
        plan = ActionPlan(
            name=data.name.strip(),
            description=data.description,
            owner_org_node_id=node.id,
            coordinator_id=coordinator.id,
            hue=data.hue,
            position=position,
        )
        self.session.add(plan)
        self.session.flush()
        out = self._summary(plan)
        self.session.commit()
        return out

    def update(self, plan_id: int, data: PlanUpdate) -> PlanSummary:
        plan = self._plan(plan_id)
        self.principal.require(Permission.PLAN_MANAGE, plan.owner_org_node_id)
        values: dict[str, object] = {}
        if data.name is not None:
            values["name"] = data.name.strip()
        if data.description is not None:
            values["description"] = data.description
        if data.hue is not None:
            values["hue"] = data.hue
        if data.owner_org_node_id is not None:
            node = self._node(data.owner_org_node_id)
            self.principal.require(Permission.PLAN_MANAGE, node.id)  # on the new owner too
            values["owner_org_node_id"] = node.id
        if data.coordinator_id is not None:
            values["coordinator_id"] = self._coordinator(data.coordinator_id).id
        result = self.session.execute(
            update(ActionPlan)
            .where(ActionPlan.id == plan.id, ActionPlan.version == data.version)
            .values(**values, version=ActionPlan.version + 1)
        )
        if cast(CursorResult[object], result).rowcount != 1:
            raise StaleVersionError("Someone else changed this plan")
        self.session.refresh(plan)
        out = self._summary(plan)
        self.session.commit()
        return out

    def delete(self, plan_id: int) -> None:
        """Delete a plan; its projects' logbooks note that they were removed from it."""
        plan = self._plan(plan_id)
        self.principal.require(Permission.PLAN_MANAGE, plan.owner_org_node_id)
        project_ids = list(
            self.session.scalars(
                select(ActionPlanProject.project_id).where(ActionPlanProject.plan_id == plan.id)
            )
        )
        now = utcnow()
        self.session.add_all(
            LogEntry(
                project_id=project_id,
                at=now,
                actor_id=self.principal.user_id,
                field_key=lb.LogField.ACTION_PLANS,
                from_value=None,
                to_value=f"Removed from {plan.name}",
                api_token_id=self.principal.token_id,
            )
            for project_id in project_ids
        )
        self.session.execute(delete(ActionPlanProject).where(ActionPlanProject.plan_id == plan.id))
        self.session.execute(delete(ActionPlan).where(ActionPlan.id == plan.id))
        self.session.commit()

    def add_project(self, plan_id: int, number: int) -> PlanSummary:
        """Link a project (AP-7): `project.edit` on it or `plan.manage` on the plan's owner."""
        plan = self._plan(plan_id)
        project = self.access.visible(number)
        if not (
            self.access.can(project, Permission.PROJECT_EDIT)
            or self.principal.can(Permission.PLAN_MANAGE, plan.owner_org_node_id)
        ):
            self.principal.require(Permission.PROJECT_EDIT, project.org_node_id)
        if self.session.get(ActionPlanProject, (plan.id, project.id)) is None:
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
        out = self._summary(plan)
        self.session.commit()
        return out

    def remove_project(self, plan_id: int, number: int) -> PlanSummary:
        plan = self._plan(plan_id)
        project = self.access.visible(number)
        if not (
            self.access.can(project, Permission.PROJECT_EDIT)
            or self.principal.can(Permission.PLAN_MANAGE, plan.owner_org_node_id)
        ):
            self.principal.require(Permission.PROJECT_EDIT, project.org_node_id)
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
        out = self._summary(plan)
        self.session.commit()
        return out

    # ------------------------------------------------------------ overview

    def _visible_projects(self, plan: ActionPlan) -> list[Project]:
        return list(
            self.session.scalars(
                select(Project)
                .join(ActionPlanProject, ActionPlanProject.project_id == Project.id)
                .where(
                    ActionPlanProject.plan_id == plan.id,
                    self.policy.project_filter(Permission.PROJECT_VIEW),
                )
                .order_by(Project.start_date, Project.number)
            )
        )

    def _top_department(self, node_id: int) -> int:
        """The root's child that the node lies under (the node itself for the root)."""
        path = self.principal.tree.ancestors_or_self(node_id)
        return path[-2] if len(path) >= 2 else path[-1]

    def overview(self, plan_id: int) -> PlanOverview:
        """Projects grouped by top-level department, the owner's group first (AP-4, AP-5)."""
        plan = self._plan(plan_id)
        projects = self._visible_projects(plan)
        summaries = common.day_summaries(
            self.session,
            [p.id for p in projects],
            self.today,
            self.profile.numbers.hours_per_day,
        )
        people = common.person_refs(
            self.session, {p.coordinator_id for p in projects} | {plan.coordinator_id}
        )
        names = dict(self.session.execute(select(OrgNode.id, OrgNode.name)).all())
        owner_group = self._top_department(plan.owner_org_node_id)
        by_group: dict[int, list[Project]] = defaultdict(list)
        for project in projects:
            by_group[self._top_department(project.org_node_id)].append(project)

        groups: list[PlanGroup] = []
        for node_id, members in by_group.items():
            counts: dict[ProjectStatus, int] = {}
            for project in members:
                counts[project.status] = counts.get(project.status, 0) + 1
            groups.append(
                PlanGroup(
                    org_node_id=node_id,
                    name=names.get(node_id, ""),
                    is_owner=node_id == owner_group,
                    projects=[
                        PlanProject(
                            number=p.number,
                            name=p.name,
                            status=p.status,
                            start_date=p.start_date,
                            end_date=p.end_date,
                            coordinator=people[p.coordinator_id],
                            goal=p.goal,
                            days=common.meter(summaries[p.id]),
                        )
                        for p in members
                    ],
                    status_counts=counts,
                    start_date=min(p.start_date for p in members),
                    end_date=max(p.end_date for p in members),
                    days=common.meter(common.sum_summaries(summaries[p.id] for p in members)),
                )
            )
        groups.sort(key=lambda g: (not g.is_owner, g.name.casefold()))
        total = common.sum_summaries(summaries.values())
        return PlanOverview(
            plan=self._summary(plan),
            owner_name=names.get(plan.owner_org_node_id, ""),
            coordinator=people[plan.coordinator_id],
            department_count=len(groups),
            project_count=len(projects),
            days=common.meter(total),
            groups=groups,
        )

    # ------------------------------------------------------------ feed

    def feed(self, plan_id: int, project_number: int | None = None) -> PlanFeed:
        """Remarks and logbook changes (not creations), newest first, at most eight (AP-6)."""
        plan = self._plan(plan_id)
        projects = self._visible_projects(plan)
        if project_number is not None:
            projects = [p for p in projects if p.number == project_number]
            if not projects:
                raise NotFoundError(f"project {project_number} is not in this plan")
        by_id = {p.id: p for p in projects}
        if not by_id:
            return PlanFeed(items=[])
        remarks = list(
            self.session.scalars(
                select(Post)
                .where(
                    in_ids(Post.project_id, by_id),
                    Post.parent_id.is_(None),
                    Post.deleted_at.is_(None),
                )
                .order_by(Post.created_at.desc(), Post.id.desc())
                .limit(FEED_LIMIT)
            )
        )
        changes = list(
            self.session.scalars(
                select(LogEntry)
                .where(
                    in_ids(LogEntry.project_id, by_id),
                    LogEntry.field_key != lb.LogField.CREATED,
                )
                .order_by(LogEntry.at.desc(), LogEntry.id.desc())
                .limit(FEED_LIMIT)
            )
        )
        refs = common.person_refs(
            self.session, {r.author_id for r in remarks} | {c.actor_id for c in changes}
        )
        items: list[FeedItem] = [
            FeedItem(
                kind="remark",
                at=r.created_at,
                project_number=by_id[r.project_id].number,
                project_name=by_id[r.project_id].name,
                actor=refs[r.author_id],
                tab="remarks",
                excerpt=plain_excerpt(r.body_md),
                field=None,
                from_value=None,
                to_value=None,
            )
            for r in remarks
        ] + [
            FeedItem(
                kind="log",
                at=c.at,
                project_number=by_id[c.project_id].number,
                project_name=by_id[c.project_id].name,
                actor=refs[c.actor_id],
                tab="logbook",
                excerpt=None,
                field=lb.FIELD_LABELS[c.field_key],
                from_value=c.from_value,
                to_value=c.to_value,
            )
            for c in changes
        ]
        items.sort(key=lambda item: item.at, reverse=True)
        return PlanFeed(items=items[:FEED_LIMIT])


__all__ = ["FEED_LIMIT", "PlanService", "UserStatus", "plan_summaries"]
