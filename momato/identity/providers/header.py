"""SSO through a trusted reverse proxy that authenticates users and passes them in headers.

Typical: IIS with Windows authentication forwards `CORP\\jdoe` in a header such as X-Remote-User.
Headers are only believed when the request comes through a trusted proxy
(MOMATO_TRUSTED_PROXIES); the app must not be reachable around the proxy, and the proxy must
overwrite these headers on every request.
"""

import logging
from collections.abc import Mapping
from typing import Self

from momato.config import Settings
from momato.identity.providers.base import ExternalIdentity

logger = logging.getLogger("momato.sso")


class TrustedHeaderProvider:
    name = "proxy"
    display_name = "Windows sign-in"

    def __init__(
        self,
        *,
        user_header: str,
        email_header: str | None = None,
        name_header: str | None = None,
        groups_header: str | None = None,
        strip_domain: bool = True,
    ) -> None:
        self.user_header = user_header
        self.email_header = email_header
        self.name_header = name_header
        self.groups_header = groups_header
        self.strip_domain = strip_domain
        self._warned = False

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if not settings.trusted_header:
            raise ValueError("MOMATO_TRUSTED_HEADER is not set")
        return cls(
            user_header=settings.trusted_header,
            email_header=settings.trusted_header_email,
            name_header=settings.trusted_header_name,
            groups_header=settings.trusted_header_groups,
            strip_domain=settings.trusted_header_strip_domain,
        )

    def identify(self, headers: Mapping[str, str], proxy: str | None) -> ExternalIdentity | None:
        raw = (headers.get(self.user_header) or "").strip()
        if not raw:
            return None
        if proxy is None:  # anyone could send the header; only the proxy is believed
            self._warn_once()
            return None
        login = raw.split("\\")[-1] if self.strip_domain else raw
        groups_raw = headers.get(self.groups_header, "") if self.groups_header else ""
        return ExternalIdentity(
            provider=self.name,
            subject=raw.lower(),
            email=(headers.get(self.email_header) or None) if self.email_header else None,
            display_name=(headers.get(self.name_header) or None) if self.name_header else None,
            groups=tuple(g.strip() for g in groups_raw.split(",") if g.strip()),
            username=login.lower(),
        )

    def _warn_once(self) -> None:
        if self._warned:
            return
        self._warned = True
        logger.warning(
            "Ignored the %s header of a request that did not come through a trusted proxy "
            "(MOMATO_TRUSTED_PROXIES). If the proxy is listed there, Uvicorn may have replaced "
            "its address: run `python -m momato serve`, or uvicorn with --no-proxy-headers.",
            self.user_header,
        )
