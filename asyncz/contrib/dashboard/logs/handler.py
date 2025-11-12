from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from asyncz.contrib.dashboard.controllers.logs import get_log_storage
from asyncz.contrib.dashboard.logs.storage import LogStorage

_TASK_ID_KEYS: tuple[str, ...] = ("task_id", "job_id", "asyncz_task_id")
"""Tuple of attribute keys checked on a LogRecord to extract the associated task ID."""


class TaskLogHandler(logging.Handler):
    """
    A custom logging handler that processes log records and writes them into a
    `LogStorage` backend.

    The primary function is to inspect the `LogRecord` for a task identifier
    (checking `_TASK_ID_KEYS`) and include it in the persisted `LogEntry`.
    """

    def __init__(self, storage: LogStorage, level: int = logging.DEBUG) -> None:
        """
        Initializes the handler.

        Args:
            storage: The `LogStorage` instance (e.g., in-memory or database) where entries will be stored.
            level: The minimum logging level to handle.
        """
        super().__init__(level=level)
        self.storage: Any = storage

    def emit(self, record: logging.LogRecord) -> None:
        """
        Processes a single `LogRecord`, extracts the task ID, formats the message,
        and appends the resulting `LogEntry` to the storage.
        """
        with contextlib.suppress(Exception):
            task_id = getattr(record, "task_id", None) or record.__dict__.get("task_id")
            self.storage.append(
                {
                    "ts": datetime.now(timezone.utc),
                    "level": record.levelname,
                    "task_id": task_id,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
            )


class TaskLoggerAdapter(logging.LoggerAdapter):
    """
    A LoggerAdapter used to automatically inject the `task_id` into every log record's
    'extra' dictionary before processing.

    This ensures that logs originating from a specific job instance are correctly
    tagged for filtering and display in the dashboard.
    """

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:  # type: ignore
        """
        Injects the `task_id` from `self.extra` into the record's `extra` dictionary.

        Args:
            msg: The log message.
            kwargs: Keyword arguments for logging, potentially containing an 'extra' dict.

        Returns:
            The original message and the modified kwargs dictionary.
        """
        extra: dict[str, Any] = kwargs.setdefault("extra", {})

        # Inject the task_id from the adapter's context, but do not clobber an
        # existing, explicit task_id provided in the log call itself.
        extra.setdefault("task_id", self.extra.get("task_id"))  # type: ignore
        return msg, kwargs


def get_task_logger(task_id: str, name: str = "asyncz") -> TaskLoggerAdapter:
    """
    Creates and returns a `TaskLoggerAdapter` instance pre-configured with a specific `task_id`.

    Args:
        task_id: The unique ID of the job/task currently executing.
        name: The name of the underlying logger (default: "asyncz.task").

    Returns:
        TaskLoggerAdapter: An adapter ready for logging within a task context.

    Example:
        >>> logger = get_task_logger("abc123")
        >>> logger.info("Starting task work")
    """
    base: logging.Logger = logging.getLogger(name)
    return TaskLoggerAdapter(base, {"task_id": task_id})


_handler: Optional[logging.Handler] = None
"""Stores the singleton instance of the installed log handler."""


def install_task_log_handler(storage: LogStorage, level: int = logging.INFO) -> logging.Handler:
    """
    Installs the `TaskLogHandler` into the root logger, ensuring logs across the
    application are routed to the specified storage.

    This function is idempotent and should be called once during application startup.

    Args:
        storage: The `LogStorage` instance to write logs to.
        level: The minimum logging level to capture (default: INFO).

    Returns:
        The installed singleton `TaskLogHandler` instance.
    """
    global _handler
    if _handler is not None:
        return _handler

    storage = storage or get_log_storage()
    _handler = TaskLogHandler(storage)

    root = logging.getLogger("asyncz")
    root.setLevel(logging.DEBUG)
    root.addHandler(_handler)
    root.propagate = True  # let parent/handlers still receive if needed
    return _handler
