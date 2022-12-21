# Events

The events are special objects that are triggered on specific occasions and may carry some
additional information with them regarding detauls of that specific event.

Asyncz events are pydantic objects that carry the information across the system and because
they are pydantic objects that also means it can be leveraged by specific validations.

## SchedulerEvent

The base event of all Asyncz events. If you want to create your own custom event, it is **advised**
to subclass it and all the events are inherited from this class which means they inherit also
the superclass parameters.

### Parameters

* **code** - The code type of the event.
* **alias** - The alias given to a [store](./stores.md) or [executor](./executors.md)

## TaskEvent

The events related to a specific [task](./tasks.md).

### Parameters

* **task_id** - The identifier given to a task.
* **store** - The alias given to a store.

## TaskSubmissionEvent

Event related to the submission of a task.

### Parameters

* **scheduled_run_times** - List of datetimes when the task is supposed to run.

## TaskExecutionEvent

Event relared to the running of a task within the executor.

### Parameters

* **scheduled_run_times** - The time when the task was scheduled to be run.
* **return_value** - The return value of the task successfully executed.
* **exception** - The exception raised by the task.
* **traceback** - A formated traceback for the exception.