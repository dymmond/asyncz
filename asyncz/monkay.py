from __future__ import annotations

import os
from typing import TYPE_CHECKING

from monkay import Monkay

if TYPE_CHECKING:
    from asyncz.conf.global_settings import Settings


def create_monkay(global_dict: dict) -> Monkay[None, Settings]:
    monkay: Monkay[None, Settings] = Monkay(
        global_dict,
        # enable if we want to have extensions. The second line is only relevant if they should be loaded from settings
        # with_extensions=True,
        # settings_extensions_name="extensions",
        settings_path=lambda: os.environ.get(
            "ASYNCZ_SETTINGS_MODULE", "asyncz.conf.global_settings.Settings"
        ),
        lazy_imports={
            # this way we have always fresh settings because of the forward
            "settings": "asyncz.conf.settings",  # Lazy import for application settings
            "Settings": "asyncz.conf.global_settings.Settings",
        },
        skip_all_update=True,
        package="asyncz",
    )
    return monkay
