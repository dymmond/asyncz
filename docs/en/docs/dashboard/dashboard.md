# Asyncz Dashboard

Asyncz includes an optional Lilya-based dashboard for inspecting tasks and running common management actions from a browser.

## What it provides

- an overview page with scheduler, task-state, and recent-run summaries
- a runtime page with scheduler state, timing, store, and executor metadata
- a task list with search, state/executor/trigger filters, sortable views, and last-run status
- per-task actions for Run now, pause, resume, remove, and history inspection
- bulk task actions for Run now, pause, resume, and remove
- a run-history page backed by scheduler execution events
- per-run detail pages with correlated log records
- an optional login flow
- a log viewer backed by the dashboard logging subsystem, including run-id filtering

## Install

```bash
pip install "asyncz[dashboard]"
```

## Mounting with Lilya

```python
from lilya.apps import Lilya

from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
app = Lilya()

admin = AsynczAdmin(scheduler=scheduler)
admin.include_in(app)
```

Start and stop the scheduler with your application lifecycle:

```python
app = Lilya(
    routes=[...],
    on_startup=[scheduler.start],
    on_shutdown=[scheduler.shutdown],
)
```

## Mounting in other ASGI frameworks

Use `admin.get_asgi_app()` and mount it according to your framework's ASGI mounting API.

```python
from starlette.applications import Starlette
from starlette.routing import Mount

from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
admin = AsynczAdmin(scheduler=scheduler)

app = Starlette(routes=[Mount("/dashboard", app=admin.get_asgi_app())])
```

## Login support

Enable login by passing `enable_login=True` and a backend implementation.

```python
from asyncz.contrib.dashboard.admin import (
    AsynczAdmin,
    SimpleUsernamePasswordBackend,
    User,
)


def verify(username: str, password: str) -> User | None:
    if username == "admin" and password == "secret":
        return User(id="admin", name="Admin")
    return None


admin = AsynczAdmin(
    scheduler=scheduler,
    enable_login=True,
    backend=SimpleUsernamePasswordBackend(verify),
)
```

## Admin surfaces

The dashboard is organized around operational tasks:

| Area | Purpose |
| --- | --- |
| Overview | Scheduler state, task counts, recent tasks, and recent runs. |
| Tasks | Filter tasks, trigger immediate runs, pause, resume, remove, and inspect last-run state. |
| Runtime | Inspect scheduler timing, timezone, state code, stores, executors, and task distribution. |
| History | Inspect manual and scheduled task runs captured from scheduler events. |
| Logs | Filter captured log records by task id, run id, level, and message text. |

The dashboard uses packaged Alpine.js for transient browser state such as
navigation, selection, and modal controls. Scheduler state remains server-owned:
task rows, history records, and logs are rendered from scheduler APIs and the
dashboard storage backends.

## Configuration

Dashboard defaults live in `asyncz.contrib.dashboard.config.DashboardConfig`.

The most commonly customized fields are:

- `dashboard_url_prefix`
- `title`
- `header_title`
- `description`
- `session_cookie`
- `same_site`
- `https_only`

You can return a custom `DashboardConfig` from `settings.dashboard_config`.

## Static assets

The dashboard serves its browser assets from package resources. It does not
load Tailwind CSS, Alpine.js, HTMX, Toastify, or the default favicon from public
CDNs at runtime.

Packaged assets live under `asyncz.contrib.dashboard/statics` and include:

- Tailwind CSS compiled for the bundled Jinja templates
- Alpine.js CSP build
- HTMX
- Toastify JavaScript and CSS
- the dashboard favicon

The asset manifest at `statics/vendor/manifest.json` records upstream package
versions, npm integrity values, SHA-256 checksums, and license files. When
updating these assets, regenerate the compiled Tailwind file from
`statics/css/asyncz-tailwind.input.css`, update the manifest, and run the
dashboard static-asset tests plus a wheel/sdist build.

## Task list behavior

The task dashboard now reads from the scheduler's immutable task inspection snapshots rather than serializing live tasks ad hoc inside each controller.

That means the UI can consistently show:

- task id and display name
- callable name/reference
- trigger alias and human-readable trigger description
- next run time
- store and executor aliases
- derived task state (`pending`, `paused`, or `scheduled`)

The task table supports:

- free-text search
- state filtering
- executor filtering
- trigger filtering
- sorting by name, trigger, state, or next run time

Active filters are preserved across:

- HTMX auto-refreshes
- row actions
- bulk actions

## Dashboard "run now" semantics

When you use the dashboard's **Run** action, the dashboard calls `scheduler.run_task(..., remove_finished=False)`.

This is intentional:

- recurring tasks advance to their next scheduled run
- one-off/date tasks remain visible in the dashboard as **paused** instead of disappearing immediately

That behavior is useful for operators because a manually triggered one-off task can still be inspected, resumed, or removed explicitly after the forced run.

Manual dashboard runs are recorded in run history with `source="manual"`.
Scheduled executions are recorded with `source="scheduled"` when they are
submitted through normal scheduler processing.

## Run history

When the dashboard is mounted, it installs a scheduler listener for task
submission and execution events. The default run-history backend is
process-local memory storage.

Each run record captures:

- run id
- task id and task name
- callable reference
- store and executor alias
- source (`manual`, `scheduled`, or `unknown`)
- status (`running`, `succeeded`, `failed`, `missed`, or `max_instances`)
- submitted and finished timestamps
- duration
- return value or exception details when available

Run history handles synchronous debug executors as well as asynchronous
executors. If a debug executor emits the execution event before the submission
event, the record is still merged into one run and the later submission event
fills in the source.

## Per-run logs

Run-history lifecycle events write structured log records with a `run_id`.
The run detail page shows:

- direct lifecycle logs for that run id
- task-scoped logs emitted during the run window

For application task logs, prefer task-scoped standard-library logging:

```python
from asyncz.contrib.dashboard.logs.handler import get_task_logger

logger = get_task_logger("cleanup-task")
logger.info("cleanup started")
```

Or pass task metadata directly:

```python
import logging

logging.getLogger("asyncz.jobs").info(
    "cleanup started",
    extra={"task_id": "cleanup-task"},
)
```

## Overview page

The overview page summarizes:

- scheduler running/stopped state
- configured timezone
- total task count
- scheduled / paused / pending counts
- recent tasks with their callable and trigger metadata
- recent runs with status, source, duration, and log-inspection links

## Runtime page

The runtime page shows the active scheduler's read-only operational metadata:

- running/stopped state and scheduler state code
- task inventory totals, including submitted tasks
- configured timezone, store retry interval, and startup delay
- registered stores with alias, implementation class, logger namespace, and task count
- registered executors with alias, implementation class, logger namespace, and task count

Use this page when you need to confirm which persistence and execution backends
the running process is actually using.

## Custom log storage

Pass `log_storage=` to `AsynczAdmin` if you want the dashboard log viewer to use something other than the default in-memory storage.

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage

admin = AsynczAdmin(
    scheduler=scheduler,
    log_storage=MemoryLogStorage(maxlen=20_000),
)
```

## Custom run-history storage

Pass `run_history_storage=` to `AsynczAdmin` to control the in-process run
history backend. The built-in storage is `MemoryRunHistoryStorage`.

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.history import MemoryRunHistoryStorage

admin = AsynczAdmin(
    scheduler=scheduler,
    run_history_storage=MemoryRunHistoryStorage(maxlen=10_000),
)
```

The built-in backend is intentionally process-local. Use a custom backend if
you need run history to survive process restarts or be shared across multiple
worker processes.
