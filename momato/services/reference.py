"""The bootstrap document: the org tree, people, plans and the profile; never any projects."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from momato import __version__
from momato.db.models import ActionPlan, OrgNode, User
from momato.db.models.people import UserKind, UserStatus
from momato.domain.access import Permission
from momato.domain.errors import AuthenticationRequiredError
from momato.domain.fields import Profile
from momato.domain.projects import (
    PRIORITY_LABELS,
    STATUS_HUES,
    STATUS_LABELS,
    Priority,
    ProjectStatus,
)
from momato.identity.principal import Principal
from momato.identity.providers import IdentityProviders
from momato.schemas.auth import Me
from momato.schemas.reference import (
    Bootstrap,
    CardOut,
    CategoryOut,
    FieldOut,
    OrgNodeOut,
    PersonOut,
    PriorityOut,
    ProfileOut,
    StatusOut,
    TemplateTaskOut,
)
from momato.services.plans import plan_summaries
from momato.services.timesheet import TimesheetService


def profile_out(profile: Profile) -> ProfileOut:
    numbers = profile.numbers
    return ProfileOut(
        name=profile.name,
        cards=[
            CardOut(
                key=card.key,
                title=card.title,
                fields=[
                    FieldOut(
                        key=f.key,
                        label=f.label,
                        type=f.type.value if f.type else None,
                        core=f.core,
                        choices=list(f.choices),
                    )
                    for f in card.fields
                ],
            )
            for card in profile.cards
        ],
        categories=[
            CategoryOut(key=c.key, label=c.label, kind=c.kind.value) for c in profile.categories
        ],
        task_template=[
            TemplateTaskOut(
                name=t.name, start=float(t.start), end=float(t.end), milestone=t.milestone
            )
            for t in profile.task_template
        ],
        hours_per_day=numbers.hours_per_day,
        day_cap_minutes=numbers.day_cap_minutes,
        timesheet_step_minutes=numbers.timesheet_step_minutes,
        available_days_per_year=numbers.available_days_per_year,
        other_work_share=float(numbers.other_work_share),
        first_project_number=numbers.first_project_number,
    )


def build_bootstrap(
    session: Session,
    principal: Principal,
    profile: Profile,
    providers: IdentityProviders,
    *,
    today: date,
) -> Bootstrap:
    """Everything the frontend needs once. A visitor who may see nothing gets 401 (sign in)."""
    if principal.is_anonymous and not principal.can_somewhere(Permission.PROJECT_VIEW):
        raise AuthenticationRequiredError("log in to use MoMaTo")
    org = [
        OrgNodeOut(
            id=n.id,
            parent_id=n.parent_id,
            name=n.name,
            position=n.position,
            is_department=n.is_department,
        )
        for n in session.scalars(
            select(OrgNode).order_by(OrgNode.parent_id, OrgNode.position, OrgNode.id)
        )
    ]
    people = [
        PersonOut(
            id=u.id,
            name=u.name,
            job_title=u.job_title,
            org_node_id=u.org_node_id,
            hue=u.hue,
            active=u.status is not UserStatus.DEACTIVATED,
            work_minutes=[
                u.work_minutes_mon,
                u.work_minutes_tue,
                u.work_minutes_wed,
                u.work_minutes_thu,
                u.work_minutes_fri,
            ],
        )
        for u in session.scalars(
            select(User).where(User.kind == UserKind.PERSON).order_by(User.name, User.id)
        )
    ]
    hidden = set(profile.hidden_statuses)
    plans = list(session.scalars(select(ActionPlan).order_by(ActionPlan.position, ActionPlan.id)))
    return Bootstrap(
        version=__version__,
        today=today,
        me=Me.build(principal, providers),
        org=org,
        people=people,
        statuses=[
            StatusOut(
                key=s.value,
                label=STATUS_LABELS[s],
                hue=STATUS_HUES[s],
                gray=s is ProjectStatus.REJECTED,
                hidden=s in hidden,
            )
            for s in ProjectStatus
        ],
        priorities=[PriorityOut(key=p.value, label=PRIORITY_LABELS[p]) for p in Priority],
        plans=plan_summaries(session, principal, plans),
        profile=profile_out(profile),
        week_card=TimesheetService(session, principal, profile, today=today).week_card(),
    )
