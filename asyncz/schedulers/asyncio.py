import asyncio
from typing import Any, Optional

from asyncz.executors.asyncio import AsyncIOExecutor
from asyncz.schedulers.base import BaseScheduler
from asyncz.schedulers.utils import run_in_event_loop
from asyncz.typing import DictAny
from asyncz.utils import maybe_ref


class AsyncIOScheduler(BaseScheduler):
    """
    A scheduler that runs on an asyncio event loop.

    This scheduler is typically to run with asyncio which means that any ASGI framework can also
    use it internally if needed. For example, Esmerald and Starlette.

    Args:
        event_loop: AsyncOP event loop to use. Default to the global event loop.
    """

    def __init__(
        self, event_loop: Optional[Any] = None, timeout: Optional[int] = None, **kwargs: "DictAny"
    ) -> None:
        super().__init__(**kwargs)
        self.event_loop = event_loop
        self.timeout = timeout

    def start(self, paused: bool = False):
        if not self.event_loop:
            self.event_loop = asyncio.get_event_loop()
        super().start(paused)

    @run_in_event_loop
    def shutdown(self, wait: bool = True):
        super().shutdown(wait)
        self.stop_timer()

    def _setup(self, config: "DictAny") -> None:
        self.event_loop = maybe_ref(config.pop("event_loop", None))
        super()._setup(config)

    def start_timer(self, wait_seconds: Optional[int] = None):
        self.stop_timer()
        if wait_seconds is not None:
            self.timeout = self.event_loop.call_later(wait_seconds, self.wakeup)

    def stop_timer(self):
        if self.timeout:
            self.timeout.cancel()
            del self.timezone

    @run_in_event_loop
    def wakeup(self):
        self.stop_timer()
        wait_seconds = self.process_tasks()
        self.start_timer(wait_seconds)

    def create_default_executor(self):
        return AsyncIOExecutor()
