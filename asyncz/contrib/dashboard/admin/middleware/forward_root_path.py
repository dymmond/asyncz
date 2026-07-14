from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from lilya.types import ASGIApp, Receive, Scope, Send

DEFAULT_TRUSTED_FORWARD_CLIENTS: tuple[str, ...] = ("127.0.0.1", "::1", "localhost")


class ForwardedPrefixMiddleware:
    """
    ASGI middleware that records the external root path based on the
    `X-Forwarded-Prefix` header provided by a reverse proxy (like Nginx).

    Lilya uses ``root_path`` during route matching and ``app_root_path`` when
    generating absolute URLs. Reverse proxies usually strip the external prefix
    before forwarding the request, so this middleware leaves route matching alone
    and only sets ``app_root_path`` for URL generation.
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: bytes = b"x-forwarded-prefix",
        trusted_hosts: Iterable[str] = DEFAULT_TRUSTED_FORWARD_CLIENTS,
    ) -> None:
        """
        Initializes the middleware.

        Args:
            app: The next ASGI application in the stack.
            header_name: The byte string name of the HTTP header to check for the prefix.
                         Defaults to `b"x-forwarded-prefix"`.
            trusted_hosts: Client hosts or networks allowed to set the forwarded prefix.
                           Use `("*",)` only when another layer already enforces trust.
        """
        self.app: ASGIApp = app
        self.header_name: bytes = header_name
        self.trusted_hosts = tuple(trusted_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point. Processes headers and updates the scope's root_path if necessary.

        Args:
            scope: The ASGI scope dictionary.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] in ("http", "websocket") and self._is_trusted(scope):
            # Normalize headers to a dictionary for easy, case-insensitive lookup
            headers: dict[bytes, bytes] = {k.lower(): v for k, v in scope.get("headers", [])}

            prefix_bytes: bytes | None = headers.get(self.header_name.lower())

            if prefix_bytes:
                # Decode and strip the prefix value
                p: str = prefix_bytes.decode("latin-1").strip()

                if p and p != "/":
                    # 1. Ensure leading slash (e.g., 'base' -> '/base')
                    if not p.startswith("/"):
                        p = "/" + p

                    # 2. Strip trailing slash unless it's just '/'
                    if p != "/":
                        p = p.rstrip("/")

                    # 3. Combine with any existing external root path
                    existing: str = scope.get("app_root_path") or scope.get("root_path") or ""

                    # Ensure existing external prefix also has a leading slash
                    if existing and not existing.startswith("/"):
                        existing = "/" + existing

                    # Concatenate and clean up trailing slash (result is either '/base' or '/')
                    combined: str = (p + existing).rstrip("/") or "/"

                    # 4. Create a copy of the scope and update URL generation metadata
                    scope = dict(scope)
                    scope["app_root_path"] = combined

        # Pass control to the next application
        await self.app(scope, receive, send)

    def _is_trusted(self, scope: Scope) -> bool:
        if "*" in self.trusted_hosts:
            return True

        client = scope.get("client")
        client_host = str(client[0]) if isinstance(client, (list, tuple)) and client else ""
        if not client_host:
            return False
        if client_host in self.trusted_hosts:
            return True

        try:
            client_ip = ipaddress.ip_address(client_host)
        except ValueError:
            return False

        for value in self.trusted_hosts:
            try:
                if client_ip in ipaddress.ip_network(value, strict=False):
                    return True
            except ValueError:
                continue
        return False
