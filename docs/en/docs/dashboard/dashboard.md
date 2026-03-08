---
hide:
  - navigation
---

# Asyncz Dashboard

Asyncz includes an optional Lilya-based dashboard for inspecting tasks and running common management actions from a browser.

## What it provides

- a task list with search and filtering
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
