# Events

Asyncz emits structured event objects when schedulers, stores, executors, and tasks change state. All event models live in `asyncz.events.base`, and the event code constants live in `asyncz.events.constants`.

## Event models

### `SchedulerEvent`

The base event type. It carries:

- `code`: the event code
- `alias`: the store or executor alias involved in the event, when relevant

### `TaskEvent`

Extends `SchedulerEvent` with task-specific data:

- `task_id`
- `store`
- `scheduler_identity`: set by the scheduler before listeners receive the event

### `TaskSubmissionEvent`

Extends `TaskEvent` with:

- `scheduled_run_times`: the run times the scheduler submitted to an executor
- `coalesced_run_count`: due run times omitted because `coalesce=True`
- `source`: `manual`, `scheduled`, or `unknown`

### `TaskExecutionEvent`

Extends `TaskEvent` with:

- `scheduled_run_time`
- `return_value`
- `exception`
- `traceback`

## Common event codes

Import codes from `asyncz.events.constants` and register listeners with `scheduler.add_listener(...)`.

Typical codes include:

- `SCHEDULER_START`
- `SCHEDULER_SHUTDOWN`
- `TASK_ADDED`
- `TASK_REMOVED`
- `TASK_SUBMITTED`
- `TASK_EXECUTED`
- `TASK_ERROR`
- `TASK_MISSED`

## Adding a listener

```python
{!> ../../../docs_src/schedulers/add_event.py !}
```

## Dashboard event history

When the optional dashboard is mounted, it records scheduler events observed in
that process. The Events page can filter by event category, event name, task id,
search text, and limit.

This is process-local history. It does not replace a distributed event broker.
