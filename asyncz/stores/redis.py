import pickle
from collections.abc import Iterable
from datetime import datetime
from datetime import timezone as tz
from typing import TYPE_CHECKING, Any, Optional, cast

from asyncz.exceptions import AsynczException, ConflictIdError, TaskLookupError
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType
from asyncz.utils import datetime_to_utc_timestamp, utc_timestamp_to_datetime

try:
    from redis import Redis
except ImportError:
    raise ImportError("You must install redis to be able to use this store.") from None

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType


class RedisStore(BaseStore):
    """
    Stores tasks in a Redis instance. Any remaining kwargs are passing directly to the redis
    instance.

    Args:
        database - The database number to store tasks in.
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
        pickle_protocol: int | None = pickle.HIGHEST_PROTOCOL,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        try:
            self.database = int(database)
        except (TypeError, ValueError):
            raise AsynczException(
                f"The database value must be and int and got ({type(database)})"
            ) from None

        self.pickle_protocol = pickle_protocol
        self.tasks_key = tasks_key
        self.run_times_key = run_times_key
        self.redis = Redis(db=self.database, **kwargs)

    def lookup_task(self, task_id: str) -> Optional["TaskType"]:
        state = self.redis.hget(self.tasks_key, task_id)
        return self.rebuild_task(state) if state else None

    def rebuild_task(self, state: Any) -> "TaskType":
        state = pickle.loads(self.conditional_decrypt(state))
        task = Task.__new__(Task)
        task.__setstate__(state)
        task.scheduler = cast("SchedulerType", self.scheduler)
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> list["TaskType"]:
        timestamp = datetime_to_utc_timestamp(now)
        ids: list[str] = self.redis.zrangebyscore(self.run_times_key, 0, timestamp)  # type: ignore
        if not ids:
            return []
        states: list[Any] = self.redis.hmget(self.tasks_key, ids)  # type: ignore
        return self.rebuild_tasks(zip(ids, states, strict=False))

    def rebuild_tasks(self, states: Iterable[tuple[str, Any]]) -> list["TaskType"]:
        tasks = []
        failed_task_ids = []

        for task_id, state in states:
            try:
                tasks.append(self.rebuild_task(state))
            except BaseException:
                cast("SchedulerType", self.scheduler).loggers[self.logger_name].exception(
                    f"Unable to restore task '{task_id}'. Removing it..."
                )
                failed_task_ids.append(task_id)

        if failed_task_ids:
            with self.redis.pipeline() as pipe:
                pipe.hdel(self.tasks_key, *failed_task_ids)
                pipe.zrem(self.run_times_key, *failed_task_ids)
                pipe.execute()

        return tasks

    def get_next_run_time(self) -> datetime | None:
        next_run_time: Any = self.redis.zrange(self.run_times_key, 0, 0, withscores=True)
        if next_run_time:
            return utc_timestamp_to_datetime(cast(float, next_run_time[0][1]))
        return None

    def get_all_tasks(self) -> list["TaskType"]:
        states: list[tuple[str, Any]] = self.redis.hgetall(self.tasks_key)  # type: ignore
        tasks = self.rebuild_tasks(states.items())
        paused_sort_key = datetime(9999, 12, 31, tzinfo=tz.utc)
        return sorted(tasks, key=lambda task: task.next_run_time or paused_sort_key)

    def add_task(self, task: "TaskType") -> None:
        assert task.id
        if self.redis.hexists(self.tasks_key, task.id):
            raise ConflictIdError(task.id)

        with self.redis.pipeline() as pipe:
            pipe.multi()
            pipe.hset(
                self.tasks_key,
                task.id,
                self.conditional_encrypt(pickle.dumps(task.__getstate__(), self.pickle_protocol)),  # type: ignore
            )

            if task.next_run_time:
                pipe.zadd(
                    self.run_times_key,
                    {task.id: datetime_to_utc_timestamp(task.next_run_time)},
                )
            pipe.execute()

    def update_task(self, task: "TaskType") -> None:
        assert task.id
        if not self.redis.hexists(self.tasks_key, task.id):
            raise TaskLookupError(task.id)

        with self.redis.pipeline() as pipe:
            pipe.hset(
                self.tasks_key,
                task.id,
                self.conditional_encrypt(pickle.dumps(task.__getstate__(), self.pickle_protocol)),  # type: ignore
            )
            if task.next_run_time:
                pipe.zadd(
                    self.run_times_key,
                    {task.id: datetime_to_utc_timestamp(task.next_run_time)},
                )
            else:
                pipe.zrem(self.run_times_key, task.id)

            pipe.execute()

    def delete_task(self, task_id: str) -> None:
        if not self.redis.hexists(self.tasks_key, task_id):
            raise TaskLookupError(task_id)

        with self.redis.pipeline() as pipe:
            pipe.hdel(self.tasks_key, task_id)
            pipe.zrem(self.run_times_key, task_id)
            pipe.execute()

    def remove_all_tasks(self) -> None:
        with self.redis.pipeline() as pipe:
            pipe.delete(self.tasks_key)
            pipe.delete(self.run_times_key)
            pipe.execute()

    def shutdown(self) -> None:
        self.redis.connection_pool.disconnect()
        super().shutdown()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
