from typing import TYPE_CHECKING

from .monkay import create_monkay
from .schedulers import AsyncIOScheduler as Asyncz

__version__ = "0.17.0"

if TYPE_CHECKING:
    from .conf import settings
    from .conf.global_settings import Settings


__all__ = [
    "Asyncz",
    "Settings",
    "settings",
]

monkay = create_monkay(globals())
del create_monkay
