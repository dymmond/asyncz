from datetime import datetime, tzinfo
from typing import ClassVar, Optional

from asyncz.triggers.base import BaseTrigger


class ShutdownTrigger(BaseTrigger):
    alias: ClassVar[str] = "shutdown"

    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> None:
        return None
