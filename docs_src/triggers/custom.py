from datetime import datetime
from typing import Optional, Union

from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers.base import BaseTrigger
from loguru import logger


class CustomTrigger(BaseTrigger):
    alias: str = "custom"

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        # Add logic for the next trigger time of the custom trigger
        ...


def get_info():
    logger.info("info...")


# Create an instance
trigger = CustomTrigger(...)

# Create a scheduler
scheduler = AsyncIOScheduler()

# Add custom trigger
scheduler.add_task(get_info, trigger)
