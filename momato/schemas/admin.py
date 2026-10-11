"""Shapes of the administration endpoints: org tree, people, sign-in, roles, grants, audit log."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from momato.db.models.people import UserStatus
from momato.domain.access import Audience, Permission, Scope, ScopeKind
from momato.schemas.common import Name100, Name200

MAX_WORK_MINUTES = 12 * 60


class OrgNodeCreate(BaseModel):
    """A new branch under `parent_id`; without a parent it is the root, allowed only while the
    organisation has none (a fresh installation)."""

    parent_id: int | None = None
    name: Name200
    is_department: bool = False


class OrgNodeUpdate(BaseModel):
    """Every field is optional; `parent_id` moves the node (with `position` choosing the place)."""

    name: Name200 | None = None
    is_department: bool | None = None
    parent_id: int | None = None
    position: int | None = Field(default=None, ge=0)


def _day_range(value: list[int]) -> list[int]:
    if any(m < 0 or m > MAX_WORK_MINUTES for m in value):
        raise ValueError(f"each day is between 0 and {MAX_WORK_MINUTES} minutes")
    return value


# Minutes per weekday, Monday to Friday (D-019).
WorkMinutes = Annotated[list[int], Field(min_length=5, max_length=5), AfterValidator(_day_range)]


class PersonCreate(BaseModel):
    name: Name200
    job_title: str | None = Field(default=None, max_length=100)
    org_node_id: int
    hue: int = Field(default=285, ge=0, le=359)
    work_minutes: WorkMinutes | None = None


class PersonUpdate(BaseModel):
    """Only the fields that are sent change; `job_title: null` clears the title."""

    name: Name200 | None = None
    job_title: str | None = Field(default=None, max_length=100)
    org_node_id: int | None = None
    hue: int | None = Field(default=None, ge=0, le=359)
    work_minutes: WorkMinutes | None = None


class AvailabilityIn(BaseModel):
    days: Decimal = Field(ge=0, le=366, decimal_places=2)


class AvailabilityOut(BaseModel):
    year: int
    override_days: float | None  # what an administrator set; None: the default applies
    default_days: float  # the profile's days × the person's capacity factor (D-020)
    days: float  # the effective value


class ScopeIn(BaseModel):
    """Where a role applies: everywhere, one branch (`node_id`) or the holder's own department."""

    scope_kind: ScopeKind
    node_id: int | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.scope_kind is ScopeKind.NODE) != (self.node_id is not None):
            raise ValueError("a branch scope needs a node_id; the other scopes have none")
        return self

    @property
    def scope(self) -> Scope:
        return Scope(self.scope_kind, self.node_id)


class AssignmentIn(ScopeIn):
    role_key: str = Field(min_length=1, max_length=50)


class AssignmentOut(BaseModel):
    id: int
    role_key: str
    role_name: str
    scope_kind: ScopeKind
    node_id: int | None
    scope_label: str


class ExternalIdentityOut(BaseModel):
    """A person's single sign-on link and the groups the provider last reported for them."""

    provider: str
    last_seen_at: datetime | None
    groups: list[str]


class GroupMappingIn(ScopeIn):
    provider: str = Field(min_length=1, max_length=50)
    group_name: str = Field(min_length=1, max_length=255)
    role_key: str = Field(min_length=1, max_length=50)


class GroupMappingOut(BaseModel):
    id: int
    provider: str
    group_name: str
    role_key: str
    role_name: str
    scope_kind: ScopeKind
    node_id: int | None
    scope_label: str


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    kind: str  # "redirect", "ambient" or "negotiate"


class PersonAdminOut(BaseModel):
    id: int
    name: str
    job_title: str | None
    org_node_id: int | None
    hue: int
    work_minutes: list[int]
    status: UserStatus
    created_at: datetime
    availability: list[AvailabilityOut]
    # Sign-in and rights: only for callers who hold users.manage (None / empty otherwise).
    username: str | None = None
    email: str | None = None
    has_password: bool = False
    must_change_password: bool = False
    last_login_at: datetime | None = None
    assignments: list[AssignmentOut] = []
    identities: list[ExternalIdentityOut] = []


class SignInUpdate(BaseModel):
    """Prepare or change how a person signs in. `null` clears a value (`username` too: without
    a username there is no password sign-in)."""

    username: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=254)


class PasswordReset(BaseModel):
    password: str | None = Field(default=None, max_length=1000)


class PasswordResetOut(BaseModel):
    generated_password: str | None  # shown once when the server chose it


class StatusIn(BaseModel):
    status: UserStatus


class PermissionInfo(BaseModel):
    value: Permission
    scoped: bool
    description: str


class RoleOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    is_builtin: bool
    permissions: list[Permission]
    assignment_count: int
    default_grant_count: int


class RoleCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,49}$")
    name: Name100
    description: str = Field(default="", max_length=1000)
    permissions: list[Permission] = []


class RoleUpdate(BaseModel):
    name: Name100 | None = None
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[Permission] | None = None


class DefaultGrantIn(ScopeIn):
    audience: Audience
    role_key: str = Field(min_length=1, max_length=50)


class DefaultGrantOut(BaseModel):
    id: int
    audience: Audience
    role_key: str
    role_name: str
    scope_kind: ScopeKind
    node_id: int | None
    scope_label: str


class AuditEntryOut(BaseModel):
    id: int
    at: datetime
    actor_id: int | None
    actor: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
