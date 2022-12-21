from typing import Dict

from pydantic import BaseModel


class AsynczObjectMapping(BaseModel):
    @property
    def triggers(self) -> Dict[str, str]:
        return {
            "date": "asyncz.triggers.date:DateTrigger",
            "interval": "asyncz.triggers.interval:IntervalTrigger",
            "cron": "asyncz.triggers.cron.trigger:CronTrigger",
            "and": "asyncz.triggers.date:DateTrigger",
            "or": "asyncz.triggers.combining:OrTrigger",
        }

    @property
    def executors(self) -> Dict[str, str]:
        return {
            "debug": "asyncz.executors.debug:DebugExecutor",
            "threadpool": "asyncz.executors.pool:ThreadPoolExecutor",
            "processpool": "asyncz.executors.pool:ProcessPoolExecutor",
            "asyncio": "asyncz.executors.asyncio:AsyncIOExecutor",
        }

    @property
    def stores(self) -> Dict[str, str]:
        return {
            "memory": "asyncz.stores.memory:MemoryTaskStore",
            "mongo": "asyncz.stores.mongo:MongoDBStore",
            "redis": "asyncz.stores.redis:RedisStore",
        }
