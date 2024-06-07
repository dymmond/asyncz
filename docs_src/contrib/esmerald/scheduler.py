from loguru import logger

from asyncz.contrib.esmerald.decorator import scheduler
from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import IntervalTrigger
from esmerald import Esmerald


# Run every 2 minutes
@scheduler(trigger=IntervalTrigger(minutes=2))
def send_message():
    logger.info("Message sent after 2 minutes")


# Run every 20 minutes
@scheduler(trigger=IntervalTrigger(minutes=20))
def send_longer_message():
    logger.info("Message sent after 20 minutes")


# Create the extra configurations
configurations = (
    {
        "asyncz.stores.mongo": {"type": "mongodb"},
        "asyncz.stores.default": {"type": "redis", "database": "0"},
        "asyncz.executors.pool": {
            "max_workers": "20",
            "class": "asyncz.executors.pool:ThreadPoolExecutor",
        },
        "asyncz.executors.default": {"class": "asyncz.executors.asyncio:AsyncIOExecutor"},
        "asyncz.task_defaults.coalesce": "false",
        "asyncz.task_defaults.max_instances": "3",
        "asyncz.task_defaults.timezone": "UTC",
    },
)

# Start Esmerald with the scheduler
# Pass the configurations
# Enable the scheduler
# AsyncIOScheduler Is the default scheduler of Esmerald but
# we pass here for example purposes
app = Esmerald(
    scheduler_class=AsyncIOScheduler,
    scheduler_configurations=configurations,
    scheduler_tasks={
        "send_message": "src.accounts.tasks",
        "send_longer_message": "src.accounts.tasks",
    },
    enable_scheduler=True,
)
