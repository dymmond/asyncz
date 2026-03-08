---
hide:
  - navigation
---

# Asyncz CLI

Asyncz ships with a CLI for managing schedulers and persisted tasks without writing application-specific management commands.

## Install

```bash
pip install asyncz
```

The `asyncz` command is exposed through `project.scripts`.

## Operating modes

### Standalone mode

The CLI builds a temporary scheduler from the options you pass.

### Bootstrap mode

The CLI imports an application-owned scheduler through `--bootstrap` and operates on that scheduler instance.

## Store specifications

`--store` values use `alias=value` form.

Examples:

- `default=memory`
- `durable=file:///tmp/asyncz-store`
- `durable=sqlite:///scheduler.db`
- `cache=redis://localhost:6379/0`
- `durable=mongodb://localhost:27017/asyncz`

## Executor specifications

`--executor` values use `alias=type[:workers]`.

Examples:

- `default=asyncio`
- `io=thread:8`
- `cpu=process:4`
- `debug=debug`

## Trigger arguments

`add` accepts exactly one of:

- `--cron`
- `--interval`
- `--at`

Notes:

- `--interval` supports `s`, `m`, and `h` units, such as `10s`, `5m`, or `2h`
- `--at` expects an ISO 8601 datetime

## Common commands

### Start a scheduler

```bash
asyncz start --store durable=sqlite:///scheduler.db --executor default=asyncio
```

### Add a recurring task

```bash
asyncz add myapp.tasks:cleanup \
  --name nightly-cleanup \
  --cron "0 2 * * *" \
  --store durable=sqlite:///scheduler.db
```

### Add a one-off task

```bash
asyncz add myapp.tasks:report \
  --name generate-report \
  --at "2027-01-01T10:00:00+00:00" \
  --store durable=sqlite:///scheduler.db
```

### List tasks

```bash
asyncz list --store durable=sqlite:///scheduler.db
asyncz list --json --store durable=sqlite:///scheduler.db
asyncz list --state paused --trigger interval --sort-by name
```

The `list` command now uses the scheduler's task inspection API, so it can filter and sort without reimplementing task serialization itself.

Useful filters:

- `--state pending|paused|scheduled`
- `--executor <alias>`
- `--trigger <alias-or-class-name>`
- `--query <text>`
- `--sort-by id|name|next_run_time|schedule_state|executor|store|trigger`
- `--desc`

JSON output includes the original compatibility fields (`id`, `name`, `trigger`, `next_run_time`) plus richer inspection fields such as:

- `trigger_alias`
- `trigger_description`
- `state`
- `store`
- `executor`
- `callable_name`
- `callable_reference`

### Run, pause, resume, and remove

```bash
asyncz run <task_id> --store durable=sqlite:///scheduler.db
asyncz pause <task_id> --store durable=sqlite:///scheduler.db
asyncz resume <task_id> --store durable=sqlite:///scheduler.db
asyncz remove <task_id> --store durable=sqlite:///scheduler.db
```

These commands now delegate to the scheduler's own task-control APIs (`run_task()`, `pause_task()`, `resume_task()`, and `delete_task()`), which keeps CLI behavior aligned with the dashboard and programmatic callers.

## Bootstrap contract

`--bootstrap` must resolve to one of:

- a class with `get_scheduler()`
- an object with `get_scheduler()`
- a callable that returns an `AsyncIOScheduler`

Example:

```python
from asyncz.schedulers import AsyncIOScheduler


class AsynczSpec:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

    def get_scheduler(self) -> AsyncIOScheduler:
        return self.scheduler
```

Then run:

```bash
asyncz start --bootstrap "myproject.bootstrap:AsynczSpec"
```
