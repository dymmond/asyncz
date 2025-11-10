from __future__ import annotations

from lilya.apps import ChildLilya, Lilya
from lilya.middleware.base import DefineMiddleware
from lilya.middleware.cors import CORSMiddleware
from lilya.requests import Request
from lilya.responses import Response
from lilya.routing import Include, Path

from asyncz import monkay
from asyncz.contrib.dashboard import create_dashboard_app
from asyncz.contrib.dashboard.admin.middleware import AuthGateMiddleware
from asyncz.contrib.dashboard.admin.protocols import AuthBackend
from asyncz.schedulers.asyncio import AsyncIOScheduler


class AsynczAdmin:
    def __init__(
        self,
        enable_login: bool = False,
        backend: AuthBackend | None = None,
        url_prefix: str | None = None,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        if enable_login and not backend:
            raise ValueError("`backend` must not be `None` when enable login is True")

        if url_prefix is None:
            url_prefix = monkay.settings.dashboard_config.dashboard_url_prefix

        if scheduler is None:
            scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

        self.enable_login = enable_login
        self.scheduler = scheduler
        self.backend: AuthBackend = backend  # type: ignore
        self.url_prefix = url_prefix.rstrip("/")
        self.child_app = self._build_child()

    def _build_child(self) -> ChildLilya:
        middlewares = [
            DefineMiddleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                allow_credentials=True,
            ),
            monkay.settings.dashboard_config.session_middleware,
        ]

        if self.enable_login:
            middlewares.append(
                DefineMiddleware(
                    AuthGateMiddleware,
                    authenticate=self.backend.authenticate,
                    login_path="/login",
                    allowlist=("/login", "/logout", "/static", "/assets"),
                )
            )

        routes: list[Path | Include] = []
        if self.enable_login:
            # Build login and logout pages
            async def login(request: Request) -> Response:
                return await self.backend.login(request)

            async def logout(request: Request) -> Response:
                return await self.backend.logout(request)

            login_logout = [
                Path("/login", login, methods=["GET", "POST"]),
                Path("/logout", logout, methods=["GET", "POST"]),
            ]
            routes.extend(login_logout)

        routes.append(
            Include(
                "/",
                app=create_dashboard_app(scheduler=self.scheduler),
            )
        )

        app = ChildLilya(
            middleware=middlewares,
            routes=routes,
        )

        return app

    def include_in(self, app: Lilya) -> None:
        app.add_child_lilya(self.url_prefix, self.child_app)
