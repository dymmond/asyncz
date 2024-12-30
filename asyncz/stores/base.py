from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from asyncz.locks import FileLockProtected, NullLockProtected
from asyncz.state import BaseStateExtra
from asyncz.stores.types import StoreType

if TYPE_CHECKING:
    from asyncz.protocols import LockProtectedProtocol
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class BaseStore(BaseStateExtra, StoreType):
    """
    Base class for all task stores.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scheduler: Optional[SchedulerType] = None
        self.encryption_key: Optional[AESCCM] = None

    def create_lock(self) -> LockProtectedProtocol:
        """
        Creates a lock protector.
        """
        if not self.scheduler or not self.scheduler.lock_path:
            return NullLockProtected()
        return FileLockProtected(self.scheduler.lock_path.replace(r"{store}", self.alias))

    def start(self, scheduler: SchedulerType, alias: str) -> None:
        """
        Called by the scheduler when the scheduler is being started or when the task store is being
        added to an already running scheduler.

        Args:
            scheduler: The scheduler that is starting this task store.
            alias: Alias of this task store as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.alias = alias
        self.logger_name = f"asyncz.stores.{alias}"
        self.lock = self.create_lock()
        encryption_key = os.environ.get("ASYNCZ_STORE_ENCRYPTION_KEY")
        if encryption_key:
            # we simply use a hash. This way all kinds of tokens, lengths and co are supported
            self.encryption_key = AESCCM(hashlib.new("sha256", encryption_key.encode()).digest())

    def shutdown(self) -> None:
        """
        Frees any resources still bound to this task store.
        """
        if self.lock:
            self.lock.shutdown()

    def conditional_decrypt(self, inp: bytes) -> bytes:
        if self.encryption_key:
            return self.encryption_key.decrypt(inp[:13], inp[13:], None)
        else:
            return inp

    def conditional_encrypt(self, inp: bytes) -> bytes:
        if self.encryption_key:
            nonce = os.urandom(13)
            return nonce + self.encryption_key.encrypt(nonce, inp, None)
        else:
            return inp

    def fix_paused_tasks(self, tasks: list[TaskType]) -> None:
        for index, task in enumerate(tasks):
            if task.next_run_time is not None:
                if index > 0:
                    paused_tasks = tasks[:index]
                    del tasks[:index]
                    tasks.extend(paused_tasks)
                break

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
