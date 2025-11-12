from pathlib import Path
from typing import Any

from lilya.apps import Lilya
from lilya.compat import reverse
from lilya.requests import Request
from lilya.routing import NoMatchFound, Router
from lilya.templating import Jinja2Template


def safe_url_for(request: Request, name: str, **params: Any) -> str | None:
    """
    Safely generates a full URL for a given route name within the current request's scope.

    This function attempts to resolve the URL using the router associated with the
    current ASGI scope and catches `NoMatchFound` exceptions, returning `None` instead
    of crashing if the route name is not found.

    Args:
        request: The incoming Lilya Request object, used to retrieve the active router context.
        name: The unique name of the route to generate the URL for.
        **params: Keyword arguments required for path parameters (e.g., `user_id=1`).

    Returns:
        The generated absolute URL string, or `None` if the route name cannot be found.
    """
    # Retrieve the router or application instance from the ASGI scope
    scoped_app: Router | Lilya | Any | None = request.scope.get("router") or request.scope.get(
        "app"
    )

    try:
        # Attempt to reverse the URL using the current routing context
        return reverse(name, app=scoped_app, **params)
    except NoMatchFound:
        # Gracefully handle the case where the route name does not exist
        return None


templates = Jinja2Template(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["getattr"] = getattr
templates.env.globals["safe_url_for"] = safe_url_for
