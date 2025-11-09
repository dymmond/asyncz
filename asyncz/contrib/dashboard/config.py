import secrets
from dataclasses import dataclass
from typing import cast

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
    title: str = "Dashboard"
    header_title: str = "Asyncz "
    description: str = "A simple dashboard for monitoring Asyncz tasks."
    favicon: str = (
        "https://raw.githubusercontent.com/dymmond/asyncz/refs/heads/main/docs/statics/favicon.ico"
    )
    dashboard_url_prefix: str = "/dashboard"
    sidebar_bg_colour: str = "#f06824"
    session_middleware: DefineMiddleware = DefineMiddleware(
        SessionMiddleware, secret_key=secrets.token_hex(32)
    )


def get_effective_prefix() -> str:
    """Compute an absolute dashboard base path, combining ASGI root_path and the
    configured dashboard URL prefix.

    Guarantees:
    - Always starts with '/'
    - No trailing slash (except when the result is exactly '/')
    - Never double-appends the configured prefix if it's already in root_path
    """
    return cast(str, monkay.settings.dashboard_config.dashboard_url_prefix)
