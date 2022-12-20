from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


# Run every 5 hours
@scheduler.scheduled_job("interval", hours=5, id="my_task_id")
def my_task():
    logger.info("My task working")


scheduler.start()
