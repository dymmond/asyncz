import sys
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from traceback import format_tb
from typing import TYPE_CHECKING, Any, List, Optional, Union

from asyncz.events import JobExecutionEvent
from asyncz.events.constants import JOB_ERROR, JOB_EXECUTED, JOB_MISSED
from asyncz.exceptions import MaximumInstancesError
from asyncz.state import BaseStateExtra
from loguru import logger
from loguru._logger import Logger
from pytz import utc

if TYPE_CHECKING:
    from asyncz.jobs.types import JobType


class BaseExecutor(BaseStateExtra, ABC):
    """
    Base model for the executors. It defines the interface for all the executors used by the Asyncz.

    Asyncz uses loguru for its logging as it is more descriptive and intuitive.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.instances = defaultdict(lambda: 0)

    def start(self, scheduler: Any, alias: str):
        """
        Called by the scheduler when the scheduler is being started or when the executor is being
        added to an already running scheduler.

        Args:
            scheduler - The scheduler that is starting this executor.
            alias - The alias of this executor as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.lock = scheduler.create_lock()
        self.logger = logger
        self.logger.bind(logger_name=f"asyncz.executors.{alias}")

    def shutdown(self, wait: bool = True):
        """
        Shuts down the executor.

        Args:
            wait - Boolean indicating to wait until all submitted jobs have been executed.
        """

    def send_job(self, job: "JobType", run_times: List[datetime]):
        """
        Sends the job for execution.

        Args:
            job: A Job instanceyo execute.
            run_times: A list of datetimes specifying when the job should have been run.
        """
        assert self.lock is not None, "This executor has not been started yet."

        with self.lock:
            if self.instances[job.id] >= job.max_instances:
                raise MaximumInstancesError(job.id, job.max_instances)

            self.do_send_job(job, run_times)
            self.instances[job.id] += 1

    @abstractmethod
    def do_send_job(self, job: "JobType", run_times: List[datetime]) -> Any:
        """
        Executes the actual task of scheduling `run_job` to be called.
        """
        ...

    def run_job_success(self, job_id: Union[str, int], events: List[int]) -> Any:
        """
        Called by the executor with the list of generated events when the function run_job has
        been successfully executed.
        """
        with self.lock:
            self.instances[job_id] -= 1
            if self.instances[job_id] == 0:
                del self.instances[job_id]

        for event in events or []:
            self.scheduler.dispatch_event(event)

    def run_job_error(self, job_id: Union[str, int]) -> Any:
        """
        Called by the executor with the exception if there is an error calling the run_job.
        """
        with self.lock:
            self.instances[job_id] -= 1
            if self.instances[job_id] == 0:
                del self.instances[job_id]

        self.logger.opt(exception=True).error(f"Error running job {job_id}", exc_info=True)


def run_job(
    job: "JobType", store_alias: str, run_times: List[datetime], _logger: Optional["Logger"] = None
):
    """
    Called by executors to run the job. Returns a list of scheduler events to be dispatched by the
    scheduler.

    The run job is made to run in async mode.
    """
    if not _logger:
        _logger = logger

    events = []
    for run_time in run_times:
        if getattr(job, "mistrigger_grace_time", None) is not None:
            difference = datetime.now(utc) - run_time
            grace_time = timedelta(seconds=job.mistrigger_grace_time)
            if difference > grace_time:
                events.append(
                    JobExecutionEvent(
                        code=JOB_MISSED,
                        job_id=job.id,
                        store=store_alias,
                        scheduled_run_time=run_time,
                    )
                )
                _logger.warning(f"Run time of job '{job}' was missed by {difference}")
                continue

        _logger.info(f'Running job "{job}" (scheduled at {run_time})')
        try:
            return_value = job.fn(*job.args, **job.kwargs)
        except BaseException:
            exc, trace_back = sys.exc_info()[1:]
            formatted_trace_back = "".join(format_tb(trace_back))
            events.append(
                JobExecutionEvent(
                    code=JOB_ERROR,
                    job_id=job.id,
                    store=store_alias,
                    scheduled_run_time=run_time,
                    exception=exc,
                    traceback=formatted_trace_back,
                )
            )
            traceback.clear_frames(trace_back)
            del trace_back
        else:
            events.append(
                JobExecutionEvent(
                    code=JOB_EXECUTED,
                    job_id=job.id,
                    store=store_alias,
                    scheduled_run_time=run_time,
                    return_value=return_value,
                )
            )
            _logger.info(f"Job '{job}' executed successfully.")
    return events


async def run_coroutine_job(
    job: "JobType", store_alias: str, run_times: List[datetime], _logger: Optional["Logger"] = None
):
    """
    Called by executors to run the job. Returns a list of scheduler events to be dispatched by the
    scheduler.

    The run job is made to run in async mode.
    """
    if not _logger:
        _logger = logger

    events = []
    for run_time in run_times:
        if getattr(job, "mistrigger_grace_time", None) is not None:
            difference = datetime.now(utc) - run_time
            grace_time = timedelta(seconds=job.mistrigger_grace_time)
            if difference > grace_time:
                events.append(
                    JobExecutionEvent(
                        code=JOB_MISSED,
                        job_id=job.id,
                        alias=store_alias,
                        scheduled_run_time=run_time,
                    )
                )
                _logger.warning(f"Run time of job '{job}' was missed by {difference}")
                continue

        _logger.info(f'Running job "{job}" (scheduled at {run_time})')
        try:
            return_value = await job.fn(*job.args, **job.kwargs)
        except BaseException:
            exc, trace_back = sys.exc_info()[1:]
            formatted_trace_back = "".join(format_tb(trace_back))
            events.append(
                JobExecutionEvent(
                    code=JOB_ERROR,
                    job_id=job.id,
                    alias=store_alias,
                    scheduled_run_time=run_time,
                    exception=exc,
                    traceback=formatted_trace_back,
                )
            )
            traceback.clear_frames(trace_back)
            del trace_back
        else:
            events.append(
                JobExecutionEvent(
                    code=JOB_EXECUTED,
                    job_id=job.id,
                    alias=store_alias,
                    scheduled_run_time=run_time,
                    return_value=return_value,
                )
            )
            _logger.info(f"Job '{job}' executed successfully")

    return events
