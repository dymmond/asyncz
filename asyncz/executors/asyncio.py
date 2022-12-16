from typing import TYPE_CHECKING, Any, Union

from asyncz.exceptions import AsynczException
from asyncz.executors.base import BaseExecutor, run_coroutine_job, run_job
from asyncz.utils import iscoroutinefunction_partial

if TYPE_CHECKING:
    from asyncz.jobs.types import JobType


class AsyncIOExecutor(BaseExecutor):
    """
    Executor used for AsyncIO, typically can also be plugged into any ASGI framwork as well, for example, Esmerald, Starlite, FastAPI...

    Runs the job in the default executor event loop.

    If the job function is a native coroutine function, it is scheduled to be run directly in the
    event loop as soon as possible. All other functions are run in the event loop's default
    executor which is usually a thread pool.
    """

    def start(self, scheduler: Any, alias: str):
        super().start(scheduler, alias)
        self.event_loop = scheduler.event_loop
        self.pending_futures = set()

    def shutdown(self, wait: bool = True):
        for f in self.pending_futures:
            if not f.done():
                f.cancel()

        self.pending_futures.clear()

    def do_send_job(self, job: "JobType", run_times: Union[int, str]):
        def callback(fn):
            self.pending_futures.discard(fn)
            try:
                events = fn.result()
            except BaseException:
                self.run_job_error(job.id)
            else:
                self.run_job_success(job.id, events)

        if iscoroutinefunction_partial(job.fn):
            if run_coroutine_job is not None:
                coroutine = run_coroutine_job(job, job.store_alias, run_times, self.logger)
                fn = self.event_loop.create_task(coroutine)
            else:
                raise AsynczException(
                    detail="Executing coroutine based jobs is not supported with Trollius."
                )
        else:
            fn = self.event_loop.run_in_executor(
                None, run_job, job, job.store_alias, run_times, self.logger
            )

        fn.add_done_callback(callback)
        self.pending_futures.add(fn)
