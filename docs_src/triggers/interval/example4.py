import logging

from asyncz.schedulers import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("My task working")


# Run every 5 hours and limits the window
scheduler.add_task(my_task, "interval", hours=5, jitter=200)

scheduler.start()
