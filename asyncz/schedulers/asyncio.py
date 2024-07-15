from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from asyncz.executors.asyncio import AsyncIOExecutor
from asyncz.schedulers.base import BaseScheduler
from asyncz.schedulers.utils import run_in_event_loop
from asyncz.utils import maybe_ref

if TYPE_CHECKING:
    from asyncz.executors.base import BaseExecutor


class AsyncIOScheduler(BaseScheduler):
    """
    A scheduler that runs on an asyncio event loop.

    This scheduler is typically to run with asyncio which means that any ASGI framework can also
    use it internally if needed. For example, Esmerald and Starlette.

    Args:
        event_loop: AsyncOP event loop to use. Default to the global event loop.
    """

    event_loop: Any = None
    timer: Optional[Any] = None

    def start(self, paused: bool = False) -> bool:
        if not self.event_loop:
            try:
                self.event_loop = asyncio.get_running_loop()
            except RuntimeError:
                self.event_loop = asyncio.new_event_loop()
        return super().start(paused)

    @run_in_event_loop
    def _shutdown(self, wait: bool = True) -> None:
        if super().shutdown(wait):
            self.stop_timer()

    def shutdown(self, wait: bool = True) -> bool:
        # not decremented yet so +1
        result = self.ref_counter
        self._shutdown(wait)
        return result > 1

    def _setup(self, config: Any) -> None:
        self.event_loop = maybe_ref(config.pop("event_loop", None))
        super()._setup(config)

    def start_timer(self, wait_seconds: Optional[float] = None) -> None:
        self.stop_timer()
        if wait_seconds is not None:
            self.timer = self.event_loop.call_later(wait_seconds, self.wakeup)

    def stop_timer(self) -> None:
        if getattr(self, "timer", None):
            self.timer.cancel()  # type: ignore
            self.timer = None

    @run_in_event_loop
    def wakeup(self) -> None:
        self.stop_timer()
        wait_seconds = self.process_tasks()
        self.start_timer(wait_seconds)

    def create_default_executor(self) -> BaseExecutor:
        return AsyncIOExecutor()
