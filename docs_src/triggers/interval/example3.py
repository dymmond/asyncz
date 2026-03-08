import logging

from asyncz.schedulers import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# Run every 5 hours
@scheduler.add_task("interval", hours=5, id="my_task_id")
def my_task():
    logger.info("My task working")


scheduler.start()
