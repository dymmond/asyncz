from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


@scheduler.scheduled_task("cron", hours=1, id="my_task_id", day="last sat")
def my_task():
    logger.info("My task working")


scheduler.start()
