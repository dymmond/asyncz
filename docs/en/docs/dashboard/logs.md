# Asyncz Dashboard Logs

The dashboard log viewer is built on top of Python's standard `logging` module. It captures records from the `asyncz` logger namespace and stores them in a pluggable log storage backend.

## Default behavior

When the dashboard is mounted, Asyncz:

1. creates or reuses a log storage backend
2. installs `TaskLogHandler` on the `asyncz` logger namespace
3. renders log rows through `/dashboard/logs/` and `/dashboard/logs/partials/table`

## Logging from tasks

For task-scoped logging, use `get_task_logger(...)`.

```python
from asyncz.contrib.dashboard.logs.handler import get_task_logger

logger = get_task_logger("task-123")
logger.info("starting work")
```

`TaskLogHandler` looks for a task id in these record fields:

- `task_id`
- `job_id`
- `asyncz_task_id`

That means regular stdlib logging also works:

```python
import logging

logging.getLogger("asyncz.jobs").info("task completed", extra={"job_id": "task-123"})
```

## Custom storage

All storage backends implement this interface:

```python
from collections.abc import Iterable

from asyncz.contrib.dashboard.logs.storage import LogEntry


class LogStorage:
    def append(self, entry: LogEntry) -> None:
        ...

    def query(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> Iterable[LogEntry]:
        ...
```

The built-in default is `MemoryLogStorage`.

```python
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage

storage = MemoryLogStorage(maxlen=20_000)
```

Pass a custom storage instance into `AsynczAdmin`:

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin

admin = AsynczAdmin(scheduler=scheduler, log_storage=storage)
```

## Query parameters used by the UI

The table partial accepts:

- `task_id`
- `level`
- `q`
- `limit`

Example:

```text
/dashboard/logs/partials/table?task_id=task-123&level=ERROR&q=timeout
```
