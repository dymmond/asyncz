from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from threading import Event, Thread
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
    use it internally if needed. For example, Ravyn and Starlette.

    Args:
        event_loop: AsyncIO event loop to use. Default to the global event loop.
        isolated_event_loop: Use a fresh, isolated event_loop instead the existing.
    """

    isolated_event_loop: bool = False
    event_loop_thread: Optional[Thread] = None
    timer: Optional[Any] = None

    def _init_new_loop(self, event: Event) -> None:
        # called in thread
        self.event_loop = loop = asyncio.new_event_loop()
        event.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def start(self, paused: bool = False) -> bool:
        if not self.event_loop:
            try:
                if self.isolated_event_loop:
                    raise RuntimeError()
                self.event_loop = asyncio.get_running_loop()
            except RuntimeError:
                event = Event()
                self.event_loop_thread = Thread(
                    target=self._init_new_loop, args=[event], daemon=True
                )
                self.event_loop_thread.start()
                event.wait()
        return super().start(paused)

    @run_in_event_loop
    def _shutdown(self, wait: bool = True) -> None:
        if super().shutdown(wait):
            self.stop_timer()
            thread = self.event_loop_thread
            if thread:
                self.event_loop.stop()
                self.event_loop = self.event_loop_thread = None
                with contextlib.suppress(RuntimeError):
                    thread.join()

    def shutdown(self, wait: bool = True) -> bool:
        # not decremented yet so +1
        result = self.ref_counter
        self._shutdown(wait)
        return result > 1

    def _setup(self, config: Any) -> None:
        self.event_loop = maybe_ref(config.pop("event_loop", None))
        self.isolated_event_loop = bool(config.pop("isolated_event_loop", False))
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


class NativeAsyncIOScheduler(AsyncIOScheduler):
    """
    A scheduler that runs on an existing asyncio event loop.

    This scheduler is typically to run with asyncio which means that any ASGI framework can also
    use it internally if needed. For example, Ravyn and Starlette.

    Args:
        isolated_event_loop: Use a fresh, isolated event_loop instead the existing.
    """

    _shutdown_handle: Any = None

    async def start(self, paused: bool = False) -> bool:  # type: ignore
        if self.isolated_event_loop:
            event = Event()
            self.event_loop_thread = Thread(target=self._init_new_loop, args=[event], daemon=True)
            self.event_loop_thread.start()
            await asyncio.to_thread(event.wait)
        else:
            self.event_loop = asyncio.get_running_loop()

        return super(AsyncIOScheduler, self).start(paused)

    def handle_shutdown_coros(self, coros: Sequence[Any]) -> None:
        if coros:
            self._shutdown_handle = asyncio.gather(*coros)
        else:
            self._shutdown_handle = None

    async def shutdown(self, wait: bool = True) -> bool:  # type: ignore
        # not decremented yet so +1
        result = self.ref_counter
        if super(AsyncIOScheduler, self).shutdown(wait):
            handle = self._shutdown_handle
            if handle is not None:
                self._shutdown_handle = None
                await handle
            self.stop_timer()
            thread = self.event_loop_thread
            if thread:
                self.event_loop.stop()
                self.event_loop = self.event_loop_thread = None
                await asyncio.to_thread(thread.join)
        return result > 1

    def _setup(self, config: Any) -> None:
        self.isolated_event_loop = bool(config.pop("isolated_event_loop", False))
        super(AsyncIOScheduler, self)._setup(config)
