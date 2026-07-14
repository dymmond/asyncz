from __future__ import annotations

from collections.abc import Iterable

from lilya.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        b"img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
        b"object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    ),
    (b"referrer-policy", b"same-origin"),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)


class SecurityHeadersMiddleware:
    """Attach conservative browser security headers to dashboard responses."""

    def __init__(
        self,
        app: ASGIApp,
        headers: Iterable[tuple[bytes, bytes]] = DEFAULT_SECURITY_HEADERS,
    ) -> None:
        self.app = app
        self.headers = tuple(headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _value in message.get("headers", [])}
                message_headers = list(message.get("headers", []))
                for name, value in self.headers:
                    if name not in existing:
                        message_headers.append((name, value))
                if scope.get("scheme") == "https" and b"strict-transport-security" not in existing:
                    message_headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = message_headers

            await send(message)

        await self.app(scope, receive, send_with_headers)
