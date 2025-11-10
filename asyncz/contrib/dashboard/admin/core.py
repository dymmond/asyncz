from __future__ import annotations

from lilya.apps import ChildLilya, Lilya
from lilya.middleware.base import DefineMiddleware
from lilya.middleware.base import Middleware as LilyaMiddleware
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
    """
    A configurable wrapper for the Asyncz web dashboard and management API.

    This class handles the creation of a private `ChildLilya` application, configures
    CORS, session management, and optional authentication (via AuthGateMiddleware),
    and exposes a method to mount itself onto a parent Lilya application.
    """

    def __init__(
        self,
        enable_login: bool = False,
        backend: AuthBackend | None = None,
        url_prefix: str | None = None,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        """
        Initializes the Asyncz Admin dashboard instance.

        Args:
            enable_login: If True, enables session and authentication middleware, requiring a `backend`.
            backend: The authentication backend implementing `AuthBackend` methods (required if `enable_login` is True).
            url_prefix: The base URL path where the dashboard should be mounted (e.g., "/asyncz").
                        Defaults to the value from `monkay.settings.dashboard_config`.
            scheduler: The active `AsyncIOScheduler` instance to manage. If None, a new
                       default scheduler is created (in-memory store).

        Raises:
            ValueError: If `enable_login` is True but no `backend` is provided.
        """
        if enable_login and not backend:
            raise ValueError("`backend` must not be `None` when enable login is True")

        # Resolve defaults
        config = monkay.settings.dashboard_config
        self.url_prefix: str = (url_prefix or config.dashboard_url_prefix).rstrip("/")
        self.scheduler: AsyncIOScheduler = scheduler or AsyncIOScheduler(
            stores={"default": {"type": "memory"}}
        )

        self.enable_login: bool = enable_login
        self.backend: AuthBackend = backend  # type: ignore[assignment]

        # Build the internal ChildLilya application immediately
        self.child_app: ChildLilya = self._build_child()

    def _build_child(self) -> ChildLilya:
        """
        Constructs the internal `ChildLilya` application with all necessary middlewares
        and routes (dashboard, login/logout).

        Returns:
            The fully configured `ChildLilya` application instance.
        """
        config = monkay.settings.dashboard_config

        # 1. Base Middleware Setup (CORS, Session, AuthGate)
        middlewares: list[LilyaMiddleware] = [
            DefineMiddleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                allow_credentials=True,
            ),
            config.session_middleware,
        ]

        if self.enable_login:
            # Append AuthGateMiddleware if login is enabled
            middlewares.append(
                DefineMiddleware(
                    AuthGateMiddleware,
                    authenticate=self.backend.authenticate,
                    login_path="/login",
                    allowlist=("/login", "/logout", "/static", "/assets"),
                )
            )

        # 2. Route Setup (Login/Logout, Dashboard)
        routes: list[Path | Include] = []
        if self.enable_login:
            # Define login and logout endpoints using the configured backend
            async def login(request: Request) -> Response:
                """Handler to delegate to the backend's login logic."""
                return await self.backend.login(request)

            async def logout(request: Request) -> Response:
                """Handler to delegate to the backend's logout logic."""
                return await self.backend.logout(request)

            login_logout: list[Path] = [
                Path("/login", login, methods=["GET", "POST"]),
                Path("/logout", logout, methods=["GET", "POST"]),
            ]
            routes.extend(login_logout)

        # Mount the core dashboard application
        routes.append(
            Include(
                "/",
                app=create_dashboard_app(scheduler=self.scheduler),
            )
        )

        # 3. Create the ChildLilya app
        app: ChildLilya = ChildLilya(
            middleware=middlewares,
            routes=routes,
        )

        return app

    def include_in(self, app: Lilya) -> None:
        """
        Mounts the dashboard's internal `ChildLilya` application onto a parent `Lilya` application.

        Args:
            app: The host `Lilya` application instance.
        """
        app.add_child_lilya(self.url_prefix, self.child_app)
