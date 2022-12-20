import pytz
from asyncz.events.constants import JOB_ADDED, JOB_REMOVED
from asyncz.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)


def my_custom_listener(event):
    if not event.exception:
        logger.info("All good")
    else:
        logger.exception("Problem with the job")


# Add event listener
scheduler.add_listener(my_custom_listener, JOB_ADDED | JOB_REMOVED)
