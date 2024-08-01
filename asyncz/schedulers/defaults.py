from typing import Dict

triggers: Dict[str, str] = {
    "date": "asyncz.triggers.date:DateTrigger",
    "interval": "asyncz.triggers.interval:IntervalTrigger",
    "cron": "asyncz.triggers.cron.trigger:CronTrigger",
    "and": "asyncz.triggers.date:DateTrigger",
    "or": "asyncz.triggers.combining:OrTrigger",
}


executors: Dict[str, str] = {
    "debug": "asyncz.executors.debug:DebugExecutor",
    "pool": "asyncz.executors.pool:ThreadPoolExecutor",
    "threadpool": "asyncz.executors.pool:ThreadPoolExecutor",
    "processpool": "asyncz.executors.process_pool:ProcessPoolExecutor",
    "asyncio": "asyncz.executors.asyncio:AsyncIOExecutor",
}

stores: Dict[str, str] = {
    "memory": "asyncz.stores.memory:MemoryTaskStore",
    "mongodb": "asyncz.stores.mongo:MongoDBStore",
    "redis": "asyncz.stores.redis:RedisStore",
    "sqlalchemy": "asyncz.stores.sqlalchemy:SQLAlchemyStore",
}
