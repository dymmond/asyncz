from collections.abc import Callable
from functools import partial, wraps
from typing import Any


def run_in_event_loop(fn: Callable[..., Any]) -> Any:
    """
    Decorator to run in an event loop.
    """

    @wraps(fn)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:  # type: ignore
        wrapped = partial(fn, self, *args, **kwargs)
        self.event_loop.call_soon_threadsafe(wrapped)

    return wrapper
