# Asyncz Dashboard

Asyncz includes an optional Lilya-based dashboard for inspecting tasks and running common management actions from a browser.

## What it provides

- an overview page with scheduler and task-state summaries
- a task list with search, state/executor/trigger filters, and sortable views
- per-task actions for run, pause, resume, and remove
- bulk task actions
- an optional login flow
- a log viewer backed by the dashboard logging subsystem

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

## Overview page

The overview page summarizes:

- scheduler running/stopped state
- configured timezone
- total task count
- scheduled / paused / pending counts
- recent tasks with their callable and trigger metadata

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
