# API Reference

This page collects the main public Asyncz types in one place.

## Schedulers

::: asyncz.schedulers.asyncio.AsyncIOScheduler

::: asyncz.schedulers.asyncio.NativeAsyncIOScheduler

## Tasks

::: asyncz.tasks.base.Task

## Triggers

::: asyncz.triggers.date.DateTrigger

::: asyncz.triggers.interval.IntervalTrigger

::: asyncz.triggers.cron.trigger.CronTrigger

::: asyncz.triggers.combination.AndTrigger

::: asyncz.triggers.combination.OrTrigger

::: asyncz.triggers.shutdown.ShutdownTrigger

## Executors

::: asyncz.executors.asyncio.AsyncIOExecutor

::: asyncz.executors.pool.ThreadPoolExecutor

::: asyncz.executors.process_pool.ProcessPoolExecutor

::: asyncz.executors.debug.DebugExecutor

## Stores

::: asyncz.stores.memory.MemoryStore

::: asyncz.stores.file.FileStore

::: asyncz.stores.mongo.MongoDBStore

::: asyncz.stores.redis.RedisStore

::: asyncz.stores.sqlalchemy.SQLAlchemyStore

## Events

::: asyncz.events.base.SchedulerEvent

::: asyncz.events.base.TaskEvent

::: asyncz.events.base.TaskSubmissionEvent

::: asyncz.events.base.TaskExecutionEvent
