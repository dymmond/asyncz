from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("My task working")


# Run every 5 hours and limits the window
scheduler.add_job(my_task, "interval", hours=5, jitter=200)

scheduler.start()
