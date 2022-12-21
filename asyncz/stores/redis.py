import pickle
from datetime import datetime
from typing import Any, List, Optional, Union

from asyncz.exceptions import AsynczException, ConflictIdError, TaskLookupError
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType
from asyncz.stores.base import BaseStore
from asyncz.typing import DictAny
from asyncz.utils import datetime_to_utc_timestamp, utc_timestamp_to_datetime
from pytz import utc

try:
    from redis import Redis
except ImportError:
    raise ImportError("You must install redis to be able to use this store.")


class RedisStore(BaseStore):
    """
    Stores tasks in a Redis instance. Any remaining kwargs are passing directly to the redis
    instance.

    Args:
        datababe - The database number to store tasks in.
        tasks_key - The key to store tasks in.
        run_times_key - The key to store the tasks run times in.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available
    """

    def __init__(
        self,
        database: int = 0,
        tasks_key: str = "asyncz.tasks",
        run_times_key: str = "asyncz.run_times",
        pickle_protocol: Optional[int] = pickle.HIGHEST_PROTOCOL,
        **kwargs: DictAny,
    ):
        super().__init__(**kwargs)
        try:
            self.database = int(database)
        except (TypeError, ValueError):
            raise AsynczException(f"The database value must be and int and got ({type(database)})")

        self.pickle_protocol = pickle_protocol
        self.tasks_key = tasks_key
        self.run_times_key = run_times_key
        self.redis = Redis(db=self.database, **kwargs)

    def lookup_task(self, task_id: Union[str, int]) -> "TaskType":
        state = self.redis.hget(self.tasks_key, task_id)
        return self.rebuild_task(state) if state else None

    def rebuild_task(self, state: Any) -> "TaskType":
        state = pickle.loads(state)
        task = Task.__new__(TaskType)
        task.__setstate__(state)
        task.scheduler = self.scheduler
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> List["TaskType"]:
        timestamp = datetime_to_utc_timestamp(now)
        ids = self.redis.zrangebyscore(self.run_times_key, 0, timestamp)
        if not ids:
            return []
        states = self.redis.hmget(self.tasks_key, *ids)
        return self.rebuild_tasks(zip(ids, states))

    def rebuild_tasks(self, states: Any) -> List["TaskType"]:
        tasks = []
        failed_task_ids = []

        for task_id, state in states:
            try:
                tasks.append(self.rebuild_task(state))
            except BaseException:
                self.logger.exception(f"Unable to restore task '{task_id}'. Removing it...")
                failed_task_ids.append(task_id)

        if failed_task_ids:
            with self.redis.pipeline() as pipe:
                pipe.hdel(self.tasks_key, *failed_task_ids)
                pipe.zrem(self.run_times_key, *failed_task_ids)
                pipe.execute()

        return tasks

    def get_next_run_time(self) -> datetime:
        next_run_time = self.redis.zrange(self.run_times_key, 0, 0, withscores=True)
        if next_run_time:
            return utc_timestamp_to_datetime(next_run_time[0][1])

    def get_all_tasks(self) -> List["TaskType"]:
        states = self.redis.hgetall(self.tasks_key)
        tasks = self.rebuild_tasks(states.items())
        paused_sort_key = datetime(9999, 12, 31, tzinfo=utc)
        return sorted(tasks, key=lambda task: task.next_run_time or paused_sort_key)

    def add_task(self, task: "TaskType"):
        if self.redis.hexists(self.tasks_key, task.id):
            raise ConflictIdError(task.id)

        with self.redis.pipeline() as pipe:
            pipe.multi()
            pipe.hset(
                self.tasks_key, task.id, pickle.dumps(task.__getstate__(), self.pickle_protocol)
            )

            if task.next_run_time:
                pipe.zadd(
                    self.run_times_key, {task.id: datetime_to_utc_timestamp(task.next_run_time)}
                )
            pipe.execute()

    def update_task(self, task: "TaskType"):
        if not self.redis.hexists(self.tasks_key, task.id):
            raise TaskLookupError(task.id)

        with self.redis.pipeline() as pipe:
            pipe.hset(
                self.tasks_key, task.id, pickle.dumps(task.__getstate__(), self.pickle_protocol)
            )
            if task.next_run_time:
                pipe.zadd(
                    self.run_times_key, {task.id: datetime_to_utc_timestamp(task.next_run_time)}
                )
            else:
                pipe.zrem(self.run_times_key, task.id)

            pipe.execute()

    def delete_task(self, task_id: Union[str, int]):
        if not self.redis.hexists(self.tasks_key, task_id):
            raise TaskLookupError(task_id)

        with self.redis.pipeline() as pipe:
            pipe.hdel(self.tasks_key, task_id)
            pipe.zrem(self.run_times_key, task_id)
            pipe.execute()

    def remove_all_tasks(self):
        with self.redis.pipeline() as pipe:
            pipe.delete(self.tasks_key)
            pipe.delete(self.run_times_key)
            pipe.execute()

    def shutdown(self):
        self.redis.connection_pool.disconnect()

    def __repr__(self):
        return "<%s>" % self.__class__.__name__
