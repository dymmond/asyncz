from loguru import logger

from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("My task working")


# Run every 5 hours and limits the window
scheduler.add_task(
    my_task, "interval", hours=5, start_at="2022-12-24 00:00:00", end_at="2022-12-25 23:59:59"
)

scheduler.start()
