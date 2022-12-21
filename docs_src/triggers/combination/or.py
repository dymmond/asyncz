from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import CronTrigger, OrTrigger
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Hello, world!")


# Combine the triggers
trigger = OrTrigger(
    triggers=[CronTrigger(day_of_week="sat", hour=5), CronTrigger(day_of_week="sun", hour=10)]
)

# Add the trigger to the task
scheduler.add_task(my_task, trigger)
