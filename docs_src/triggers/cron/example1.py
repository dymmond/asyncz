
from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Hello, world!")


# Schedules job_function to be run on the third Friday
# of June, July, August, November and December at 00:00, 01:00, 02:00 and 03:00
scheduler.add_job(my_task, "cron", month="6-8,11-12", day="3rd fri", hour="0-3")

scheduler.start()
