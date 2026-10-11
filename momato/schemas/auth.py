"""Shapes for login, password change and the current-user ("me") document."""

from typing import Self

from pydantic import BaseModel, Field

from momato.domain.access import Permission
from momato.identity.principal import Principal
from momato.identity.providers import IdentityProviders
from momato.schemas.tokens import TokenInfo


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1000)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=1000)
    new_password: str = Field(max_length=1000)


class PermissionReach(BaseModel):
    """Where a permission applies. The frontend uses this to show or hide controls only; the
    server enforces every rule itself."""

    everywhere: bool
    node_ids: list[int]


class LoginProvider(BaseModel):
    name: str
    display_name: str


class WindowsLogin(BaseModel):
    automatic: bool  # the page tries it by itself when it loads, without being asked


class LoginOptions(BaseModel):
    password: bool
    providers: list[LoginProvider]
    # Windows sign-in by the app itself (POST /api/auth/windows), when it is switched on.
    windows: WindowsLogin | None = None


class Me(BaseModel):
    id: int
    person_id: int | None  # the person's id; None for the anonymous visitor and system accounts
    username: str | None
    name: str
    job_title: str | None
    org_node_id: int | None
    department_id: int | None
    is_anonymous: bool
    is_system: bool
    must_change_password: bool
    # The display name of the proxy sign-in that identifies this person on every request, if any
    # (e.g. "Windows sign-in"); such people cannot log out (SH-7).
    signed_in_by: str | None = None
    # The API token this request came with, if any: its name and scope (TOK-1).
    api_token: TokenInfo | None = None
    permissions: dict[Permission, PermissionReach]
    login: LoginOptions

    @classmethod
    def build(cls, principal: Principal, providers: IdentityProviders) -> Self:
        permissions: dict[Permission, PermissionReach] = {}
        for permission in Permission:
            reach = principal.reach(permission)
            permissions[permission] = PermissionReach(
                everywhere=reach.everywhere, node_ids=sorted(reach.node_ids)
            )
        return cls(
            id=principal.user_id,
            person_id=None if principal.is_anonymous or principal.is_system else principal.user_id,
            username=principal.username,
            name=principal.name,
            job_title=principal.job_title,
            org_node_id=principal.org_node_id,
            department_id=principal.department_id,
            is_anonymous=principal.is_anonymous,
            is_system=principal.is_system,
            must_change_password=principal.must_change_password,
            signed_in_by=next(
                (p.display_name for p in providers.ambient if p.name == principal.ambient_provider),
                None,
            ),
            api_token=TokenInfo(name=principal.token_name or "", scope=principal.token_scope)
            if principal.token_id is not None and principal.token_scope is not None
            else None,
            permissions=permissions,
            login=LoginOptions(
                password=True,
                providers=[
                    LoginProvider(name=p.name, display_name=p.display_name)
                    for p in providers.redirect.values()
                ],
                windows=WindowsLogin(automatic=providers.negotiate.automatic)
                if providers.negotiate
                else None,
            ),
        )
