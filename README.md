# Asyncz

<p align="center">
  <a href="https://asyncz.tarsil.io"><img src="https://res.cloudinary.com/tarsild/image/upload/v1687363326/packages/asyncz/asyncz-new_wiyih8.png" alt='Asyncz'></a>
</p>

<p align="center">
    <em>🚀 The scheduler that simply works. 🚀</em>
</p>

<p align="center">
<a href="https://github.com/dymmond/asyncz/actions/workflows/test-suite.yml/badge.svg?event=push&branch=main" target="_blank">
    <img src="https://github.com/dymmond/asyncz/actions/workflows/test-suite.yml/badge.svg?event=push&branch=main" alt="Test Suite">
</a>

<a href="https://pypi.org/project/asyncz" target="_blank">
    <img src="https://img.shields.io/pypi/v/asyncz?color=%2334D058&label=pypi%20package" alt="Package version">
</a>

<a href="https://pypi.org/project/asyncz" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/asyncz.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

**Documentation**: [https://asyncz.dymmond.com](https://asyncz.dymmond.com) 📚

**Source Code**: [https://github.com/dymmond/asyncz](https://github.com/dymmond/asyncz)

---

Asyncz is an async-first scheduler for Python applications and ASGI services. It wraps the core APScheduler model in a codebase that is focused on `asyncio`, explicit task objects, pluggable stores and executors, and framework-friendly lifecycle integration.

Documentation: [https://asyncz.dymmond.com](https://asyncz.dymmond.com)

## Highlights

- `AsyncIOScheduler` and `NativeAsyncIOScheduler` for async runtimes.
- Built-in triggers for `date`, `interval`, `cron`, `and`, `or`, and `shutdown`.
- Built-in stores for `memory`, `file`, `mongodb`, `redis`, and `sqlalchemy`.
- Executors for in-event-loop work, thread pools, process pools, and direct debug execution.
- CLI commands for starting schedulers and managing persisted tasks.
- Optional dashboard UI for browsing tasks and captured logs.
- Standard-library logging throughout the project.

## Installation

```bash
pip install asyncz
```

Useful extras:

```bash
pip install "asyncz[dashboard]"
pip install "asyncz[localtime]"
```

## Quick start

```python
import logging

from asyncz.schedulers import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)

scheduler = AsyncIOScheduler()


def cleanup() -> None:
    logging.getLogger(__name__).info("cleanup finished")


scheduler.add_task(cleanup, "interval", minutes=5, id="cleanup-task")
scheduler.start()
```

## Core concepts

Asyncz is built around four main component types:

- [Schedulers](https://asyncz.dymmond.com/schedulers/)
- [Triggers](https://asyncz.dymmond.com/triggers/)
- [Stores](https://asyncz.dymmond.com/stores/)
- [Executors](https://asyncz.dymmond.com/executors/)

Tasks are the public unit of scheduling. A task combines a callable, a trigger, an executor alias, and the metadata needed to persist and reschedule it correctly.

## Logging

Asyncz uses Python's built-in `logging` module. The default logger namespaces are:

- `asyncz.schedulers`
- `asyncz.executors.<alias>`
- `asyncz.stores.<alias>`

If you need custom logger creation, pass your own `loggers_class` to the scheduler. That class only needs to implement the same dictionary-like contract used by `ClassicLogging`.

## ASGI integration

Asyncz can wrap an ASGI app directly:

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()
application = scheduler.asgi(application)
```

Or you can wire startup and shutdown hooks manually:

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()

app = Lilya(
    routes=[...],
    on_startup=[scheduler.start],
    on_shutdown=[scheduler.shutdown],
)
```

The scheduler also supports synchronous and asynchronous context managers, which makes it easy to use inside lifespan handlers.

## Persistent stores and encryption

The default store is in-memory. For durable scheduling, configure a file, MongoDB, Redis, or SQLAlchemy store.

Persistent stores support the `ASYNCZ_STORE_ENCRYPTION_KEY` environment variable. When it is set, task payloads are encrypted before they are written to the backing store.

## CLI and dashboard

Asyncz ships with:

- a CLI for `start`, `add`, `list`, `run`, `pause`, `resume`, and `remove`
- a Lilya-based dashboard with task controls and a log viewer

See the documentation for usage details:

- [CLI guide](https://asyncz.dymmond.com/cli/)
- [Dashboard guide](https://asyncz.dymmond.com/dashboard/dashboard/)
