from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from asyncz.schedulers import AsyncIOScheduler


class LockProtectedProtocol(Protocol):
    """
    Protocol defining an interface for objects that provide non-blocking,
    lock-protected operations.

    This is typically used by components (like Job Stores) within the scheduler
    to synchronize access across threads or processes, often backing the scheduler's
    own locking mechanism.
    """

    def protected(
        self, blocking: bool = False, timeout: Optional[int] = None
    ) -> AbstractContextManager[bool]:
        """
        Returns a context manager that ensures exclusive access to a resource.

        Args:
            blocking: If `True`, the call will block indefinitely until the lock is acquired.
                      If `False`, the call returns immediately. Defaults to `False`.
            timeout: The maximum duration (in seconds) to wait for the lock if `blocking` is `True`.

        Returns:
            An `AbstractContextManager` that yields `True` if the lock was acquired
            or `False` if the lock was not acquired (when non-blocking).
        """
        ...

    def shutdown(self) -> None:
        """
        Shuts down the lock protection mechanism, releasing any held resources.
        """
        ...


class AsynczClientProtocol(Protocol):
    """
    Protocol defining the interface for obtaining the core `AsyncIOScheduler` instance.

    This is used by classes (like the CLI application runner) that need direct access
    to the scheduler to manage its lifecycle or interact with its tasks.
    """

    def get_scheduler(self) -> AsyncIOScheduler:
        """
        Retrieves the main scheduler instance managed by the conforming object.

        Returns:
            The active `AsyncIOScheduler` instance.
        """
        ...
