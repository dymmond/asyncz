from typing import TYPE_CHECKING, Union

from asyncz.executors.base import BaseExecutor, run_job

if TYPE_CHECKING:
    from asyncz.jobs.types import JobType


class DebugExecutor(BaseExecutor):
    """
    A special executor that executes the target callable directly instead of deferring it to a
    thread or process.
    """

    def do_send_job(
        self,
        job: "JobType",
        run_times: Union[
            int,
            str,
        ],
    ):
        try:
            events = run_job(job, job.store_alias, run_times, self.logger)
        except BaseException:
            self.run_job_error(job.id)
        else:
            self.run_job_success(job.id, events)
