from datetime import timezone as tz

from asyncz.executors import AsyncIOExecutor, ThreadPoolExecutor
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.stores import MongoDBStore, RedisStore

# Define the stores
# Override the default MemoryStore to become RedisStore where the db is 0
stores = {"mongo": MongoDBStore(), "default": RedisStore(database=0)}

# Define the executors
# Override the default ot be the AsyncIOExecutor
executors = {
    "default": AsyncIOExecutor(),
    "threadpool": ThreadPoolExecutor(max_workers=20),
}

# Set the defaults
task_defaults = {"coalesce": False, "max_instances": 4}

# Start the scheduler
scheduler = AsyncIOScheduler()

## Add some tasks here or anything else (for instance 3 tasks)
scheduler.add_task(...)
scheduler.add_task(...)
scheduler.add_task(...)

scheduler.setup(
    stores=stores, executors=executors, task_defaults=task_defaults, timezone=tz.utc
)
