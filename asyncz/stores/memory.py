from datetime import datetime
from typing import TYPE_CHECKING, List, Union

from asyncz.exceptions import ConflictIdError, JobLookupError
from asyncz.stores.base import BaseStore
from asyncz.utils import datetime_to_utc_timestamp

if TYPE_CHECKING:
    from asyncz.jobs.types import JobType


class MemoryStore(BaseStore):
    """
    Stores jobs in an arrat in RAM. Provides no persistance support.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jobs = []
        self.jobs_index = {}

    def lookup_job(self, job_id: Union[str, int]) -> "JobType":
        return self.jobs_index.get(job_id, (None, None))[0]

    def get_due_jobs(self, now: datetime) -> List["JobType"]:
        now_timestamp = datetime_to_utc_timestamp(now)
        pending = []

        for job, timestamp in self.jobs:
            if timestamp is None or timestamp > now_timestamp:
                break
            pending.append(job)

        return pending

    def get_next_run_time(self) -> datetime:
        return self.jobs[0][0].next_run_time if self.jobs else None

    def get_all_jobs(self) -> List["JobType"]:
        return [job[0] for job in self.jobs]

    def add_job(self, job: "JobType"):
        if job.id in self.jobs_index:
            raise ConflictIdError(job.id)

        timestamp = datetime_to_utc_timestamp(job.next_run_time)
        index = self.get_job_index(timestamp, job.id)
        self.jobs.insert(index, (job, timestamp))
        self.jobs_index[job.id] = (job, timestamp)

    def update_job(self, job: "JobType"):
        old_job, old_timestamp = self.jobs_index.get(job.id, (None, None))
        if old_job is None:
            raise JobLookupError(job.id)

        old_index = self.get_job_index(old_timestamp, old_job.id)
        new_timestamp = datetime_to_utc_timestamp(job.next_run_time)
        if old_timestamp == new_timestamp:
            self.jobs[old_index] = (job, new_timestamp)
        else:
            del self.jobs[old_index]
            new_index = self.get_job_index(new_timestamp, job.id)
            self.jobs.insert(new_index, (job, new_timestamp))

    def remove_job(self, job_id: Union[str, int]):
        job, timestamp = self.jobs_index.get(job_id, (None, None))
        if job is None:
            raise JobLookupError(job_id)

        index = self.get_job_index(timestamp, job_id)
        del self.jobs[index]
        del self.jobs_index[job.id]

    def remove_all_jobs(self):
        self.jobs = []
        self.jobs_index = {}

    def shutdown(self):
        self.remove_all_jobs()

    def get_job_index(self, timestamp: Union[int, float], job_id: Union[int, str]) -> int:
        """
        Returns the index of the given job, or if it's not found, the index where the job should be
        inserted based on the given timestamp.
        """
        low, high = 0, len(self.jobs)
        timestamp = float("inf") if timestamp is None else timestamp
        while low < high:
            mid = (low + high) // 2
            mid_job, mid_timestamp = self.jobs[mid]
            mid_timestamp = float("inf") if mid_timestamp is None else mid_timestamp
            if mid_timestamp > timestamp:
                high = mid
            elif mid_timestamp < timestamp:
                low = mid + 1
            elif mid_job.id > job_id:
                high = mid
            elif mid_job.id < job_id:
                low = mid + 1
            else:
                return mid

        return low
