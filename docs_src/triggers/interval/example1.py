from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("My task working")


# Run every 5 hours
scheduler.add_task(my_task, "interval", hours=5)

scheduler.start()
