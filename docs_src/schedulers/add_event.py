from datetime import timezone as tz
from loguru import logger

from asyncz.events.constants import TASK_ADDED, TASK_REMOVED
from asyncz.schedulers.asyncio import AsyncIOScheduler

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=tz.utc)


def my_custom_listener(event):
    if not event.exception:
        logger.info("All good")
    else:
        logger.exception("Problem with the task")


# Add event listener
scheduler.add_listener(my_custom_listener, TASK_ADDED | TASK_REMOVED)
