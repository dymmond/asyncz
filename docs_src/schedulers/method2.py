from asyncz.schedulers.asyncio import AsyncIOScheduler

# Start the scheduler
scheduler = AsyncIOScheduler(
    {
        "asyncz.stores.mongo": {"type": "mongodb"},
        "asyncz.stores.default": {"type": "redis", "database": "0"},
        "asyncz.executors.threadpool": {
            "max_workers": "20",
            "class": "asyncz.executors.threadpool:ThreadPoolExecutor",
        },
        "asyncz.executors.default": {"class": "asyncz.executors.asyncio::AsyncIOExecutor"},
        "asyncz.job_defaults.coalesce": "false",
        "asyncz.job_defaults.max_instances": "3",
        "asyncz.job_defaults.timezone": "UTC",
    },
)
