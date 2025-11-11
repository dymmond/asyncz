import secrets
from dataclasses import dataclass
from typing import Literal

from lilya.requests import Request

try:
    from lilya.middleware import DefineMiddleware
    from lilya.middleware.sessions import SessionMiddleware
except ImportError:
    raise ModuleNotFoundError(
        "The dashboard functionality requires the 'lilya' package. "
        "Please install it with 'pip install lilya'."
    ) from None

from asyncz import monkay


@dataclass
class DashboardConfig:
    """
    Command center for the Dashboard configuration.

    This class holds all settings related to the dashboard's appearance, routing,
    and stateful security, primarily managed through session cookies.
    """

    # --- Display Settings ---

    title: str = "Dashboard"
    """The title displayed in the browser tab/window header."""

    header_title: str = "Asyncz "
    """The main title displayed within the dashboard application header."""

    description: str = "A simple dashboard for monitoring Asyncz tasks."
    """A brief description of the dashboard's purpose."""

    favicon: str = (
        "https://raw.githubusercontent.com/dymmond/asyncz/refs/heads/main/docs/statics/favicon.ico"
    )
    """URL path or external URL for the favicon."""

    dashboard_url_prefix: str = "/dashboard"
    """The base URL prefix where the dashboard is mounted in the host application."""

    sidebar_bg_colour: str = "#f06824"
    """The CSS color value for the sidebar background."""

    secret_key: str | None = None
    """
    The cryptographic key used to sign the session cookie. Must be kept secret.
    If `None`, a secure key is generated automatically on first access.
    """

    session_cookie: str = "asyncz_admin"
    """The name of the session cookie to be set on the client."""

    max_age: int | None = 14 * 24 * 60 * 60  # 14 days, in seconds
    """
    The maximum age (lifetime) of the session cookie in seconds.
    `None` means the cookie expires when the browser closes.
    """

    path: str = "/"
    """The path scope for which the cookie is valid."""

    same_site: Literal["lax", "strict", "none"] = "lax"
    """Controls when cookies are sent in cross-site requests, balancing security and usability."""

    https_only: bool = False
    """If `True`, the cookie will only be transmitted over HTTPS connections (requires secure context)."""

    domain: str | None = None
    """The domain scope for which the cookie is valid."""

    @property
    def session_middleware(self) -> DefineMiddleware:
        """
        Dynamically creates and returns a `DefineMiddleware` instance configured with the
        necessary `SessionMiddleware` parameters.

        A secure key is generated using `secrets.token_urlsafe` if `secret_key` is `None`.

        Returns:
            A `DefineMiddleware` instance ready to be included in an ASGI application.
        """
        return DefineMiddleware(
            SessionMiddleware,
            secret_key=self.secret_key or secrets.token_urlsafe(32),
            session_cookie=self.session_cookie,
            max_age=self.max_age,
            path=self.path,
            same_site=self.same_site,
            https_only=self.https_only,
            domain=self.domain,
        )


def _normalize_prefix(value: str | None) -> str:
    """Ensure a leading slash and remove trailing slash (except for root)."""
    if not value:
        return "/"
    v = value.strip()
    if not v.startswith("/"):
        v = "/" + v
    return v if v == "/" else v.rstrip("/")


def get_effective_prefix(request: Request | None = None) -> str:
    """Compute the effective base URL prefix for the dashboard.

    - If *request* is **None**, return the configured dashboard prefix exactly as before
      (leading '/', no trailing '/', except when it is '/'). This preserves
      backward compatibility with tests that called the old zero-arg function.
    - If *request* is provided, combine ASGI mount ``root_path`` (if any) with the
      configured prefix, avoiding double-prefixing and double slashes.
    """
    configured_prefix = _normalize_prefix(
        getattr(monkay.settings.dashboard_config, "dashboard_url_prefix", "/")
    )

    # Prefer the configured prefix when it's meaningful (not '/')
    if configured_prefix != "/":
        return configured_prefix

    # Only when configured is '/' do we consider the mount root
    if request is not None:
        scope = getattr(request, "scope", {}) or {}
        mount_prefix = _normalize_prefix(scope.get("root_path") or "/")
        return mount_prefix

    return "/"
