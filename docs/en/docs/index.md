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

Asyncz is an async-first scheduler for Python applications and ASGI services. It keeps the familiar scheduler / trigger / store / executor model, but it is built around `asyncio`, explicit task objects, framework lifecycle integration, and predictable standard-library logging.

## Why Asyncz

- `AsyncIOScheduler` for regular async applications.
- `NativeAsyncIOScheduler` for environments that already own the event loop.
- Built-in triggers for one-off work, recurring intervals, cron expressions, combinations, and shutdown hooks.
- Multiple persistence options for local development and production deployments.
- CLI and dashboard tooling for operational workflows.

## Install

```bash
pip install asyncz
```

Optional extras:

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

## What to read next

- [Schedulers](./schedulers.md) for configuration, lifecycle, and logging.
- [Triggers](./triggers.md) for scheduling rules.
- [Tasks](./tasks.md) for task objects, decorator mode, and lifecycle generators.
- [Stores](./stores.md) for persistence and encryption.
- [Executors](./executors.md) for runtime execution strategy.
- [ASGI and Context Managers](./asgi.md) for framework integration.
- [CLI](./cli.md) for operational workflows.
- [Dashboard](./dashboard/dashboard.md) for the optional admin UI.

## Logging

Asyncz uses Python's built-in `logging` module. The default logger namespaces are:

- `asyncz.schedulers`
- `asyncz.executors.<alias>`
- `asyncz.stores.<alias>`

If you need custom logger creation, pass a custom `loggers_class` when constructing the scheduler.

## Persistence and encryption

The default store is `memory`. For durable scheduling, Asyncz also ships with `file`, `mongodb`, `redis`, and `sqlalchemy` stores.

Persistent stores support `ASYNCZ_STORE_ENCRYPTION_KEY`. When it is set, serialized task payloads are encrypted before they are written to the backing store.
