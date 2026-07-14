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

Asyncz is a production scheduler for async Python applications and ASGI services. It keeps the familiar scheduler / trigger / store / executor model, but it is built around `asyncio`, explicit task objects, framework lifecycle integration, durable stores, Python standard logging, and operator tooling that works from both the CLI and the browser.

Use Asyncz when scheduled work needs to be observable, editable, and safe to operate in production. Tasks can be inspected before they are changed, triggered manually when needed, previewed without advancing their triggers, and followed through history and logs after they run.

Documentation: [https://asyncz.dymmond.com](https://asyncz.dymmond.com)

## What Asyncz gives you

- Async runtimes: `AsyncIOScheduler` for regular async applications and `NativeAsyncIOScheduler` for environments that already own the event loop.
- Scheduling primitives: `date`, `interval`, `cron`, `and`, `or`, and `shutdown` triggers.
- Durable stores: `memory`, `file`, `mongodb`, `redis`, and `sqlalchemy`.
- Executor choices: asyncio event loop execution, thread pools, process pools, and direct debug execution.
- Safe task control for operators: stable task ids, manual Run now, pause, resume, remove, inspect, preview, and update workflows.
- Scheduler inspection APIs: process identity, lifecycle timing, task counts, stores, executors, instances visible in the current process, and upcoming run previews.
- Modern dashboard: task filters, row and bulk actions, links to logs for each task, task edit previews, runtime and instance pages, timeline, audit trail, run history, and log inspection for each run.
- Packaged dashboard assets: no runtime dependency on public Tailwind, Alpine.js, HTMX, Toastify, or favicon CDNs.
- Python standard logging throughout the project.

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

## Operator workflows

Add a durable task with a stable id:

```bash
asyncz add myapp.tasks:cleanup \
  --id cleanup-task \
  --name cleanup \
  --interval 5m \
  --store durable=sqlite:///scheduler.db
```

Inspect it before touching it:

```bash
asyncz inspect cleanup-task --count 5 --store durable=sqlite:///scheduler.db
asyncz inspect cleanup-task --json --store durable=sqlite:///scheduler.db
```

Preview a metadata change before writing it:

```bash
asyncz update cleanup-task \
  --name cleanup-v2 \
  --max-instances 2 \
  --dry-run \
  --store durable=sqlite:///scheduler.db
```

Apply it without a prompt when the diff is expected:

```bash
asyncz update cleanup-task \
  --name cleanup-v2 \
  --max-instances 2 \
  --yes \
  --store durable=sqlite:///scheduler.db
```

Trigger it immediately, then inspect its next scheduled run:

```bash
asyncz run cleanup-task --store durable=sqlite:///scheduler.db
asyncz preview cleanup-task --count 5 --store durable=sqlite:///scheduler.db
```

Check the active scheduler and upcoming schedule:

```bash
asyncz status --store durable=sqlite:///scheduler.db
asyncz doctor --strict --store durable=sqlite:///scheduler.db
asyncz timeline --per-task 3 --limit 50 --store durable=sqlite:///scheduler.db
```

## Core concepts

Asyncz is built around four main component types:

- [Schedulers](https://asyncz.dymmond.com/schedulers/)
- [Triggers](https://asyncz.dymmond.com/triggers/)
- [Stores](https://asyncz.dymmond.com/stores/)
- [Executors](https://asyncz.dymmond.com/executors/)

Tasks are the public unit of scheduling. A task combines a callable, a trigger, an executor alias, and the metadata needed to persist and reschedule it correctly.

## Logging

Asyncz uses Python's `logging` module. The default logger namespaces are:

- `asyncz.schedulers`
- `asyncz.executors.<alias>`
- `asyncz.stores.<alias>`

If you need custom logger creation, pass your own `loggers_class` to the scheduler. That class only needs to implement the same dictionary-like contract used by `ClassicLogging`.

The dashboard also ships with a log capture layer for the `asyncz` logger namespace. It can filter by task id, run id, level, and message text. Run history entries include the scheduler identity, coalesced run count, and lifecycle log records, so operators can open a specific run and inspect the logs attached to that run.

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

## Dashboard quick mount

Install the dashboard extra:

```bash
pip install "asyncz[dashboard]"
```

Mount the dashboard into a Lilya application:

```python
from lilya.apps import Lilya

from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()
app = Lilya(
    routes=[...],
    on_startup=[scheduler.start],
    on_shutdown=[scheduler.shutdown],
)

admin = AsynczAdmin(url_prefix="/dashboard", scheduler=scheduler)
admin.include_in(app)
```

The dashboard is an admin surface rendered by the server and enhanced by packaged Alpine.js and HTMX. It can:

- filter, sort, and search tasks
- trigger tasks manually without removing one time tasks from the table
- open logs for a task directly from its row
- preview and apply supported task metadata edits through `scheduler.update_task()`
- pause, resume, remove, and control tasks in bulk
- inspect scheduler runtime, instances visible in the current process, and upcoming timelines
- follow runs through history records and correlated logs
- audit dashboard management actions separately from execution history

## Persistent stores and encryption

The default store is in memory. For durable scheduling, configure a file, MongoDB, Redis, or SQLAlchemy store.

Persistent stores support the `ASYNCZ_STORE_ENCRYPTION_KEY` environment variable. When it is set, task payloads are encrypted before they are written to the backing store.

## Production checklist

- Use stable task ids for scheduled work that operators may inspect, trigger, pause, resume, or update.
- Use a durable store for tasks that must survive process restarts.
- Run `asyncz doctor --strict` in deployment checks when the scheduler is expected to be ready.
- Use `asyncz inspect`, `asyncz preview`, and `asyncz timeline` before manual interventions.
- Use `asyncz update --dry-run` or the dashboard edit preview before changing task metadata.
- Mount the dashboard behind your application authentication or enable the dashboard login backend.
- Configure reverse proxy prefixes explicitly when serving the dashboard behind an external path.
- Keep task logs on Python's `logging` module so the dashboard log viewer can correlate run records and task output.

## CLI and dashboard

Asyncz ships with:

- a CLI for `version`, `doctor`, `instances`, `start`, `add`, `update`, `list`, `inspect`, `preview`, `timeline`, `status`, `run`, `pause`, `resume`, and `remove`
- a Lilya dashboard with a scheduler overview, task controls, edit previews, bulk operations, runtime, instances, timeline, audit trail, run history, and log inspection

See the documentation for usage details:

- [CLI guide](https://asyncz.dymmond.com/cli/)
- [Dashboard guide](https://asyncz.dymmond.com/dashboard/dashboard/)
