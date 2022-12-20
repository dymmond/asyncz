from datetime import date

from asyncz.schedulers import AsyncIOScheduler
from loguru import logger

scheduler = AsyncIOScheduler()


def my_task(number):
    logger.info(number)


# Execute the job on December 25th, 2022
scheduler.add_job(my_task, run_date=date(2022, 12, 24), args=[25])

scheduler.start()
