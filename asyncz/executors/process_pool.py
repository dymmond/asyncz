import concurrent.futures
from multiprocessing import Pipe, connection
from threading import Thread
from typing import TYPE_CHECKING, Any, Optional, cast

from asyncz.executors.pool import BasePoolExecutor

if TYPE_CHECKING:
    import logging

    from asyncz.schedulers.types import SchedulerType

# because multiprocessing is heavy weight, it is split out from pool


class ProcessPoolLoggerSenderFnWrap:
    def __init__(self, send_pipe: connection.Connection, fn_name: str) -> None:
        self.send_pipe = send_pipe
        self.fn_name = fn_name

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.send_pipe.send((self.fn_name, args, kwargs))


class ProcessPoolLoggerSender:
    def __init__(self, send_pipe: connection.Connection) -> None:
        self.send_pipe = send_pipe

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            return object.__getattr__(self, item)
        return ProcessPoolLoggerSenderFnWrap(self.send_pipe, item)


class ProcessPoolReceiver(Thread):
    def __init__(self, receive_pipe: connection.Connection, logger: "logging.Logger") -> None:
        super().__init__()
        self.receive_pipe = receive_pipe
        self.logger = logger
        self.start()

    def run(self) -> None:
        try:
            while True:
                fn_name, args, kwargs = self.receive_pipe.recv()
                if not fn_name.startswith("_"):
                    getattr(self.logger, fn_name)(*args, **kwargs)
        except EOFError:
            pass


class ProcessPoolExecutor(BasePoolExecutor):
    """
    An executor that runs tasks in a concurrent.futures process pool.

    Args:
        max_workers: The maximum number of spawned processes.
        pool_kwargs: Dict of keyword arguments to pass to the underlying
            ProcessPoolExecutor constructor.
    """

    def __init__(
        self, max_workers: int = 10, pool_kwargs: Optional[Any] = None, **kwargs: Any
    ) -> None:
        self.receive_pipe, self.send_pipe = Pipe(False)
        pool_kwargs = pool_kwargs or {}
        pool = concurrent.futures.ProcessPoolExecutor(int(max_workers), **pool_kwargs)
        super().__init__(pool, **kwargs)

    def start(self, scheduler: "SchedulerType", alias: str) -> None:
        super().start(scheduler, alias)
        assert self.logger is not None, "logger is None"
        # move the old logger to logger_receiver
        self.logger_receiver = ProcessPoolReceiver(self.receive_pipe, self.logger)
        # and send the process logger instead
        self.logger = cast("logging.Logger", ProcessPoolLoggerSender(self.send_pipe))

    def shutdown(self, wait: bool = True) -> None:
        super().shutdown(wait=wait)
        self.send_pipe.close()
        self.logger_receiver.join()
