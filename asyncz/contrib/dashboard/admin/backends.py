from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from lilya.requests import Request
from lilya.responses import RedirectResponse, Response

from asyncz.contrib.dashboard.admin.protocols import AuthBackend, User
from asyncz.contrib.dashboard.engine import templates
from asyncz.contrib.dashboard.mixins import default_context


class SimpleUsernamePasswordBackend(AuthBackend):
    def __init__(
        self,
        verify: Callable[[str, str], Optional[User]],
        session_key: str = "asyncz_admin",
        login_template: str = "login.html",
    ) -> None:
        self.verify = verify
        self.session_key = session_key
        self.login_template = login_template

    async def authenticate(self, request: Request) -> Optional[User]:
        data = request.session.get(self.session_key)
        return User(**data) if data else None

    async def login(self, request: Request) -> Response:
        context = default_context(request)

        if request.method == "GET":
            context.update({"next": request.query_params.get("next")})
            return templates.get_template_response(
                request,
                self.login_template,
                context,
            )
        form = await request.form()
        username, password = (form.get("username") or "").strip(), form.get("password") or ""
        user = self.verify(username, password)

        if not user:
            context.update({"error": "Invalid credentials"})
            return templates.get_template_response(request, self.login_template, context)

        request.session[self.session_key] = {
            "id": user.id,
            "name": user.name,
            "is_admin": user.is_admin,
            **user.extra,
        }
        nxt = form.get("next") or "/"
        return RedirectResponse(nxt, status_code=303)

    async def logout(self, request: Request) -> Response:
        request.session.pop(self.session_key, None)
        return RedirectResponse("/login", status_code=303)
