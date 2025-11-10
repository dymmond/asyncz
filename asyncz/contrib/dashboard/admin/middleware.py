from __future__ import annotations

from collections.abc import Callable, Iterable

from lilya.requests import Request
from lilya.responses import PlainText, RedirectResponse, Response
from lilya.types import ASGIApp, Receive, Scope, Send


class AuthGateMiddleware:
    """
    ASGI middleware that enforces authentication for the wrapped child app,
    except for configured allowlisted paths (e.g., /login, /logout, /static/*).
    HTMX-friendly: returns 401 + HX-Redirect header for partial requests.
    """

    def __init__(
        self,
        app: ASGIApp,
        authenticate: Callable,  # request -> Optional[User]
        login_path: str = "/login",
        allowlist: Iterable[str] = ("/login", "/logout", "/static", "/assets"),
    ) -> None:
        self.app = app
        self.authenticate = authenticate
        self.login_path = login_path
        self.allowlist = tuple(allowlist)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # For mounted child apps, root_path is the mount prefix (e.g. "/dashboard")
        mount_prefix = scope.get("root_path", "") or ""
        path = scope.get("path") or "/"

        # Normalize to child-relative path by stripping the mount prefix
        # e.g., path="/dashboard/login" with root_path="/dashboard" -> child_path="/login"
        child_path = path
        if mount_prefix and path.startswith(mount_prefix):
            child_path = path[len(mount_prefix) :] or "/"
        if not child_path.startswith("/"):
            child_path = "/" + child_path

        # Allow-list checks should be done against the child-relative path
        if any(child_path == p or child_path.startswith(p + "/") for p in self.allowlist):
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive)

        user = await self.authenticate(request)
        if user:
            request.state.user = user
            return await self.app(request.scope, receive, send)

        # Unauthenticated: build a redirect URL under the mount prefix
        # e.g. "/dashboard" + "/login" + "?next=/tasks"
        login_url = f"{mount_prefix}{self.login_path}"
        next_q = f"?next={path}"

        if request.headers.get("hx-request") == "true":
            # Use the canonical header casing for htmx; headers are case-insensitive,
            # but this matches docs and avoids surprises.
            response: Response = PlainText(
                "Authentication required",
                status_code=401,
                headers={"HX-Redirect": login_url + next_q},
            )
        else:
            response = RedirectResponse(login_url + next_q, status_code=303)

        await response(scope, receive, send)
