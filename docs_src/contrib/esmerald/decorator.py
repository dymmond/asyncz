from esmerald import Esmerald
from loguru import logger

from asyncz.contrib.esmerald.decorator import scheduler
from asyncz.triggers import CronTrigger, IntervalTrigger


# Run every 2 minutes
@scheduler(trigger=IntervalTrigger(minutes=2))
def send_message():
    logger.info("Message sent after 2 minutes")


# Run every 20 minutes
@scheduler(trigger=IntervalTrigger(minutes=20))
def send_longer_message():
    logger.info("Message sent after 20 minutes")


# Run every mon,wed,fri
@scheduler(trigger=CronTrigger(day_of_week="mon,wed,fri", hour=1, minute=2))
def send_cron_message():
    logger.info("Message sent every Monday, Wednesday and Friday")


# Start Esmerald with the scheduler
# Enable the scheduler
# we pass here for example purposes
app = Esmerald(
    scheduler_tasks={
        "send_message": "src.accounts.tasks",
        "send_longer_message": "src.accounts.tasks",
        "send_cron_message": "src.accounts.tasks",
    },
    enable_scheduler=True,
)
