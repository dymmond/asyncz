import concurrent.futures
from abc import abstractmethod
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import ConfigDict

from asyncz.executors.base import BaseExecutor, run_task

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class BasePoolExecutor(BaseExecutor):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True, populate_by_name=True)
    cancel_futures: bool = False
    overwrite_wait: Optional[bool] = None

    @abstractmethod
    def __init__(self, pool: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pool = pool

    def do_send_task(self, task: "TaskType", run_times: list[datetime]) -> Any:
        task_id = task.id
        assert task_id is not None, "Cannot send decorator type task"

        def callback(fn: Any) -> None:
            exc, _ = (
                fn.exception_info()
                if hasattr(fn, "exception_info")
                else (fn.exception(), getattr(fn.exception(), "__traceback__", None))
            )
            if exc:
                self.run_task_error(task_id)
            else:
                self.run_task_success(task_id, fn.result())

        try:
            fn = self.pool.submit(run_task, task, task.store_alias, run_times, self.logger)
        except (BrokenProcessPool, TypeError):
            self.scheduler.loggers[self.logger_name].warning(
                "Process pool is broken. Replacing pool with a new instance."
            )
            self.pool = self.pool.__class__(self.pool.max_workers)
            fn = self.pool.submit(run_task, task, task.store_alias, run_times, self.logger)

        fn.add_done_callback(callback)

    def shutdown(self, wait: bool = True) -> None:
        if self.overwrite_wait is not None:
            wait = self.overwrite_wait
        self.pool.shutdown(wait, cancel_futures=self.cancel_futures)
        self.pool.shutdown(wait)


class ThreadPoolExecutor(BasePoolExecutor):
    """
    An executor that runs tasks in a concurrent.futures thread pool.

    Args:
        max_workers: The maximum number of spawned threads.
        pool_kwargs: Dict of keyword arguments to pass to the underlying ThreadPoolExecutor constructor.
    """

    def __init__(self, max_workers: int = 10, pool_kwargs: Optional[Any] = None, **kwargs: Any):
        pool_kwargs = pool_kwargs or {}
        pool = concurrent.futures.ThreadPoolExecutor(int(max_workers), **pool_kwargs)
        super().__init__(pool, **kwargs)
