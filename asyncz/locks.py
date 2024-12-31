from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from threading import Lock, RLock
from typing import Any, Optional

from .file_locking import LOCK_EX, LOCK_NB, lock, unlock
from .protocols import LockProtectedProtocol


class NullLockProtected(LockProtectedProtocol):
    @contextmanager
    def protected(
        self, blocking: bool = False, timeout: Optional[int] = None
    ) -> Generator[bool, None, None]:
        yield True

    def shutdown(self) -> None:
        pass


class LockProtected(LockProtectedProtocol):
    def __init__(self) -> None:
        self.lock = self.create_lock()

    def create_lock(self) -> Lock | RLock:
        return Lock()

    def shutdown(self) -> None:
        pass

    @contextmanager
    def protected(
        self, blocking: bool = False, timeout: Optional[int] = None
    ) -> Generator[bool, None, None]:
        locked = self.lock.acquire(blocking, -1 if timeout is None else timeout)
        yield locked
        if locked:
            self.lock.release()


class RLockProtected(LockProtected):
    def create_lock(self) -> Lock | RLock:
        return RLock()


class FileLockProtected(LockProtectedProtocol):
    file_path: str

    def __init__(self, file_path: str) -> None:
        kwargs: Any = {}
        if r"{pgrp" in file_path:
            kwargs["pgrp"] = os.getpgrp()
        if r"{ppid" in file_path:
            kwargs["ppid"] = os.getppid()
        self.file_path = file_path.format(**kwargs)

    @contextmanager
    def protected(
        self, blocking: bool = False, timeout: Optional[int] = None
    ) -> Generator[bool, None, None]:
        with open(self.file_path, "w+") as file:
            flags = LOCK_EX
            if not blocking:
                flags |= LOCK_NB
            locked = lock(file, flags)
            try:
                yield locked
            finally:
                if locked:
                    unlock(file)

    def shutdown(self) -> None:
        with suppress(FileNotFoundError):
            os.remove(self.file_path)
