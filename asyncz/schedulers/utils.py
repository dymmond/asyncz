from functools import partial, wraps
from typing import Any

from asyncz.typing import DictAny


def run_in_event_loop(fn):
    """
    Decorator to run in an evenmt loop.
    """

    @wraps(fn)
    def wrapper(self, *args: Any, **kwargs: "DictAny"):
        wrapped = partial(fn, self, *args, **kwargs)
        self.event_loop.call_soon_threadsafe(wrapped)

    return wrapper
