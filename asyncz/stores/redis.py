import pickle
from datetime import datetime
from typing import Any, List, Optional, Union

from asyncz.exceptions import AsynczException, ConflictIdError, JobLookupError
from asyncz.jobs import Job
from asyncz.jobs.types import JobType
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
    Stores jobs in a Redis instance. Any remaining kwargs are passing directly to the redis
    instance.

    Args:
        datababe - The database number to store jobs in.
        jobs_key - The key to store jobs in.
        run_times_key - The key to store the jobs run times in.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available
    """

    def __init__(
        self,
        database: int = 0,
        jobs_key: str = "asyncz.jobs",
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
        self.jobs_key = jobs_key
        self.run_times_key = run_times_key
        self.redis = Redis(db=self.database, **kwargs)

    def lookup_job(self, job_id: Union[str, int]) -> "JobType":
        state = self.redis.hget(self.jobs_key, job_id)
        return self.rebuild_job(state) if state else None

    def rebuild_job(self, state: Any) -> "JobType":
        state = pickle.loads(state)
        job = Job.__new__(JobType)
        job.__setstate__(state)
        job.scheduler = self.scheduler
        job.store_alias = self.alias
        return job

    def get_due_jobs(self, now: datetime) -> List["JobType"]:
        timestamp = datetime_to_utc_timestamp(now)
        ids = self.redis.zrangebyscore(self.run_times_key, 0, timestamp)
        if not ids:
            return []
        states = self.redis.hmget(self.jobs_key, *ids)
        return self.rebuild_jobs(zip(ids, states))

    def rebuild_jobs(self, states: Any) -> List["JobType"]:
        jobs = []
        failed_job_ids = []

        for job_id, state in states:
            try:
                jobs.append(self.rebuild_job(state))
            except BaseException:
                self.logger.exception(f"Unable to restore job '{job_id}'. Removing it...")
                failed_job_ids.append(job_id)

        if failed_job_ids:
            with self.redis.pipeline() as pipe:
                pipe.hdel(self.jobs_key, *failed_job_ids)
                pipe.zrem(self.run_times_key, *failed_job_ids)
                pipe.execute()

        return jobs

    def get_next_run_time(self) -> datetime:
        next_run_time = self.redis.zrange(self.run_times_key, 0, 0, withscores=True)
        if next_run_time:
            return utc_timestamp_to_datetime(next_run_time[0][1])

    def get_all_jobs(self) -> List["JobType"]:
        states = self.redis.hgetall(self.jobs_key)
        jobs = self.rebuild_jobs(states.items())
        paused_sort_key = datetime(9999, 12, 31, tzinfo=utc)
        return sorted(jobs, key=lambda job: job.next_run_time or paused_sort_key)

    def add_job(self, job: "JobType"):
        if self.redis.hexists(self.jobs_key, job.id):
            raise ConflictIdError(job.id)

        with self.redis.pipeline() as pipe:
            pipe.multi()
            pipe.hset(
                self.jobs_key, job.id, pickle.dumps(job.__getstate__(), self.pickle_protocol)
            )

            if job.next_run_time:
                pipe.zadd(
                    self.run_times_key, {job.id: datetime_to_utc_timestamp(job.next_run_time)}
                )
            pipe.execute()

    def update_job(self, job: "JobType"):
        if not self.redis.hexists(self.jobs_key, job.id):
            raise JobLookupError(job.id)

        with self.redis.pipeline() as pipe:
            pipe.hset(
                self.jobs_key, job.id, pickle.dumps(job.__getstate__(), self.pickle_protocol)
            )
            if job.next_run_time:
                pipe.zadd(
                    self.run_times_key, {job.id: datetime_to_utc_timestamp(job.next_run_time)}
                )
            else:
                pipe.zrem(self.run_times_key, job.id)

            pipe.execute()

    def remove_job(self, job_id: Union[str, int]):
        if not self.redis.hexists(self.jobs_key, job_id):
            raise JobLookupError(job_id)

        with self.redis.pipeline() as pipe:
            pipe.hdel(self.jobs_key, job_id)
            pipe.zrem(self.run_times_key, job_id)
            pipe.execute()

    def remove_all_jobs(self):
        with self.redis.pipeline() as pipe:
            pipe.delete(self.jobs_key)
            pipe.delete(self.run_times_key)
            pipe.execute()

    def shutdown(self):
        self.redis.connection_pool.disconnect()

    def __repr__(self):
        return "<%s>" % self.__class__.__name__
