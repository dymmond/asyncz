import logging

from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import CronTrigger, OrTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Hello, world!")


# Combine the triggers
trigger = OrTrigger(
    triggers=[CronTrigger(day_of_week="sat", hour=5), CronTrigger(day_of_week="sun", hour=10)]
)

# Add the trigger to the task
scheduler.add_task(my_task, trigger)
