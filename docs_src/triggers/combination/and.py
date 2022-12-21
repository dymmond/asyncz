from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import AndTrigger, CronTrigger, IntervalTrigger
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Hello, world!")


# Combine the triggers
trigger = AndTrigger(triggers=[IntervalTrigger(hours=5), CronTrigger(day_of_week="mon, tue")])

# Add the trigger to the task
scheduler.add_task(my_task, trigger)
