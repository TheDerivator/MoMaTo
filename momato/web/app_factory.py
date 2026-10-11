"""`create_app()`: assembles the FastAPI application from settings, API routers and static files."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

from momato import __version__
from momato.api import build_api_router
from momato.api.client import ForwardedHeadersMiddleware, TrustedProxies
from momato.api.errors import install_error_handlers
from momato.config import Environment, Settings, get_settings
from momato.db.session import Database
from momato.identity.providers import IdentityProviders
from momato.services.profile import load_profile
from momato.services.setup import prepare_database
from momato.web.csrf import CSRFMiddleware
from momato.web.frontend import mount_frontend, render_index
from momato.web.security import SecurityHeadersMiddleware, content_security_policy

logger = logging.getLogger("momato")


def _announce_generated_password(password: str) -> None:
    logger.warning(
        "Created the built-in 'admin' account with password: %s  (it must be changed at first "
        "login; set MOMATO_INITIAL_ADMIN_PASSWORD to choose it yourself)",
        password,
    )


def create_app(
    settings: Settings | None = None, providers: IdentityProviders | None = None
) -> FastAPI:
    """Build a fully wired application. Tests pass their own settings and SSO providers."""
    settings = settings or get_settings()
    providers = providers if providers is not None else IdentityProviders.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        database = Database(settings.resolved_database_url)
        if settings.auto_migrate:
            admin_password = settings.initial_admin_password
            report = prepare_database(
                database,
                initial_admin_password=admin_password.get_secret_value()
                if admin_password
                else None,
            )
            if report.generated_admin_password:
                _announce_generated_password(report.generated_admin_password)
        app.state.database = database
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(
        title="MoMaTo",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.identity_providers = providers
    install_error_handlers(app)
    app.state.profile = load_profile(settings.profile)  # a broken profile stops the start
    base_path = settings.normalized_base_path
    development = settings.environment is Environment.DEVELOPMENT
    policy = content_security_policy(render_index(base_path))
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # REQUIREMENTS 8.5: over 1 kB
    app.add_middleware(CSRFMiddleware, cookie_secure=settings.cookie_secure)
    app.add_middleware(
        SecurityHeadersMiddleware,
        # In development index.html is re-read per request, so its script hashes are too.
        policy=(lambda: content_security_policy(render_index(base_path)))
        if development
        else (lambda: policy),
    )
    # Added last, so it runs first: everything after it sees the real client and scheme.
    app.add_middleware(ForwardedHeadersMiddleware, trusted=TrustedProxies(settings.trusted_proxies))
    app.include_router(build_api_router(providers), prefix="/api")
    mount_frontend(app, base_path=base_path, reload_index=development)
    return app
