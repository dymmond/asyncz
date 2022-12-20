from datetime import datetime
from typing import Optional, Union

from asyncz.triggers.base import BaseTrigger


class CustomTrigger(BaseTrigger):
    alias: str = "custom"

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        # Add logic for the next trigger time of the custom trigger
        ...
