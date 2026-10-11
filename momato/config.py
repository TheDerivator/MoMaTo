"""Typed application settings, read from environment variables prefixed `MOMATO_` (or `.env`)."""

from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class UnknownUserPolicy(StrEnum):
    """What an SSO sign-in does with someone nobody prepared (AUTH-3)."""

    REJECT = "reject"  # invite-only: only prepared people can sign in
    CREATE = "create"  # create the person without any rights of their own


class Settings(BaseSettings):
    """All runtime configuration. Every field can be set as `MOMATO_<FIELD_NAME>`."""

    model_config = SettingsConfigDict(
        env_prefix="MOMATO_",
        # The app folder's .env, whatever the working directory (Windows services and scheduled
        # tasks start elsewhere). Environment variables take precedence over it.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT

    # Where the SQLite database (by default) and uploaded files live. Keep it outside the code
    # folder in production, e.g. C:\ProgramData\MoMaTo or /var/lib/momato.
    data_dir: Path = PROJECT_ROOT / "var"

    # Any SQLAlchemy URL. Defaults to <data_dir>/momato.sqlite3.
    # MS SQL example: mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server
    database_url: str | None = None

    # Apply migrations and create built-in data at startup. Turn off to manage the schema
    # explicitly with `python -m momato db upgrade` (e.g. with several servers on one database).
    auto_migrate: bool = True

    # Password for the built-in `admin` account when it is first created. When unset, a random
    # password is generated and printed once; the admin must change it at first login.
    initial_admin_password: SecretStr | None = None

    # Session cookies get the Secure flag. Leave unset to decide per request (on when HTTPS).
    cookie_secure: bool | None = None
    session_lifetime_hours: int = 24 * 14

    # Password login throttling: failed attempts allowed per account / per client address within
    # the window. Behind a reverse proxy, list it in `trusted_proxies` so addresses are real.
    login_max_failures_per_user: int = 5
    login_max_failures_per_ip: int = 50
    login_throttle_minutes: int = 15

    # Reverse proxies (addresses or networks, comma-separated) whose X-Forwarded-For/-Proto headers
    # are believed: the client address and scheme then come from them. Also decides who may
    # assert identities for SSO through a trusted header (M12).
    trusted_proxies: str = "127.0.0.1,::1"

    # ---- single sign-on (AUTH-3): opt-in; without these settings no SSO route exists.

    # People who sign in through SSO but were not prepared in advance (by email or Windows login
    # name): rejected, or created without any rights.
    sso_unknown_users: UnknownUserPolicy = UnknownUserPolicy.REJECT

    # OpenID Connect (Microsoft Entra ID): enabled when issuer and client id are both set. The
    # redirect address to register is `<public address>/api/auth/sso/<oidc_name>/callback`.
    oidc_name: str = "entra"  # stored with linked people; don't change once in use
    oidc_display_name: str = "Microsoft"  # the button says "Sign in with <this>"
    oidc_issuer: str | None = None  # e.g. https://login.microsoftonline.com/<tenant>/v2.0
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_scopes: str = "openid profile email"
    oidc_subject_claim: str = "sub"
    oidc_email_claims: str = "email,preferred_username,upn"  # the first one present is used
    oidc_groups_claim: str = "groups"

    # Through a trusted reverse proxy that authenticates people and passes them in headers (e.g.
    # IIS with Windows authentication). Enabled when `trusted_header` names the user header. Only
    # requests that come through one of the `trusted_proxies` may assert identities.
    trusted_header: str | None = None  # e.g. "X-Remote-User" (value like CORP\jdoe)
    trusted_header_email: str | None = None
    trusted_header_name: str | None = None
    trusted_header_groups: str | None = None  # a comma-separated list in one header
    trusted_header_strip_domain: bool = True  # CORP\jdoe becomes the login name "jdoe"

    # Windows sign-in by the app itself (HTTP Negotiate: Kerberos or NTLM, through SSPI); the
    # server must run on Windows, in the domain. No proxy is needed.
    windows_auth: bool = False
    windows_auth_automatic: bool = True  # the page tries it by itself; false: only on request
    windows_auth_strip_domain: bool = True  # CORP\jdoe becomes the login name "jdoe"

    # The deployment profile (D-009): a file momato/profiles/<name>.toml fixing the detail fields,
    # time categories, task template and a few numbers of this deployment.
    profile: str = "default"

    # URL path the app is published under, e.g. "/momato/" behind an IIS or nginx prefix
    # (the proxy strips the prefix before forwarding). Used for the page's <base href>.
    base_path: str = "/"

    # The address people use, e.g. https://momato.example.com/momato (with the base path, no
    # trailing slash needed). When set, it is what SSO callbacks and the agent guide use;
    # otherwise the address of the request is. Set it behind a proxy that rewrites the host.
    public_url: str | None = None

    # Pretend it is this date (YYYY-MM-DD) instead of the server's own (D-027). Tests pin it to
    # Thursday 8 October 2026, ISO week 41, the design's date; frozen demos may too.
    today: date | None = None

    # For `python -m momato serve`.
    host: str = "127.0.0.1"
    port: int = 8000
    # Serve HTTPS directly (both set); usually a reverse proxy does it instead. Windows sign-in
    # and secure cookies want HTTPS.
    tls_certfile: Path | None = None
    tls_keyfile: Path | None = None

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'momato.sqlite3').as_posix()}"

    @property
    def normalized_base_path(self) -> str:
        """`base_path` with exactly one leading and one trailing slash."""
        inner = self.base_path.strip().strip("/")
        return f"/{inner}/" if inner else "/"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    def current_date(self) -> date:
        """Today on the server (in its own time zone), unless `today` pins it."""
        return self.today or date.today()


@lru_cache
def get_settings() -> Settings:
    """Settings from the environment, created once per process."""
    return Settings()
