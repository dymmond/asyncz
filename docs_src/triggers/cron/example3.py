import logging

from asyncz.schedulers import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@scheduler.add_task("cron", hours=1, id="my_task_id", day="last sat")
def my_task():
    logger.info("My task working")


scheduler.start()
