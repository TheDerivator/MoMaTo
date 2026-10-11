"""FastAPI dependencies: one DB session per request, the current principal, and services.

Requests with unsafe methods (POST, PUT, PATCH, DELETE) get a write session. Services commit
explicitly; whatever they leave uncommitted is rolled back when the session closes.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from momato.api.client import client_ip, proxy_host
from momato.config import Settings
from momato.db.session import Database
from momato.domain.access import Permission, TokenScope
from momato.domain.errors import (
    AuthenticationRequiredError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from momato.domain.fields import Profile
from momato.identity import api_tokens
from momato.identity.principal import Principal
from momato.identity.providers import IdentityProviders
from momato.identity.sessions import SESSION_COOKIE
from momato.services.access import AccessService
from momato.services.account import AccountService
from momato.services.attachments import AttachmentStore
from momato.services.auth import AuthService
from momato.services.exports import ExportService
from momato.services.org_admin import OrgAdminService
from momato.services.people_admin import PeopleAdminService
from momato.services.people_planning import PeoplePlanningService
from momato.services.planning import PlanningService
from momato.services.plans import PlanService
from momato.services.projects import ProjectService
from momato.services.remarks import RemarkService
from momato.services.search import SearchService
from momato.services.sso import SsoService
from momato.services.tasks import TaskService
from momato.services.timesheet import TimesheetService
from momato.services.tokens import TokenService

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_providers(request: Request) -> IdentityProviders:
    return request.app.state.identity_providers


def get_db_session(request: Request) -> Generator[Session]:
    database: Database = request.app.state.database
    with database.new_session(write=request.method not in SAFE_METHODS) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Providers = Annotated[IdentityProviders, Depends(get_providers)]


def get_auth_service(
    session: DbSession, settings: AppSettings, providers: Providers
) -> AuthService:
    return AuthService(session, settings, providers)


Auth = Annotated[AuthService, Depends(get_auth_service)]


def bearer_token(request: Request) -> str | None:
    """The API token of `Authorization: Bearer <token>`, if the request carries one."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    return credentials.strip() if scheme.lower() == "bearer" else None


def get_principal(request: Request, auth: Auth) -> Principal:
    principal = auth.principal_for_request(
        session_token=request.cookies.get(SESSION_COOKIE),
        api_token=bearer_token(request),
        headers=request.headers,
        proxy=proxy_host(request),
    )
    if principal.token_id is None:
        return principal
    if principal.token_scope is TokenScope.READ and request.method not in SAFE_METHODS:
        raise PermissionDeniedError("this API token is read only")
    if api_tokens.due_for_touch(principal):
        ip = client_ip(request)
        if request.method in SAFE_METHODS:
            # A reading request has a reading session: note the use in a short write of its own.
            database: Database = request.app.state.database
            with database.session(write=True) as session:
                api_tokens.touch(session, principal.token_id, ip_address=ip)
        else:
            api_tokens.touch(auth.session, principal.token_id, ip_address=ip)  # saved with the rest
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def get_usable_principal(principal: CurrentPrincipal) -> Principal:
    """The caller of a data endpoint: a visitor who may see nothing is told to sign in (401),
    and a person who must change their password may do nothing else (403)."""
    if principal.must_change_password:
        raise PasswordChangeRequiredError("set a new password first")
    if principal.is_anonymous and not principal.can_somewhere(Permission.PROJECT_VIEW):
        raise AuthenticationRequiredError("log in to use MoMaTo")
    return principal


UsablePrincipal = Annotated[Principal, Depends(get_usable_principal)]


def get_profile(request: Request) -> Profile:
    return request.app.state.profile


AppProfile = Annotated[Profile, Depends(get_profile)]


def get_project_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> ProjectService:
    return ProjectService(
        session, principal, profile, today=settings.current_date(), uploads_dir=settings.uploads_dir
    )


def get_task_service(
    session: DbSession, principal: UsablePrincipal, settings: AppSettings
) -> TaskService:
    return TaskService(session, principal, today=settings.current_date())


def get_planning_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> PlanningService:
    return PlanningService(session, principal, profile, today=settings.current_date())


def get_plan_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> PlanService:
    return PlanService(session, principal, profile, today=settings.current_date())


def get_remark_service(
    session: DbSession, principal: UsablePrincipal, settings: AppSettings
) -> RemarkService:
    return RemarkService(session, principal, AttachmentStore(settings.uploads_dir))


def get_people_planning_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> PeoplePlanningService:
    return PeoplePlanningService(session, principal, profile, today=settings.current_date())


def get_timesheet_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> TimesheetService:
    return TimesheetService(session, principal, profile, today=settings.current_date())


def get_search_service(session: DbSession, principal: UsablePrincipal) -> SearchService:
    return SearchService(session, principal)


def get_org_admin_service(session: DbSession, principal: UsablePrincipal) -> OrgAdminService:
    return OrgAdminService(session, principal)


def get_people_admin_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> PeopleAdminService:
    return PeopleAdminService(session, principal, profile, today=settings.current_date())


def get_account_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> AccountService:
    return AccountService(session, principal, profile, today=settings.current_date())


def get_export_service(
    session: DbSession, principal: UsablePrincipal, profile: AppProfile, settings: AppSettings
) -> ExportService:
    return ExportService(session, principal, profile, today=settings.current_date())


def get_sso_service(session: DbSession, settings: AppSettings, providers: Providers) -> SsoService:
    return SsoService(session, settings, providers)


def get_token_service(session: DbSession, principal: CurrentPrincipal) -> TokenService:
    return TokenService(session, principal)


def get_access_service(session: DbSession, principal: UsablePrincipal) -> AccessService:
    return AccessService(session, principal)


Projects = Annotated[ProjectService, Depends(get_project_service)]
Tasks = Annotated[TaskService, Depends(get_task_service)]
Planning = Annotated[PlanningService, Depends(get_planning_service)]
Plans = Annotated[PlanService, Depends(get_plan_service)]
Remarks = Annotated[RemarkService, Depends(get_remark_service)]
Timesheets = Annotated[TimesheetService, Depends(get_timesheet_service)]
PeoplePlans = Annotated[PeoplePlanningService, Depends(get_people_planning_service)]
Search = Annotated[SearchService, Depends(get_search_service)]
OrgAdmin = Annotated[OrgAdminService, Depends(get_org_admin_service)]
PeopleAdmin = Annotated[PeopleAdminService, Depends(get_people_admin_service)]
AccessAdmin = Annotated[AccessService, Depends(get_access_service)]
Account = Annotated[AccountService, Depends(get_account_service)]
Tokens = Annotated[TokenService, Depends(get_token_service)]
Exports = Annotated[ExportService, Depends(get_export_service)]
Sso = Annotated[SsoService, Depends(get_sso_service)]
