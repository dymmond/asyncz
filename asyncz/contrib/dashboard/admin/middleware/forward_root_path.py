from __future__ import annotations

from lilya.types import ASGIApp, Receive, Scope, Send


class ForwardedPrefixMiddleware:
    """
    ASGI middleware that automatically updates the `scope['root_path']` based on the
    `X-Forwarded-Prefix` header provided by a reverse proxy (like Nginx).

    This ensures that internal framework components, such as `url_for()` and `StaticFiles`,
    generate correct absolute URLs that include the proxy's mount prefix (e.g., /base/static).
    """

    def __init__(self, app: ASGIApp, header_name: bytes = b"x-forwarded-prefix"):
        """
        Initializes the middleware.

        Args:
            app: The next ASGI application in the stack.
            header_name: The byte string name of the HTTP header to check for the prefix.
                         Defaults to `b"x-forwarded-prefix"`.
        """
        self.app: ASGIApp = app
        self.header_name: bytes = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        The ASGI entry point. Processes headers and updates the scope's root_path if necessary.

        Args:
            scope: The ASGI scope dictionary.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] in ("http", "websocket"):
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

                    # 3. Combine with any existing root_path
                    existing: str = scope.get("root_path") or ""

                    # Ensure existing root_path also has a leading slash
                    if existing and not existing.startswith("/"):
                        existing = "/" + existing

                    # Concatenate and clean up trailing slash (result is either '/base' or '/')
                    combined: str = (p + existing).rstrip("/") or "/"

                    # 4. Create a copy of the scope and update root_path
                    scope = dict(scope)
                    scope["root_path"] = combined

        # Pass control to the next application
        await self.app(scope, receive, send)
