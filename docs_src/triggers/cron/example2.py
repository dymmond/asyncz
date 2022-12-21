from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task():
    logger.info("Hello, world!")


# Runs from Monday to Friday at 1:00 (am) until 2022-12-25 00:00:00
scheduler.add_task(my_task, "cron", day_of_week="mon-fri", hour=1, end_at="2022-12-25")

scheduler.start()
