from asyncz.schedulers.asyncio import AsyncIOScheduler

# Create the scheduler
scheduler = AsyncIOScheduler(
    global_config={
        "asyncz.lock_path": "/tmp/asynzc_super_project_{store}_store.pid",
        "asyncz.startup_delay": 2,
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

# Start the scheduler
with scheduler:
    ...
    # your code
