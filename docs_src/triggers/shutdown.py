import logging

from asyncz.schedulers import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Goodbye!")


# Run on shutdown in an own thread
scheduler.add_task(my_task, "shutdown")

scheduler.start()
