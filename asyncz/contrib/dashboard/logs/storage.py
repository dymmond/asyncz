from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LogEntry:
    """
    A single, immutable record representing a captured log message from a task or the engine.
    """

    ts: datetime
    """The timestamp (datetime object, preferably UTC) when the log was emitted."""
    level: str
    """The logging level of the message (e.g., 'INFO', 'ERROR')."""
    message: str
    """The formatted log message content."""
    logger: str
    """The name of the logger instance that produced the record."""
    task_id: str | None = None
    """The ID of the task associated with the log entry, if applicable."""
    extra: dict[str, Any] | None = None
    """Additional metadata from the log record's 'extra' dictionary."""


class LogStorage:
    """
    Abstract interface for log storage backends used by the Asyncz dashboard.

    All storage implementations must conform to these methods for appending new logs
    and querying existing logs.
    """

    def append(self, entry: LogEntry) -> None:  # pragma: no cover - interface
        """
        Appends a single `LogEntry` to the storage buffer.

        Args:
            entry: The `LogEntry` object to persist.
        """
        raise NotImplementedError

    def query(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> Iterable[LogEntry]:  # pragma: no cover - interface
        """
        Queries the stored logs based on various filters and limits the result size.

        Args:
            task_id: Optional. Filters logs to those originating from this specific task ID.
            level: Optional. Filters logs to match this logging level (case-insensitive).
            q: Optional. Filters logs where the message contains this substring (case-insensitive).
            limit: The maximum number of log entries to return.

        Returns:
            An iterable of matching `LogEntry` objects, ordered newest first.
        """
        raise NotImplementedError


class MemoryLogStorage(LogStorage):
    """
    A concrete `LogStorage` implementation that keeps the latest N logs in a process-local
    circular buffer (`deque`).

    This serves as a good, fast default for the dashboard but is not persistent across
    process restarts.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        """
        Initializes the in-memory storage.

        Args:
            maxlen: The maximum number of log entries to retain in the buffer. Defaults to 10,000.
        """
        self.buffer: deque[LogEntry] = deque(maxlen=maxlen)
        self.mutex: threading.Lock = threading.Lock()
        """A threading lock to ensure thread-safe access to the internal buffer."""

    def _coerce_entry(self, entry: LogEntry | dict[str, Any]) -> LogEntry:
        """
        Ensures that the input entry is a valid `LogEntry` object, performing coercion
        from a dictionary if necessary.

        It validates and normalizes fields, ensuring the timestamp is a timezone-aware
        `datetime` object (defaulting to UTC now if missing or naive).

        Args:
            entry: The input log record, either a `LogEntry` instance or a dictionary.

        Returns:
            The fully validated and normalized `LogEntry` instance.

        Raises:
            TypeError: If the input type is neither `LogEntry` nor a dictionary.
        """
        if isinstance(entry, LogEntry):
            return entry
        if not isinstance(entry, dict):
            raise TypeError(f"Unsupported log entry type: {type(entry)!r}")

        # Coerce timestamp
        ts: datetime | Any = entry.get("ts")
        if not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)
        elif ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Coerce required string fields
        level: str = str(entry.get("level", "INFO"))
        message: str = str(entry.get("message", ""))
        logger: str = str(entry.get("logger", ""))

        # Task ID (can be None)
        task_id: str | None = entry.get("task_id")

        # Extra data (must be a dict or None)
        extra: dict[str, Any] | None = entry.get("extra")
        if not isinstance(extra, dict):
            extra = None

        return LogEntry(
            ts=ts,
            level=level,
            message=message,
            logger=logger,
            task_id=task_id,
            extra=extra,
        )

    def append(self, entry: LogEntry | dict[str, Any]) -> None:
        """
        Appends a `LogEntry` (or a dictionary that is coerced into one) to the internal
        buffer in a thread-safe manner.

        If the buffer is full, the oldest entry is automatically discarded.
        """
        coerced: LogEntry = self._coerce_entry(entry)
        with self.mutex:
            self.buffer.append(coerced)

    def query(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> Iterable[LogEntry]:
        """
        Queries logs from the in-memory buffer, applying filters.

        Results are returned newest first.

        Args:
            task_id: Filters by task ID.
            level: Filters by logging level (case-insensitive).
            q: Filters by substring in the message (case-insensitive).
            limit: Maximum number of entries to return.

        Returns:
            A list of matching `LogEntry` objects.
        """
        # Prepare filters for comparison speed
        level_upper: str | None = level.upper() if level else None
        needle: str = (q or "").lower().strip()
        out: list[LogEntry] = []

        with self.mutex:
            # Iterate in reverse order (newest first)
            for e in reversed(self.buffer):
                # Filter 1: task_id
                if task_id and e.task_id != task_id:
                    continue
                # Filter 2: level
                if level_upper and e.level.upper() != level_upper:
                    continue
                # Filter 3: search query (q)
                if needle and needle not in e.message.lower():
                    continue

                out.append(e)

                # Check limit and break if reached
                if len(out) >= limit:
                    break

        # Returns a list, which is a common pattern for returning a finite result set from a query
        return out
