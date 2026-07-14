# Asyncz Dashboard

Asyncz includes an optional Lilya dashboard for inspecting tasks and running common management actions from a browser.

## What it provides

- an overview page with scheduler, task state, and recent run summaries
- a runtime page with scheduler state, timing, store, and executor metadata
- an instances page with scheduler identity and heartbeat freshness for the current process
- a timeline page that previews upcoming run times across all tasks
- an audit page for dashboard create/update/run/pause/resume/remove actions
- grouped navigation for operation and review pages
- a task list with search, state/executor/trigger filters, sortable views, and last run status
- actions on each task row for Run now, Logs, Edit, pause, resume, remove, and history inspection
- bulk task actions for Run now, pause, resume, and remove
- a run history page backed by scheduler execution events
- run detail pages with correlated log records
- an optional login flow
- a log viewer backed by the dashboard logging subsystem, including run id filtering

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
| Tasks | Filter tasks, trigger immediate runs, open logs for a task, edit supported metadata, pause, resume, remove, and inspect last run state. |
| Runtime | Inspect scheduler timing, timezone, state code, stores, executors, and task distribution. |
| Instances | Inspect scheduler identity, active/stale status, and heartbeat freshness for the current process. |
| Timeline | Preview upcoming run times across tasks without mutating scheduler state. |
| History | Inspect manual and scheduled task runs captured from scheduler events. |
| Audit | Inspect dashboard management actions separately from execution history. |
| Logs | Filter captured log records by task id, run id, level, and message text. |

The dashboard uses packaged Alpine.js for transient browser state such as
navigation, table density, filter visibility, selection, and modal controls.
The scheduler remains the source of truth: task rows, history records, and logs
are rendered from scheduler APIs and the dashboard storage backends.

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

## Reverse proxies

When the dashboard is served behind a proxy prefix, enable the forwarded prefix
middleware and configure the proxy to strip the external prefix before forwarding
requests to the ASGI app.

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin

admin = AsynczAdmin(
    scheduler=scheduler,
    url_prefix="/dashboard",
    enable_forward_middleware=True,
)
```

Example Nginx location:

```nginx
location /ops/dashboard/ {
    proxy_set_header X-Forwarded-Prefix /ops;
    proxy_set_header Host $host;
    proxy_pass http://127.0.0.1:8000/dashboard/;
}
```

With that shape, the upstream app receives `/dashboard/...` requests while
rendered links, static assets, and HTMX endpoints point at `/ops/dashboard/...`.

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
dashboard static asset tests plus a wheel/sdist build.

## Security headers

Dashboard responses include browser hardening headers by default:

- `Content-Security-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`
- `Permissions-Policy`

The default CSP allows scripts only from the dashboard origin. Styles allow
`'unsafe-inline'` because current templates and third-party browser libraries
still require inline style support, but inline script handlers are not used.

## Task list behavior

The task dashboard now reads from the scheduler's immutable task inspection snapshots rather than serializing live tasks ad hoc inside each controller.

That means the UI can consistently show:

- task id and display name
- callable name/reference
- trigger alias and readable trigger description
- next run time
- store and executor aliases
- derived task state (`pending`, `paused`, or `scheduled`)

The task table supports:

- text search
- state filtering
- executor filtering
- trigger filtering
- sorting by name, trigger, state, or next run time
- edit links for supported task fields
- log links that open the log viewer filtered to the selected task id
- comfortable and compact density modes
- a resizable table region with sticky row actions on wide viewports

Active filters are preserved across:

- automatic HTMX refreshes
- row actions
- bulk actions

## Task edits

The task edit page delegates validation and persistence to
`scheduler.update_task(...)`. It supports the same operational metadata exposed
by the `asyncz update` command:

- task name
- callable reference
- positional arguments as JSON
- keyword arguments as JSON
- executor alias
- coalesce behavior
- maximum concurrent instances
- misfire grace time, including clearing the value

Posting the edit form with `intent=preview` validates the proposed update and
renders a diff without mutating the task. Posting with
`intent=apply` applies the update through the scheduler and records a
`task.update` audit event with the changed fields.

## Dashboard "run now" semantics

When you use the dashboard's **Run** action, the dashboard calls `scheduler.run_task(..., remove_finished=False)`.

This is intentional:

- recurring tasks advance to their next scheduled run
- date tasks remain visible in the dashboard as **paused** instead of disappearing immediately

That behavior is useful for operators because a manually triggered date task can still be inspected, resumed, or removed explicitly after the forced run.

Manual dashboard runs are recorded in run history with `source="manual"`.
Scheduled executions are recorded with `source="scheduled"` when they are
submitted through normal scheduler processing.

## Run history

When the dashboard is mounted, it installs a scheduler listener for task
submission and execution events. The default run history backend is memory
storage in the current process.

Each run record captures:

- run id
- task id and task name
- callable reference
- store and executor alias
- scheduler identity from the task event that recorded the run
- number of due runs omitted by coalescing
- source (`manual`, `scheduled`, or `unknown`)
- status (`running`, `succeeded`, `failed`, `missed`, or `max_instances`)
- submitted and finished timestamps
- duration
- return value or exception details when available

Run history handles synchronous debug executors as well as asynchronous
executors. If a debug executor emits the execution event before the submission
event, the record is still merged into one run and the later submission event
fills in the source.

## Run Logs

Run history lifecycle events write structured log records with a `run_id`.
Lifecycle log records also include the scheduler identity stored on the run
record, so a run detail page can show both the logs and the scheduler process
that recorded them.
The run detail page shows:

- direct lifecycle logs for that run id
- task logs emitted during the run window

For application task logs, prefer Python logging with a task id:

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
- recent runs with status, source, duration, and log inspection links

## Runtime page

The runtime page shows the active scheduler's read-only operational metadata:

- running/stopped state and scheduler state code
- scheduler identity, start time, and uptime for the active process
- task inventory totals, including tasks accepted into the scheduler lifecycle
- configured timezone, store retry interval, and startup delay
- registered stores with alias, implementation class, logger namespace, and task count
- registered executors with alias, implementation class, logger namespace, and task count

Use this page when you need to confirm which persistence and execution backends
the running process is actually using.

## Instances page

The instances page renders `scheduler.get_scheduler_instance_infos()` and shows:

- scheduler identity and current process scope
- active/stale state
- last seen timestamp and heartbeat age
- start time and uptime
- configured store and executor aliases
- task inventory totals

In `0.16.0`, this page reports the scheduler instance reachable through the
current runtime object. It does not invent distributed scheduler membership from
task stores.

## Timeline page

The timeline page previews upcoming run times across all tasks by calling the
scheduler's `preview_task_runs()` API for each task. It does not advance
triggers, update `next_run_time`, or submit work to executors.

Use the controls to choose how many run times to preview per task and the total
number of rows to show. The result is sorted by due time so operators can quickly
see what is expected to run next.

## Audit page

The audit page records dashboard management actions separately from run history.
It captures task create, update, run, pause, resume, and remove attempts with:

- action name
- target task id
- status (`succeeded`, `warning`, or `failed`)
- timestamp
- message for the operator

The default audit backend is memory storage in the current process. Pass
`audit_storage=` to `AsynczAdmin` when you want to share or replace that storage
inside a larger application.

## Custom log storage

Pass `log_storage=` to `AsynczAdmin` if you want the dashboard log viewer to use something other than the default memory storage.

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage

admin = AsynczAdmin(
    scheduler=scheduler,
    log_storage=MemoryLogStorage(maxlen=20_000),
)
```

## Custom Run History Storage

Pass `run_history_storage=` to `AsynczAdmin` to control the run
history backend. The built-in storage is `MemoryRunHistoryStorage`.

```python
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.history import MemoryRunHistoryStorage

admin = AsynczAdmin(
    scheduler=scheduler,
    run_history_storage=MemoryRunHistoryStorage(maxlen=10_000),
)
```

The built-in backend belongs to the current process. Use a custom backend if
you need run history to survive process restarts or be shared across multiple
worker processes.
