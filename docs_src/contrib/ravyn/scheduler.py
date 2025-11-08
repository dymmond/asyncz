from loguru import logger

from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import IntervalTrigger

from ravyn.contrib.schedulers.asyncz.config import AsynczConfig
from ravyn.contrib.schedulers.asyncz.decorator import scheduler
from ravyn import Ravyn


# Run every 2 minutes
@scheduler(trigger=IntervalTrigger(minutes=2))
def send_message() -> None:
    logger.info("Message sent after 2 minutes")


# Run every 20 minutes
@scheduler(trigger=IntervalTrigger(minutes=20))
def send_longer_message() -> None:
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

# Start Ravyn with the scheduler
# Pass the configurations
# Enable the scheduler
# AsyncIOScheduler Is the default scheduler of Ravyn but
# we pass here for example purposes
app = Ravyn(
    scheduler_config=AsynczConfig(
        scheduler_class=AsyncIOScheduler,
        configurations=configurations,
        tasks={
            "send_message": "src.accounts.tasks",
            "send_longer_message": "src.accounts.tasks",
        },
    ),
    enable_scheduler=True,
)
