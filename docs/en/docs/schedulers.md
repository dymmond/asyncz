# Schedulers

Schedulers coordinate every other Asyncz component. They own the configured stores and executors, calculate due run times, submit work, dispatch events, and expose the public task-management API.

## Available schedulers

### `AsyncIOScheduler`

The default scheduler for most applications. It can reuse an existing event loop or create an isolated loop when needed.

```python
from asyncz.schedulers import AsyncIOScheduler
```

### `NativeAsyncIOScheduler`

Use this variant when the surrounding application already owns the running event loop and you want `start()` / `shutdown()` to be awaitable.

```python
from asyncz.schedulers import NativeAsyncIOScheduler
```

## Defaults

When you instantiate a scheduler with no explicit configuration, Asyncz will lazily add:

- the `memory` store as `default`
- the `asyncio` executor as `default`

## Configuring a scheduler

Asyncz accepts direct Python objects, plugin aliases, or configuration dictionaries.

### Python-first configuration

```python
{!> ../../../docs_src/schedulers/method1.py !}
```

### Configuration dictionary at construction time

```python
{!> ../../../docs_src/schedulers/method2.py !}
```

### Reconfiguring with `setup()`

```python
{!> ../../../docs_src/schedulers/method3.py !}
```

## Logging

Asyncz uses the standard `logging` module.

The default scheduler logger namespace is:

```text
asyncz.schedulers
```

If you pass `logger_name="worker-a"`, the scheduler logger becomes:

```text
asyncz.schedulers.worker-a
```

Stores and executors follow the same convention:

- `asyncz.stores.<alias>`
- `asyncz.executors.<alias>`

If you need custom logger creation, provide a custom `loggers_class`. The built-in implementation is `asyncz.schedulers.base.ClassicLogging`.

## Starting and stopping

```python
{!> ../../../docs_src/schedulers/start.py !}
```

```python
{!> ../../../docs_src/schedulers/shutdown.py !}
```

## Adding tasks

`scheduler.add_task(...)` is the main entry point for registering work.

- Pass a trigger instance directly.
- Or pass a trigger alias plus trigger-specific keyword arguments.
- The return value is an `asyncz.tasks.Task`.

```python
{!> ../../../docs_src/schedulers/add_task.py !}
```

### Decorator mode

If you omit the callable, `add_task()` returns a decorator-style task definition.

```python
{!> ../../../docs_src/schedulers/add_task_decorator.py !}
```

## Task management operations

Asyncz also supports:

- `pause()` / `resume()` for the whole scheduler
- `run_task()` for administrative "run now" flows
- `pause_task()` / `resume_task()`
- `update_task()`
- `reschedule_task()`
- `delete_task()` / `remove_all_tasks()`

Examples:

```python
{!> ../../../docs_src/schedulers/pause.py !}
```

```python
{!> ../../../docs_src/schedulers/resume.py !}
```

```python
{!> ../../../docs_src/schedulers/update_task.py !}
```

```python
{!> ../../../docs_src/schedulers/reschedule_task.py !}
```

## Running a task immediately

Use `scheduler.run_task(...)` when you need an explicit operator-driven execution outside the normal trigger cadence.

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()

task = scheduler.add_task(my_cleanup, "interval", minutes=30, id="cleanup")
scheduler.start(paused=True)

# Force an immediate execution, then keep the task paused if the trigger has no
# future run time left (useful for one-off/date tasks surfaced in admin tools).
scheduler.run_task("cleanup", remove_finished=False)
```

Important behavior:

- `run_task()` uses the task's configured executor
- it dispatches `TASK_SUBMITTED` (or `TASK_MAX_INSTANCES`) just like the main scheduler loop
- it recomputes and persists the next run time after submission
- if the trigger is exhausted, `remove_finished=True` removes the task while `False` keeps it paused

## Task inspection and querying

Schedulers expose immutable inspection snapshots through `get_task_info()` and `get_task_infos()`.

```python
info = scheduler.get_task_info("cleanup")
assert info is not None
print(info.schedule_state.value, info.trigger_alias, info.next_run_time)

scheduled = scheduler.get_task_infos(
    schedule_state="scheduled",
    trigger="interval",
    q="cleanup",
    sort_by="next_run_time",
)
```

`get_task_infos()` is intended for operational surfaces such as:

- admin dashboards
- CLI list commands
- health checks and diagnostics
- custom support tooling

Supported filters:

- `schedule_state`: `pending`, `paused`, or `scheduled`
- `executor`
- `trigger`
- `q`: case-insensitive free-text search across identifiers, names, callable metadata, trigger metadata, executor, store, and state

Supported sort keys:

- `id`
- `name`
- `next_run_time`
- `schedule_state`
- `executor`
- `store`
- `trigger`

## Multi-process locking

Schedulers support file-based inter-process coordination through `lock_path`.

Example:

```python
{!> ../../../docs_src/schedulers/method_mp.py !}
```

Available placeholders:

- `{store}`: the store alias
- `{ppid}`: the parent process id
- `{pgrp}`: the process group id

When `lock_path` is set, Asyncz also defaults `startup_delay` to `1` second so multiple workers do not immediately stampede the same persisted tasks on startup.

## ASGI integration and context managers

Schedulers can be used as:

- ASGI wrappers via `scheduler.asgi(...)`
- synchronous context managers
- asynchronous context managers

See [ASGI and Context Managers](./asgi.md) for the full lifecycle patterns.
