# AsyncZ Dashboard — Logs System

The AsyncZ Dashboard now ships with a built-in log viewer that lets you see all scheduler and task logs directly in the web interface — live, searchable, and filterable by task, log level, or message.

This guide explains everything about how it works, how to configure it, and how to extend it for your own applications.

## 🌟 Overview

AsyncZ uses a modular, pluggable logging architecture designed for flexibility:
- 🧩 **LogStorage interface** — defines how logs are stored and queried.
- ⚙️ **MemoryLogStorage** — default in-memory ring buffer (fast, simple, resets oldest entries).
- 🪵 **TaskLogHandler** — a logging.Handler that routes log records into the storage backend.
- 🔌 **install_task_log_handler()** — installs the handler globally.
- 🧠 **Dashboard integration** — `/dashboard/logs/` UI renders all recent logs with filters and live updates.
- 🧱 **Custom storage backends** — you can implement your own, such as file rotation, JSON persistence, Postgres, or Redis.

## Default Behavior

When you create the dashboard admin interface via:

```python
from asyncz.contrib.dashboard import AsyncZAdmin

admin = AsyncZAdmin(
    scheduler=scheduler,
)
```

AsyncZ automatically:
1. Creates or reuses a global `MemoryLogStorage` instance.
2. Installs a `TaskLogHandler` to the AsyncZ root logger (`asyncz` namespace).
3. Captures all logs emitted through AsyncZ’s task runners and scheduler.

You can now view all captured logs at:

```
http://localhost:8000/dashboard/logs/
```

## Passing Your Own Log Storage

AsyncZ allows you to define your own log storage backend.
You can pass a custom instance to `AsyncZAdmin`:

```python
from asyncz.contrib.dashboard import AsyncZAdmin
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage

custom_storage = MemoryLogStorage(maxlen=20_000)

admin = AsyncZAdmin(
    scheduler=scheduler,
    log_storage=custom_storage,
)
```

This ensures the dashboard uses your chosen backend for all incoming logs.

## Architecture Deep Dive

### LogStorage Interface

All log storage backends implement this abstract base:

```python
class LogStorage:
    def append(self, entry: LogEntry) -> None:
        """Store a new log entry."""
        raise NotImplementedError

    def query(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> Iterable[LogEntry]:
        """Return logs filtered by the given criteria."""
        raise NotImplementedError
```

You can get via:

```python
from asyncz.contrib.dashboard.logs.storage import LogStorage
```

### LogEntry

Every captured log is represented as a dataclass:

```python
@dataclass(frozen=True)
class LogEntry:
    ts: datetime
    level: str
    message: str
    logger: str
    task_id: str | None = None
    extra: dict[str, Any] | None = None
```

You can get via:

```python
from asyncz.contrib.dashboard.logs.storage import LogEntry
```

## Default In-Memory Storage

The default `MemoryLogStorage` keeps a ring buffer of the most recent logs:

```python
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage

storage = MemoryLogStorage(maxlen=10_000)
```

When the buffer reaches its maximum (`maxlen`):
    - The oldest logs are automatically discarded, ensuring constant memory usage.
    - You can inspect internal stats via `.stats()` if implemented (size, total appended, dropped).

## Integration with Python Logging and Structlog

### Standard Logging

AsyncZ installs the handler like this:

```python
from asyncz.contrib.dashboard.logs.handler import install_task_log_handler

install_task_log_handler(storage)
```

Internally, this attaches `TaskLogHandler` to the root logger, so all logs from AsyncZ and user tasks flow into the dashboard.

### Structlog Support

If your application uses `structlog`, you don’t need special configuration —
as long as `structlog` is configured to emit via the stdlib logging system.

Example:

```python
import structlog
from structlog.stdlib import LoggerFactory, ProcessorFormatter

structlog.configure(
    logger_factory=LoggerFactory(),
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
)
```

AsyncZ’s `TaskLogHandler` will automatically capture these events, including any `task_id` bound to the record (e.g., `logger.bind(task_id=...)`).

## 🧱 Building Custom Log Storages

You can build persistent or specialized backends by subclassing `LogStorage`.

### 1. Rotating File Logs

```python
import logging
from logging.handlers import RotatingFileHandler
from asyncz.contrib.dashboard.logs.storage import LogStorage, LogEntry

class RotatingFileStorage(LogStorage):
    def __init__(self, path="asyncz.log", max_bytes=1_000_000, backup_count=5):
        self.handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    def append(self, entry: LogEntry):
        record = logging.LogRecord(
            name=entry.logger,
            level=getattr(logging, entry.level.upper(), logging.INFO),
            pathname="",
            lineno=0,
            msg=entry.message,
            args=None,
            exc_info=None,
        )
        self.handler.emit(record)

    def query(self, **kwargs):
        # Simple case: reading back not supported for file-based rotation
        return []
```

### 2. JSON File Storage

```python
import json
from pathlib import Path
from asyncz.contrib.dashboard.logs.storage import LogStorage, LogEntry

class JSONLogStorage(LogStorage):
    def __init__(self, path: str = "asyncz_logs.json"):
        self.path = Path(path)
        self.path.touch(exist_ok=True)

    def append(self, entry: LogEntry):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__, default=str) + "\n")

    def query(self, **_):
        with self.path.open("r", encoding="utf-8") as f:
            for line in f.readlines()[-200:]:
                yield LogEntry(**json.loads(line))
```

### 3. Postgres Storage

You can persist logs to a relational database:

```python
import asyncpg
from asyncz.contrib.dashboard.logs.storage import LogStorage, LogEntry

class PostgresLogStorage(LogStorage):
    def __init__(self, dsn: str):
        self.dsn = dsn

    async def append(self, entry: LogEntry):
        conn = await asyncpg.connect(self.dsn)
        await conn.execute(
            "INSERT INTO asyncz_logs (ts, level, message, logger, task_id, extra) VALUES ($1,$2,$3,$4,$5,$6)",
            entry.ts, entry.level, entry.message, entry.logger, entry.task_id, entry.extra,
        )
        await conn.close()

    async def query(self, **filters):
        # Implementation using SQL filters and LIMIT
        ...
```

You can later render them via the same dashboard controllers (e.g., `LogsTablePartialController`) by providing your custom storage instance to `AsyncZAdmin()`.

### 4. Redis Storage

For distributed or multi-process schedulers, you can store logs in Redis:

```python
import json, redis
from asyncz.contrib.dashboard.logs.storage import LogStorage, LogEntry

class RedisLogStorage(LogStorage):
    def __init__(self, url="redis://localhost:6379", key="asyncz:logs", maxlen=10_000):
        self.client = redis.from_url(url)
        self.key = key
        self.maxlen = maxlen

    def append(self, entry: LogEntry):
        self.client.xadd(self.key, entry.__dict__, maxlen=self.maxlen, approximate=True)

    def query(self, limit=200, **_):
        messages = self.client.xrevrange(self.key, count=limit)
        for _, fields in messages:
            yield LogEntry(**{k.decode(): v.decode() for k, v in fields.items()})
```

This approach lets multiple AsyncZ nodes push logs to a shared centralized stream.

## Using AsyncZAdmin

If you’re using the higher-level `AsyncZAdmin`, you can pass your storage directly:

```python
from asyncz.contrib.dashboard import AsyncZAdmin
from myproject.logging import RedisLogStorage

admin = AsyncZAdmin(
    scheduler=scheduler,
    log_storage=RedisLogStorage(),
)
```

Internally, `AsyncZAdmin` passes your custom storage to the dashboard creation and configuration automatically.

## Dashboard UI Features
- Automatic refresh every 10 seconds.
- Filters: by task ID, log level, or search term.
- Limit: configurable via the UI (default 200).
- Reset: clears filters and reloads latest entries.
- Zero reload: all dynamic via HTMX partials.

## Summary

| Feature | Description |
|----------|-------------|
| **Default backend** | `MemoryLogStorage` (in-memory, circular buffer). |
| **Custom backends** | Easily subclass `LogStorage` for file, JSON, DB, Redis, etc. |
| **Live dashboard** | `/dashboard/logs/` auto-refreshes every 10s with filters. |
| **Integration** | Works seamlessly with Python logging and structlog. |
| **Configurable** | Pass `log_storage` to `AsyncZAdmin`. |

## Best Practices

- Use `MemoryLogStorage` in development and testing.
- Use persistent storage (Redis/Postgres) in production if logs must survive restarts.
- Bind your `task_id` in tasks for clearer traceability:

```python
import logging
log = logging.getLogger("asyncz.task")
log.info("Task started", extra={"task_id": job.id})
```

- For structlog, use `logger.bind(task_id=job.id)`.
