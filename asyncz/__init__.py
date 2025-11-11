from typing import TYPE_CHECKING

from .monkay import create_monkay

__version__ = "0.14.1"

if TYPE_CHECKING:
    from .conf import settings
    from .conf.global_settings import Settings


__all__ = [
    "Settings",
    "settings",
]

monkay = create_monkay(globals())
del create_monkay
