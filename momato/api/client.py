"""Who is on the other end of a request: the client, and the trusted reverse proxy in between.

The app reads X-Forwarded-For/-Proto itself instead of Uvicorn's --proxy-headers (switched off in
`momato serve`), because it needs both addresses: the client's for login throttling, and the
proxy's to decide whether identity headers (trusted-header SSO) may be believed. Uvicorn replaces
the proxy's address with the client's, after which nobody can tell the proxy was there.
"""

import ipaddress
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

PROXY_KEY = "momato.proxy"  # ASGI scope key: the trusted proxy the request came through
PEER_KEY = "momato.peer"  # ASGI scope key: the (address, port) the connection comes from

type _Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class TrustedProxies:
    """Comma-separated addresses (127.0.0.1), networks (10.0.0.0/8) or host names ("testclient")."""

    def __init__(self, spec: str) -> None:
        self.networks: list[_Network] = []
        self.names: set[str] = set()
        for entry in (e.strip() for e in spec.split(",")):
            if not entry:
                continue
            try:
                self.networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                self.names.add(entry.lower())

    def __contains__(self, host: object) -> bool:
        if not isinstance(host, str) or not host:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return host.lower() in self.names
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped  # ::ffff:127.0.0.1 on dual-stack sockets
        return any(address in network for network in self.networks)


def _host(entry: str) -> str:
    """The address in one X-Forwarded-For entry; IIS ARR appends the port (203.0.113.5:51234)."""
    entry = entry.strip()
    if entry.startswith("["):  # [2001:db8::1]:51234
        return entry[1:].split("]")[0]
    if entry.count(":") == 1:
        return entry.split(":")[0]
    return entry


class ForwardedHeadersMiddleware:
    """Believe X-Forwarded-For/-Proto only from trusted proxies, and remember which proxy it was."""

    def __init__(self, app: ASGIApp, trusted: TrustedProxies) -> None:
        self.app = app
        self.trusted = trusted

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            client: tuple[str, int] | None = scope.get("client")
            scope[PEER_KEY] = client
            if client and client[0] in self.trusted:
                self._apply(scope, client[0])
        await self.app(scope, receive, send)

    def _apply(self, scope: Scope, proxy: str) -> None:
        scope[PROXY_KEY] = proxy
        forwarded_for: list[str] = []
        proto: str | None = None
        headers: list[tuple[bytes, bytes]] = scope["headers"]
        for name, value in headers:
            if name == b"x-forwarded-for":
                forwarded_for.extend(value.decode("latin-1").split(","))
            elif name == b"x-forwarded-proto":
                proto = value.decode("latin-1").split(",")[0].strip().lower()
        if proto in {"http", "https"}:
            scope["scheme"] = proto
        # Each proxy appends the address it received from: the client is the nearest one that is
        # not a proxy of ours. Entries further left could have been sent by the client itself.
        for entry in reversed(forwarded_for):
            host = _host(entry)
            if host and host not in self.trusted:
                scope["client"] = (host, 0)
                break


def client_ip(request: Request) -> str | None:
    """The client's address (behind a trusted proxy: the one the proxy forwarded)."""
    return request.client.host if request.client else None


def connection_id(request: Request) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Names the network connection a request arrived on, the same for all its requests.

    The peer's address and port as the socket saw them (not what X-Forwarded-For claims), plus
    the address they connected to. Windows sign-in's NTLM handshake spans two requests on one
    connection and is remembered under this.
    """
    scope: dict[str, Any] = request.scope  # type: ignore[assignment]
    peer = scope.get(PEER_KEY) or scope.get("client") or ()
    return tuple(peer), tuple(scope.get("server") or ())


def proxy_host(request: Request) -> str | None:
    """The trusted proxy the request came through, or None when it came directly."""
    scope: dict[str, Any] = request.scope  # type: ignore[assignment]
    return scope.get(PROXY_KEY)
