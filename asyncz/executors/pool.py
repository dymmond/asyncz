import concurrent.futures
from abc import abstractmethod
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from asyncz.executors.base import BaseExecutor, run_task
from asyncz.typing import DictAny

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class BasePoolExecutor(BaseExecutor):
    @abstractmethod
    def __init__(self, pool: Any, **kwargs: "DictAny"):
        super().__init__(**kwargs)
        self.pool = pool

    def do_send_task(self, task: "TaskType", run_times: List[datetime]) -> Any:
        def callback(fn):
            exc, _ = (
                fn.exception_info()
                if hasattr(fn, "exception_info")
                else (fn.exception(), getattr(fn.exception(), "__traceback__", None))
            )
            if exc:
                self.run_task_error(task.id)
            else:
                self.run_task_success(task.id, fn.result())

        try:
            fn = self.pool.submit(run_task, task, task.store_alias, run_times)
        except (BrokenProcessPool, TypeError):
            self.logger.warning("Process pool is broken. Replacing pool with a new instance.")
            self.pool = self.pool.__class__(self.pool.max_workers)
            fn = self.pool.submit(run_task, task, task.store_alias, run_times, self.logger)

        fn.add_done_callback(callback)

    def shutdown(self, wait=True):
        self.pool.shutdown(wait)

    class Config(BaseExecutor.Config):
        allow_population_by_field_name = True


class ThreadPoolExecutor(BasePoolExecutor):
    """
    An executor that runs tasks in a concurrent.futures thread pool.

    Args:
        max_workers: The maximum number of spawned threads.
        pool_kwargs: Dict of keyword arguments to pass to the underlying ThreadPoolExecutor constructor.
    """

    max_workers: Optional[int]
    pool_kwargs: Optional["DictAny"]

    def __init__(self, max_workers: int = 10, pool_kwargs: Optional["DictAny"] = None):
        pool_kwargs = pool_kwargs or {}
        pool = concurrent.futures.ThreadPoolExecutor(int(max_workers), **pool_kwargs)
        super().__init__(pool)


class ProcessPoolExecutor(BasePoolExecutor):
    """
    An executor that runs tasks in a concurrent.futures process pool.

    Args:
        max_workers: The maximum number of spawned processes.
        pool_kwargs: Dict of keyword arguments to pass to the underlying
            ProcessPoolExecutor constructor.
    """

    max_workers: Optional[int]
    pool_kwargs: Optional["DictAny"]

    def __init__(self, max_workers: int = 10, pool_kwargs: Optional["DictAny"] = None):
        pool_kwargs = pool_kwargs or {}
        pool = concurrent.futures.ProcessPoolExecutor(int(max_workers), **pool_kwargs)
        super().__init__(pool)
