from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, Union

from asyncz.state import BaseStateExtra
from asyncz.typing import DictAny
from loguru import logger

if TYPE_CHECKING:
    from asyncz.jobs.types import JobType


class BaseStore(BaseStateExtra, ABC):
    """
    Base class for all job stores.
    """

    def __init__(
        self, scheduler: Optional[Any] = None, alias: Optional[str] = None, **kwargs: "DictAny"
    ) -> None:
        super().__init__(**kwargs)
        self.logger = logger
        self.scheduler = scheduler
        self.alias = alias

    def start(self, scheduler: Any, alias: str):
        """
        Called by the scheduler when the scheduler is being started or when the job store is being
        added to an already running scheduler.

        Args:
            scheduler: The scheduler that is starting this job store.
            alias: Alias of this job store as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.alias = alias

    def shutdown(self):
        """
        Frees any resources still bound to this job store.
        """
        ...

    def fix_paused_jobs(self, jobs: List["JobType"]):
        for index, job in enumerate(jobs):
            if job.next_run_time is not None:
                if index > 0:
                    paused_jobs = jobs[:index]
                    del jobs[:index]
                    jobs.extend(paused_jobs)
                break

    @abstractmethod
    def lookup_job(self, job_id: Union[str, int]) -> "JobType":
        """
        Returns a specific job, or None if it isn't found.

        The job store is responsible for setting the scheduler and jobstore attributes of
        the returned job to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def get_due_jobs(self, now: datetime) -> List["JobType"]:
        """
        Returns the list of jobs that have next_run_time earlier or equal to now.
        The returned jobs must be sorted by next run time (ascending).
        """
        ...

    @abstractmethod
    def get_next_run_time(self) -> datetime:
        """
        Returns the earliest run time of all the jobs stored in this job store, or None if
        there are no active jobs.
        """
        ...

    @abstractmethod
    def get_all_jobs(self) -> List["JobType"]:
        """
        Returns a list of all jobs in this job store.
        The returned jobs should be sorted by next run time (ascending).
        Paused jobs (next_run_time == None) should be sorted last.

        The job store is responsible for setting the scheduler and store attributes of
        the returned jobs to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def add_job(self, job: "JobType"):
        """
        Adds the given job to this store.
        """
        ...

    @abstractmethod
    def update_job(self, job: "JobType"):
        """
        Replaces the job in the store with the given newer version.
        """
        ...

    @abstractmethod
    def remove_job(self, job_id: Union[str, int]):
        """
        Removes the given job from this store.
        """
        ...

    @abstractmethod
    def remove_all_jobs(self):
        """Removes all jobs from this store."""
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__}>"
