from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Set

from asyncz.executors.base import BaseExecutor, run_coroutine_task, run_task
from asyncz.utils import iscoroutinefunction_partial

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class AsyncIOExecutor(BaseExecutor):
    """
    Executor used for AsyncIO, typically can also be plugged into any ASGI framework as well,
    for example, Esmerald, Starlite, FastAPI...

    Runs the task in the default executor event loop.

    If the task function is a native coroutine function, it is scheduled to be run directly in the
    event loop as soon as possible. All other functions are run in the event loop's default
    executor which is usually a thread pool.
    """

    def start(self, scheduler: Any, alias: str) -> None:
        super().start(scheduler, alias)
        self.event_loop = scheduler.event_loop
        self.pending_futures: Set[Any] = set()

    def shutdown(self, wait: bool = True) -> None:
        for f in self.pending_futures:
            if not f.done():
                f.cancel()

        self.pending_futures.clear()

    def do_send_task(self, task: "TaskType", run_times: List[datetime]) -> None:
        task_id = task.id
        assert task_id is not None, "Cannot send decorator type task"

        def callback(fn: Any) -> None:
            self.pending_futures.discard(fn)
            try:
                events = fn.result()
            except BaseException:
                self.run_task_error(task_id)
            else:
                self.run_task_success(task_id, events)

        if iscoroutinefunction_partial(task.fn):
            coroutine = run_coroutine_task(task, task.store_alias, run_times, self.logger)  # type: ignore
            fn = self.event_loop.create_task(coroutine)
        else:
            fn = self.event_loop.run_in_executor(
                None, run_task, task, task.store_alias, run_times, self.logger
            )

        fn.add_done_callback(callback)
        self.pending_futures.add(fn)
