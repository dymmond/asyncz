from loguru import logger

from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def my_task(number):
    logger.info(number)


# Execute the task on December 25th, 2022
scheduler.add_task(my_task, run_date="2022-12-25 00:01:00", args=[25])

scheduler.start()
