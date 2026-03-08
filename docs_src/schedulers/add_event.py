from datetime import timezone as tz
import logging

from asyncz.events.constants import TASK_ADDED, TASK_REMOVED
from asyncz.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=tz.utc)


def my_custom_listener(event):
    if not event.exception:
        logger.info("All good")
    else:
        logger.exception("Problem with the task")


# Add event listener
scheduler.add_listener(my_custom_listener, TASK_ADDED | TASK_REMOVED)
