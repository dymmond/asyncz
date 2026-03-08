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

### `TaskSubmissionEvent`

Extends `TaskEvent` with:

- `scheduled_run_times`: the run times the scheduler submitted to an executor

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
