# Tasks

Tasks are the public scheduling unit in Asyncz. A task combines the callable, trigger, executor alias, arguments, and persistence metadata required to schedule and reschedule work.

```python
from asyncz.tasks import Task
```

## Core task fields

- `id`
- `name`
- `fn`
- `args`
- `kwargs`
- `trigger`
- `executor`
- `mistrigger_grace_time`
- `coalesce`
- `max_instances`
- `next_run_time`

## Task state and inspection

Every task exposes a derived scheduling state:

- `pending`: the task is still in the scheduler's pending queue and has not been committed to a started store yet
- `paused`: the task exists but has no `next_run_time`
- `scheduled`: the task has an upcoming `next_run_time`

Useful task inspection helpers:

- `task.schedule_state`
- `task.paused`
- `task.snapshot()`

Example:

```python
task = scheduler.add_task(cleanup, "interval", minutes=5, id="cleanup")
info = task.snapshot()

print(info.callable_reference)
print(info.trigger_alias)
print(info.schedule_state.value)
```

`snapshot()` returns an immutable `TaskInfo` model that is safe to pass into:

- dashboards
- CLI formatting code
- structured logging
- tests and assertions

## Creating a task directly

```python
{!> ../../../docs_src/tasks/create_task.py !}
```

In most applications you will create tasks through `scheduler.add_task(...)`, which returns a `Task` instance after applying scheduler defaults.

## Updating a task

```python
{!> ../../../docs_src/tasks/update_task.py !}
```

Important constraints:

- task ids are immutable
- changing `next_run_time` requires a scheduler so Asyncz can normalize the datetime
- task callables must remain serializable if you want to persist them in a store

## Rescheduling a task

```python
{!> ../../../docs_src/tasks/reschedule_task.py !}
```

`reschedule_task()` changes the trigger and recomputes the next run time.

## Decorator mode

When you call `scheduler.add_task(...)` without a callable, Asyncz returns a decorator-mode task. When the decorated function is applied, Asyncz creates a submitted copy of that task definition.

This is useful when you want task metadata to live next to the function definition but still be managed by the scheduler.

## Lifecycle tasks

Asyncz supports lifecycle-style tasks implemented as generators or async generators.

```python
{!> ../../../docs_src/tasks/lifecycle.py !}
```

Notes:

- lifecycle generators only work with `MemoryStore`
- generator-based tasks are not pickleable, so they cannot be persisted to Redis, MongoDB, SQLAlchemy, or FileStore

## Lifecycle tasks in multi-process deployments

Asyncz can combine lifecycle tasks with file-based locks to coordinate setup, tick, and cleanup behavior across multiple worker processes.

Examples:

```python
{!> ../../../docs_src/tasks/lifecycle_mp_tick_only_one.py !}
```

```python
{!> ../../../docs_src/tasks/lifecycle_mp_only_one_instance.py !}
```
