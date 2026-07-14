from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from asyncz.datastructures import TaskState
from asyncz.locks import FileLockProtected, NullLockProtected
from asyncz.shapes import Shape, ShapeContext, ShapeError, resolve_shape
from asyncz.shapes.errors import ShapeDeserializationError, ShapeMigrationError
from asyncz.state import BaseStateExtra
from asyncz.stores.persistence import (
    TASK_STATE_ENTITY,
    TASK_STATE_ENVELOPE_VERSION,
    TaskStateEnvelope,
)
from asyncz.stores.types import StoreType

if TYPE_CHECKING:
    from asyncz.protocols import LockProtectedProtocol
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class BaseStore(BaseStateExtra, StoreType):
    """
    Base class for all task stores.

    The store contract owns persistence location, encryption, and restoration
    lifecycle. Shape integration is limited to representation conversion at the
    task-state boundary.
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize shared store state before scheduler startup.

        Stores receive their final scheduler-selected Shape in `start()`, but a
        default Shape is available immediately for tests and manually invoked
        serialization helpers.
        """

        super().__init__(**kwargs)
        self.scheduler: Optional[SchedulerType] = None
        self.encryption_key: Optional[AESCCM] = None
        self.shape: Shape = resolve_shape()

    def create_lock(self) -> LockProtectedProtocol:
        """
        Creates a lock protector.

        File locking is still owned by stores and scheduler configuration. Shapes
        do not participate in concurrency or locking decisions.
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

        The selected scheduler Shape is captured here so persisted task envelopes
        include deterministic Shape identity for future restoration.
        """
        self.scheduler = scheduler
        self.alias = alias
        self.logger_name = f"asyncz.stores.{alias}"
        self.lock = self.create_lock()
        scheduler_shape = getattr(scheduler, "shape", None)
        try:
            self.shape = resolve_shape(scheduler_shape)
        except ShapeError:
            self.shape = resolve_shape()
        encryption_key = os.environ.get("ASYNCZ_STORE_ENCRYPTION_KEY")
        if encryption_key:
            # we simply use a hash. This way all kinds of tokens, lengths and co are supported
            self.encryption_key = AESCCM(hashlib.new("sha256", encryption_key.encode()).digest())

    def shutdown(self) -> None:
        """
        Frees any resources still bound to this task store.

        Subclasses remain responsible for closing backend-specific resources
        before delegating to this shared cleanup hook.
        """
        if self.lock:
            self.lock.shutdown()

    def conditional_decrypt(self, inp: bytes) -> bytes:
        """
        Decrypt persisted store bytes when encryption is configured.

        Encryption stays outside Shape payload conversion. Shapes receive and
        return Python values, while stores own the encrypted byte boundary.
        """

        if self.encryption_key:
            return self.encryption_key.decrypt(inp[:13], inp[13:], None)
        else:
            return inp

    def conditional_encrypt(self, inp: bytes) -> bytes:
        """
        Encrypt persisted store bytes when encryption is configured.

        The method preserves the existing store encryption behavior and keeps
        cryptographic decisions separate from Shape selection.
        """

        if self.encryption_key:
            nonce = os.urandom(13)
            return nonce + self.encryption_key.encrypt(nonce, inp, None)
        else:
            return inp

    def serialize_task_state(self, task: TaskType) -> TaskStateEnvelope:
        """
        Build a versioned task-state envelope for durable stores.

        The task still owns its runtime state through `__getstate__()`. The
        payload preserves that Asyncz-owned state natively so trigger objects and
        callable references keep the same pickle behavior as legacy records.
        """

        state = task.__getstate__()
        return TaskStateEnvelope(
            entity=TASK_STATE_ENTITY,
            version=TASK_STATE_ENVELOPE_VERSION,
            shape=self.shape.name,
            payload=state,
        )

    def deserialize_task_state(self, stored_state: Any) -> TaskState:
        """
        Restore a task state from a legacy record or versioned envelope.

        Legacy `TaskState` pickles are accepted for backward compatibility. New
        envelopes must declare the expected entity, version, and registered Shape
        before restoration proceeds.
        """

        if isinstance(stored_state, TaskState):
            return stored_state

        if not isinstance(stored_state, TaskStateEnvelope):
            raise ShapeMigrationError(
                f"Unsupported Asyncz task state record type: {stored_state.__class__.__name__}."
            )
        if stored_state.entity != TASK_STATE_ENTITY:
            raise ShapeMigrationError(
                f"Unsupported Asyncz persisted entity: {stored_state.entity}."
            )
        if stored_state.version != TASK_STATE_ENVELOPE_VERSION:
            raise ShapeMigrationError(
                f"Unsupported Asyncz task state version: {stored_state.version}."
            )

        shape = resolve_shape(stored_state.shape)
        context = ShapeContext(
            entity=stored_state.entity,
            operation="restore",
            scheduler_identity=getattr(self.scheduler, "identity", None),
            schema_version=stored_state.version,
        )
        state = shape.load(TaskState, stored_state.payload, context=context)
        if not isinstance(state, TaskState):
            raise ShapeDeserializationError("Task state Shape did not restore a TaskState.")
        return state

    def fix_paused_tasks(self, tasks: list[TaskType]) -> None:
        """
        Move paused tasks behind scheduled tasks after backend sorting.

        This ordering rule remains a store concern and is intentionally unrelated
        to Shape selection or task-state serialization.
        """

        for index, task in enumerate(tasks):
            if task.next_run_time is not None:
                if index > 0:
                    paused_tasks = tasks[:index]
                    del tasks[:index]
                    tasks.extend(paused_tasks)
                break

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
