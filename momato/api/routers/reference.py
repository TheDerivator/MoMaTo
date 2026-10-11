"""The bootstrap endpoint: reference data for the whole app, never projects (SH-12)."""

from fastapi import APIRouter

from momato.api.deps import AppProfile, AppSettings, DbSession, Providers, UsablePrincipal
from momato.schemas.reference import Bootstrap
from momato.services.reference import build_bootstrap

router = APIRouter(tags=["reference"])


@router.get("/bootstrap")
def bootstrap(
    session: DbSession,
    principal: UsablePrincipal,
    profile: AppProfile,
    providers: Providers,
    settings: AppSettings,
) -> Bootstrap:
    """Who I am, today, the org tree, people, statuses, plans and the deployment profile."""
    return build_bootstrap(session, principal, profile, providers, today=settings.current_date())
