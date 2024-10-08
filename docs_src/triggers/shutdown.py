from loguru import logger

from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Goodbye!")


# Run on shutdown in an own thread
scheduler.add_task(my_task, "shutdown")

scheduler.start()
