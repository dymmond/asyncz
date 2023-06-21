from loguru import logger

from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


@scheduler.scheduled_task("cron", hours=1, id="my_task_id", day="last sat")
def my_task():
    logger.info("My task working")


scheduler.start()
