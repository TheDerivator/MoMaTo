"""HTTP API layer: thin FastAPI routers, request dependencies, error mapping. Mounted at `/api`."""

from fastapi import APIRouter

from momato.api.routers import (
    account,
    admin,
    auth,
    exports,
    meta,
    people_planning,
    plans,
    projects,
    reference,
    remarks,
    search,
    sso,
    timesheet,
    tokens,
    windows,
)
from momato.identity.providers import IdentityProviders


def build_api_router(providers: IdentityProviders | None = None) -> APIRouter:
    """Collect every API router; the web layer mounts the result under `/api`.

    SSO sign-in routes exist only when a provider is configured (M12): without configuration no
    SSO route exists (AUTH-3).
    """
    router = APIRouter()
    router.include_router(meta.router)
    router.include_router(auth.router)
    router.include_router(reference.router)
    router.include_router(projects.router)
    router.include_router(plans.router)
    router.include_router(remarks.router)
    router.include_router(search.router)
    router.include_router(timesheet.router)
    router.include_router(people_planning.router)
    router.include_router(exports.router)
    router.include_router(admin.router)
    router.include_router(account.router)
    router.include_router(tokens.router)
    if providers is not None and providers.redirect:
        router.include_router(sso.router)
    if providers is not None and providers.negotiate is not None:
        router.include_router(windows.router)
    return router
