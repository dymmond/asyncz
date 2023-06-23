from loguru import logger

from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("My task working")


scheduler.add_task(my_task, "cron", hours="*", jitter=200)

scheduler.start()
