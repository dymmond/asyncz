from __future__ import annotations

from functools import cached_property
from typing import Any, cast

from lilya.apps import ChildLilya, Lilya
from lilya.middleware.base import DefineMiddleware
from lilya.middleware.cors import CORSMiddleware
from lilya.requests import Request
from lilya.responses import Response
from lilya.routing import Include, Path, Router
from lilya.types import ASGIApp

from asyncz import monkay
from asyncz.contrib.dashboard import create_dashboard_app
from asyncz.contrib.dashboard.admin.middleware import AuthGateMiddleware
from asyncz.contrib.dashboard.admin.middleware.forward_root_path import (
    ForwardedPrefixMiddleware,
)
from asyncz.contrib.dashboard.admin.protocols import AuthBackend
from asyncz.contrib.dashboard.engine import templates
from asyncz.contrib.dashboard.logs.storage import LogStorage
from asyncz.schedulers.asyncio import AsyncIOScheduler


async def not_found(request: Request, exc: Exception) -> Any:
    return templates.get_template_response(
        request,
        "404.html",
        context={
            "title": "Not Found",
            "url_prefix": monkay.settings.dashboard_config.dashboard_url_prefix,
        },
        status_code=404,
    )


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
        enable_forward_middleware: bool = False,
        url_prefix: str | None = None,
        scheduler: AsyncIOScheduler | None = None,
        include_session: bool = True,
        include_cors: bool = True,
        login_path: str = "/login",
        allowlist: tuple[str, ...] = ("/login", "/logout", "/static", "/assets"),
        log_storage: LogStorage | None = None,
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
        self.config = monkay.settings.dashboard_config
        self.url_prefix: str = (url_prefix or self.config.dashboard_url_prefix).rstrip("/")
        self.scheduler: AsyncIOScheduler = scheduler or AsyncIOScheduler(
            stores={"default": {"type": "memory"}}
        )

        assert self.url_prefix.startswith("/"), "The dashboard url prefix must start with /."

        self.enable_login: bool = enable_login
        self.backend: AuthBackend = backend  # type: ignore[assignment]
        self.enable_forward_middleware = enable_forward_middleware

        # Extras
        self.include_session = include_session
        self.include_cors = include_cors
        self.login_path = login_path
        self.allowlist = allowlist

        # Build the internal dashboard routing application immediately
        self.log_storage: LogStorage | None = log_storage
        self.child_app: Router = self.assemble_dashboard_router()

    def add_sign_in_pages(self) -> list[Path | Include]:
        """
        Defines and registers the routes required for user login and logout pages.

        This function delegates the core logic for rendering the form (GET) and processing
        credentials/clearing sessions (POST) to the configured authentication backend (`self.backend`).

        Returns:
            A list of `Path` objects for the `/login` and `/logout` endpoints, ready
            to be included in the application's routing table.
        """
        # The list of routes to be returned
        routes: list[Path | Include] = []

        # Assert self has backend attribute (required by logic)
        backend: AuthBackend = self.backend

        async def login(request: Request) -> Response:
            """
            Handler for the `/login` route. Delegates GET (form rendering) and
            POST (credential processing) to the authentication backend.
            """
            return await backend.login(request)

        async def logout(request: Request) -> Response:
            """
            Handler for the `/logout` route. Delegates the session clearing logic
            to the authentication backend.
            """
            return await backend.logout(request)

        # 1. Add /login route
        routes.append(Path("/login", login, methods=["GET", "POST"], name="login"))

        # 2. Add /logout route
        routes.append(Path("/logout", logout, methods=["GET", "POST"], name="logout"))

        return routes

    @cached_property
    def cors_middleware(self) -> DefineMiddleware:
        """
        Creates and caches the necessary middleware definition for handling HTTP requests,
        specifically configuring **Cross-Origin Resource Sharing (CORS)**.

        This property returns a single `DefineMiddleware` instance configured to be highly
        permissive for development environments (`allow_origins=["*"]`, etc.).

        The result is cached using `@cached_property`, meaning the configuration dictionary
        is generated only once per object instance.

        Returns:
            DefineMiddleware: The fully configured middleware definition for CORS.
                              (Though the type hint is often simplified to list[DefineMiddleware]
                              in the consuming context, the property returns a single instance).
        """
        return DefineMiddleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    @cached_property
    def auth_gate_middleware(self) -> DefineMiddleware:
        """
        Creates and caches the necessary middleware definition for enforcing authentication
        across the dashboard application.

        This middleware uses the configured `self.backend`'s `authenticate` method to
        verify the user's credentials on every request, redirecting unauthorized users
        to `self.login_path`, unless the path is in `self.allowlist`.

        The result is cached using `@cached_property`, ensuring the middleware definition
        is constructed only once per object instance.

        Returns:
            DefineMiddleware: The fully configured authentication gate middleware definition.
        """
        return DefineMiddleware(
            AuthGateMiddleware,
            authenticate=self.backend.authenticate,
            login_path=self.login_path,
            allowlist=self.allowlist,
        )

    def assemble_dashboard_router(self) -> Router:
        """
        Constructs the internal `ChildLilya` application with all necessary middlewares
        and routes (dashboard, login/logout).

        Returns:
            The fully configured `ChildLilya` application instance.
        """
        # 1. Create the router app
        app: Router = Router(
            routes=[
                Include(
                    "/",
                    app=create_dashboard_app(
                        scheduler=self.scheduler, log_storage=self.log_storage
                    ),
                ),
            ],
        )

        return app

    def include_in(self, app: Lilya) -> None:
        """
        Mount the composed dashboard app at the host root.

        The composed app (built with `with_url_prefix=True`) already:
          - mounts the dashboard router under `self.url_prefix` (e.g., /dashboard)
          - exposes root-level `/login` and `/logout` routes
        So mounting it at "/" yields the desired final URLs:
          - /login, /logout
          - {self.url_prefix}/...
        """
        composed: ASGIApp = self.get_asgi_app(with_url_prefix=True)
        app.add_child_lilya("/", cast(ChildLilya, composed))

    def get_asgi_app(self, with_url_prefix: bool = False) -> ASGIApp | Lilya | ChildLilya:
        """
        Constructs and returns the final, self-contained ASGI application for the dashboard,
        complete with nested routing, middleware, and authentication gates.

        Args:
            self: The instance of the class (e.g., AsynczAdmin) holding the configuration.
            with_url_prefix: If `True`, mounts the application under `self.url_prefix`.
                             If `False` (default), mounts it directly under the root `/`.

        Returns:
            ASGIApp | Lilya | ChildLilya: The top-level `Lilya` application instance, ready to be served.
        """
        # Determine the base path for mounting the application's internal routes
        base: str = self.url_prefix if with_url_prefix else "/"
        base_norm = "/" if base == "/" else base.rstrip("/")

        # 1. Build Inner Routes (Dashboard Core + Auth Pages)
        inner_routes: list[Path | Include] = [
            Include("/", app=self.child_app)  # Mount the core dashboard routes
        ]

        # 2. Build Top-Level Routes (Mounting everything under the final prefix)
        routes: list[Path | Include] = [
            Include(path=base_norm, routes=inner_routes, name="dashboard")
        ]
        if self.enable_login:
            # Add /login and /logout handlers if authentication is enabled at root level
            routes.extend(self.add_sign_in_pages())

        # 3. Build Middleware Stack (Order is critical)
        middlewares: list[DefineMiddleware] = []

        if self.enable_forward_middleware:
            # X-Forwarded-Prefix handling (useful if mounted via proxy)
            middlewares.append(DefineMiddleware(ForwardedPrefixMiddleware))

        if self.include_cors:
            # CORS handling
            middlewares.append(self.cors_middleware)

        if self.include_session:
            # Session handling (required for SimpleUsernamePasswordBackend)
            middlewares.append(self.config.session_middleware)

        if self.enable_login:
            # Authentication enforcement
            middlewares.append(self.auth_gate_middleware)

        # 4. Create Final Lilya Application
        return cast(
            ASGIApp,
            Lilya(
                routes=routes,
                middleware=middlewares,
                exception_handlers={404: not_found},
            ),
        )
