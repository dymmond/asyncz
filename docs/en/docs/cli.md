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

### Show the installed version

```bash
asyncz version
asyncz version --json
```

Use `--json` for release checks, packaging smoke tests, and automation that
needs to compare the installed package version without parsing human-oriented
output.

### Start a scheduler

```bash
asyncz start --store durable=sqlite:///scheduler.db --executor default=asyncio
```

### Add a recurring task

```bash
asyncz add myapp.tasks:cleanup \
  --id nightly-cleanup \
  --name nightly-cleanup \
  --cron "0 2 * * *" \
  --store durable=sqlite:///scheduler.db
```

Use `--id` when operators need a stable identifier for run, pause, resume,
remove, inspect, dashboards, or external automation. If omitted, Asyncz
generates the task id.

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

### Inspect one task

```bash
asyncz inspect <task-id> --store durable=sqlite:///scheduler.db
asyncz inspect <task-id> --json --count 10 --store durable=sqlite:///scheduler.db
```

`inspect` is the single-task operator view. It returns the task snapshot and
upcoming run times in one command, so you can check the current state before
running, pausing, resuming, or removing a task.

JSON output includes:

- `task`
- `requested_count`
- `returned_count`
- `exhausted`
- `run_times`

The nested `task` object includes:

- `id`
- `name`
- `state`
- `trigger`
- `trigger_alias`
- `trigger_description`
- `next_run_time`
- `store`
- `executor`
- `callable_name`
- `callable_reference`
- `pending`
- `paused`

### Inspect scheduler status

```bash
asyncz status --store durable=sqlite:///scheduler.db
asyncz status --json --store durable=sqlite:///scheduler.db
```

The `status` command uses the scheduler inspection API for process identity,
lifecycle state, start time, uptime, timezone, configured stores and executors,
and task counts.

JSON output includes:

- `state`
- `state_code`
- `running`
- `identity`
- `started_at`
- `uptime_seconds`
- `timezone`
- `stores`
- `executors`
- `task_count`
- `scheduled_task_count`
- `paused_task_count`
- `pending_task_count`
- `submitted_task_count`
- `store_retry_interval`
- `startup_delay`

### List scheduler instances

```bash
asyncz instances --store durable=sqlite:///scheduler.db
asyncz instances --json --store durable=sqlite:///scheduler.db
```

The `instances` command lists scheduler instances visible through the current
runtime inspection contract. In `0.16.0`, this is process-local visibility: the
command reports the scheduler object it can reach and does not fabricate
distributed membership from task stores.

JSON output includes:

- `scope`
- `count`
- `instances`

Each instance object includes:

- `identity`
- `scope`
- `state`
- `state_code`
- `active`
- `stale`
- `started_at`
- `last_seen_at`
- `uptime_seconds`
- `heartbeat_age_seconds`
- `stale_after_seconds`
- `timezone`
- `stores`
- `executors`
- `task_count`
- `scheduled_task_count`
- `paused_task_count`
- `pending_task_count`
- `submitted_task_count`

### Run scheduler diagnostics

```bash
asyncz doctor --store durable=sqlite:///scheduler.db
asyncz doctor --json --store durable=sqlite:///scheduler.db
asyncz doctor --strict --bootstrap myapp.schedulers:AsynczSpec
```

The `doctor` command runs readiness checks on top of the scheduler inspection
API. Without `--bootstrap`, it starts a temporary scheduler with the configured
stores, verifies that the scheduler is running, confirms stores and executors are
registered, inspects task inventory, and validates lifecycle timing metadata.
With `--bootstrap`, it reports the scheduler returned by your application
without starting it.

JSON output includes:

- `health`
- `ready`
- `scheduler`
- `checks`

Use `--strict` when automation should fail if any diagnostic check reports
`warning` or `failed` health.

### Preview upcoming run times

```bash
asyncz preview <task-id> --count 5 --store durable=sqlite:///scheduler.db
asyncz preview <task-id> --json --count 5 --store durable=sqlite:///scheduler.db
```

The `preview` command asks the scheduler to calculate upcoming run times with
the task's real trigger. It does not update the task or advance its stored
`next_run_time`.

JSON output includes:

- `task`
- `timezone`
- `generated_at`
- `requested_count`
- `returned_count`
- `exhausted`
- `run_times`

### Preview the scheduler timeline

```bash
asyncz timeline --store durable=sqlite:///scheduler.db
asyncz timeline --json --per-task 3 --limit 100 --store durable=sqlite:///scheduler.db
```

The `timeline` command previews upcoming run times across every task and sorts
the rows by due time. It calls the same scheduler-owned trigger preview API as
`inspect` and `preview`, so it does not advance triggers or update stored
`next_run_time` values.

JSON output includes:

- `timezone`
- `generated_at`
- `requested_per_task`
- `limit`
- `task_count`
- `total_count`
- `returned_count`
- `exhausted_task_count`
- `rows`

### Run, pause, resume, and remove

```bash
asyncz run <task_id> --store durable=sqlite:///scheduler.db
asyncz pause <task_id> --store durable=sqlite:///scheduler.db
asyncz resume <task_id> --store durable=sqlite:///scheduler.db
asyncz remove <task_id> --store durable=sqlite:///scheduler.db
```

These commands now delegate to the scheduler's own task-control APIs (`run_task()`, `pause_task()`, `resume_task()`, and `delete_task()`), which keeps CLI behavior aligned with the dashboard and programmatic callers.

For a typical manual intervention:

```bash
asyncz inspect cleanup-task --store durable=sqlite:///scheduler.db
asyncz run cleanup-task --store durable=sqlite:///scheduler.db
asyncz inspect cleanup-task --store durable=sqlite:///scheduler.db
```

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
