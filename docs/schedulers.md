# Schedulers

Schedulers are the *thing* that makes all magic and binds everything together. You can see it as a
glue.

Usually the developer does not deal/handle the [stores](./stores.md), [executors](./executors.md)
or even [triggers](./triggers.md) manually, instead that is managed by the scheduler that acts
as an interface amongst them all.

Asyncz being dedicated to ASGI and asyncio brings the [AsyncIOScheduler](#asyncioscheduler)
out of the box and only supports this one natively but like everything in Asyncz, you can also
create your own [custom scheduler](#custom-scheduler) that does not necessarily need to be for
async. You can build your own scheduler for blocking/background applications.

In fact, Asyncz is used by [Esmerald](https://esmerald.dymmond.com) as internal scheduling system
and uses the [supported scheduler](./contrib/esmerald/scheduler.md) from Asyncz to perform its
tasks.

## Parameters

All schedulers contain at least:

* **global_config** - A python dictionary containing configurations for the schedulers. See the
examples of how to [configure a scheduler](#configuring-the-scheduler).

    <sup>Default: `None`</sup>

* **kwargs** - Any keyword parameters being passed to the scheduler up instantiation.

    <sup>Default: `None`</sup>

## Configuring the scheduler

Due its simplificy, Asyncz provides some ways of configuring the scheduler for you.

=== "In a nutshell"

    ```python
    from asyncz.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    ```

=== "From the schedulers"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    ```

**What is happening here?**:

When you create the scheduler like the examples above, it is creating an [AsyncIOScheduler](#asyncioscheduler)
with a [MemoryStore](./stores.md#memorystore) named `default` and starting the
<a href='https://docs.python.org/3/library/asyncio-eventloop.html' target='_blank'>asyncio event loop</a>.

### Example configuration

Let us assume you now need a very custom configuration with more than one store, executors and
custom settings.

* Two stores - A [mongo](./stores.md#mongo) and a [redis](./stores.md#redis).
* Two executors - An [asyncio](./executors.md#asyncioexecutor) and
a [thread pool](./executors.md#threadpoolexecutor).
* Coalesce turned off for new tasks by default.
* Maximum instance limiting to 4 for new tasks.

#### First option

The first way of doing the configuration is in a simple pythonic fashion.

```python
{!> ../docs_src/schedulers/method1.py !}
```

#### Second option

The second option is by starting the scheduler and injecting a dictionary directly upon
instantiation.

```python
{!> ../docs_src/schedulers/method2.py !}
```

#### Third option

The third option is by starting the scheduler and use the `configure` method.

```python
{!> ../docs_src/schedulers/method3.py !}
```

## Starting and stopping the scheduler

Every scheduler inherits from the [BaseScheduler](#basescheduler) and therefore implement the
mandatory functions such as `start` and `shutdown`.

To start the scheduler simply run:

```python
{!> ../docs_src/schedulers/start.py !}
```

To stop the scheduler simply run:

```python
{!> ../docs_src/schedulers/shutdown.py !}
```

## Adding tasks

A scheduler to work needs tasks, of course and Asyncz offers some ways of adding tasks into the
scheduler.

* [add_tasks](#add-tasks)
* [scheduled_tasks](#scheduled-tasks)

There is also a third option but that is related with the integration with ASGI frameworks, for
instance [esmerald](./contrib/esmerald/decorator.md) which it should not be used in this agnostic
context.

### Add tasks

Adding a task via `add_task` is the most common and probably the one you will be using more times
than the `scheduled_task`.

**The `add_task` returns an instance of [Task](./tasks.md).**

So, how can you add a task?

```python hl_lines="26-29 32-38 41-47"
{!> ../docs_src/schedulers/add_task.py !}
```

What happen here is actually very simple. We created an instance of the `AsyncIOScheduler` and
added the functions `send_email_newsletter`, `collect_www_info`, `check_status` to the scheduler
and started it.

Why then passing `CronTrigger` and `IntervalTrigger` instances instead of simply passing `cron`
or `interval`?

Well, we want to pass some attributes to the object and this way makes it cleaner
and simpler.

When adding tasks there is not a specific order. **You can add tasks at any given time**. If the
scheduler is not yet running, once it does it will add the tasks to it.

## Scheduled tasks

Scheduled tasks works in the same way as [add_tasks](#add-tasks) with the **unique difference** that
the `replacing_existing` is always `True` and it is used as a decorator.

```python hl_lines="10-12 19-23 29-33"
{!> ../docs_src/schedulers/scheduled_task.py !}
```

## Deleting tasks

In the same way you can [add tasks](#add-tasks) you can also remove them with the same ease and there
are also different ways of removing them.

* [delete_task](#delete-task)
* [delete](#delete)

### Delete task

This is probably the most common way of removing tasks from the scheduler using the task id and the
store alias.

```python hl_lines="27 34 40 41"
{!> ../docs_src/schedulers/delete_task.py !}
```

## Delete

The `delete` function is probably more convenient but it requires that you store the [Task](./tasks)
somewhere ocne the instance is received and for tasks scheduled by [scheduled task](#scheduled-tasks)
this method does not work, instead only the [delete task](#delete-task) will work.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/delete.py !}
```

## Pause and resume task

As shown above, you can add and remove tasks but you can pause and resume tasks as well. When a task
is paused, there is no next time to run since the action is no longer being validate. That can be
again reactivated by resuming that same [Task](./tasks).

Like the previous examples, there are also multiple ways of achieving that.

* [pause_task](#pause-task)
* [pause](#pause)
* [resume_task](#resume-task)
* [resume](#resume)

### Pause task

Like [delete_task](#delete-task), you can pause a task using the id.

```python hl_lines="22 29 35-36"
{!> ../docs_src/schedulers/pause_task.py !}
```

### Pause

The same is applied to the simple pause where you can do it directly via task instance.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/pause.py !}
```

### Resume task

Resuming a task is as simple as again, passing a task id.

```python hl_lines="22 29 35-36"
{!> ../docs_src/schedulers/resume_task.py !}
```

### Resume

Same for the resume. You can resume a task directly from the instance.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/resume.py !}
```

!!! Check
    [add_task](#add-tasks), [delete_task](#delete-task), [pause_task](#pause-task) and
    [resume_task](#resume-task) expect a **mandatory task_id** parameter as well an optional
    [store](./stores.md) name. Why the store name? Because you might want to store the tasks
    in different places and this points it out the right place.

## Update task

As mentioned in the [tasks](./tasks.md#update-a-task) section, internally the scheduler updates the
information given to the task and then executes it.

You can update any [attribute of the task](./tasks.md#parameters) by calling:

* [**asyncz.tasks.Task.update()**](./tasks.md#update-a-task) - The update method from a task instance.
* **update_task** - The function from the scheduler.

### From a task instance

```python hl_lines="26-30"
{!> ../docs_src/tasks/update_task.py !}
```

### From the scheduler

```python hl_lines="38-39"
{!> ../docs_src/schedulers/update_task.py !}
```

### Important note

All attributes can be updated **but the id** as this is immutable.

## Reschedule tasks

You can also reschedule a task if you want/need but by change what it means is changing
**only the trigger** by using:

* [**asyncz.tasks.Taskk.reschedule()**](./tasks.md#reschedule-a-task) - The reschedule task from the Task
instance. The trigger must be the [alias of the trigger object](./triggers.md#alias).
* **reschedule_task** - The function from the scheduler instance to reschedule the task.

### Reschedule the task instance

```python hl_lines="26-30"
{!> ../docs_src/tasks/reschedule_task.py !}
```

### Reschedule from the scheduler

```python hl_lines="38-39"
{!> ../docs_src/schedulers/reschedule_task.py !}
```

## Resume and pause the tasks

Resuming and pausing task processing (all tasks) is also allowed with simple instructions.

### Pausing all tasks

```python hl_lines="35"
{!> ../docs_src/schedulers/pausing_all_tasks.py !}
```

### Resuming all tasks

```python hl_lines="38"
{!> ../docs_src/schedulers/resuming_all_tasks.py !}
```

## Start the scheduler in the paused state

Starting the scheduler without the paused state means without the first wakeup call.

```python hl_lines="35"
{!> ../docs_src/schedulers/start_with_paused.py !}
```

## BaseScheduler

The base of all available schedulers provided by Asyncz and **it should be the base** of any
[custom scheduler](#custom-scheduler).

The [parameters](#parameters) are the same as the ones described before.

```python
from asyncz.schedulers.base import BaseScheduler
```

## AsyncIOScheduler

This scheduler is the only one (at least for now) supported by Asyncz and as mentioned before,
it inherits from the [BaseScheduler](#basescheduler).

```python
from asyncz.schedulers import AsyncIOScheduler
```

This special scheduler besides the normal [parameters](#parameters) of the scheduler, also contains
some additional ones.

* **event_loop** - An optional. async event_loop to be used. If nothing is provided, it will use
the `asyncio.get_event_loop()` (global).
    
    <sup>Default: `None`</sup>

* **timeout** - A timeout used for start and stop the scheduler.

    <sup>Default: `None`</sup>

## Custom Scheduler

As mentioned before, Asyncz and the nature of its existence is to be more focused on ASGI and
asyncio applications but it is not limited to it.

You can create your own scheduler for any other use case, for example a blocking or background
scheduler.

Usually when creating a custom scheduler you must override at least 3 functions.

* **start()** - Function used to start/wakeup the scheduler for the first time.
* **shutdown()** - Function used to stop the scheduler and release the resources created up
`start()`.
* **wakeup()** - Manage the timer to notify the scheduler of the changes in the store.

There are also some optional functionalities you can override if you want.

* **create_default_executor** - Override this function if you want a different default executor.

```python
{!> ../docs_src/schedulers/custom_scheduler.py !}
```

## Limit the number of currently executing instances

By default, only one instance of each [Task](./tasks.md) is allowed to run at the same time.
To change that when creating a task you can set the `max_instances` to the number you desire and
this will let the scheduler know how many should run concurrently.

## Events

It is also possible to attach event listeners to the schedule. The events are triggered on specific
occasions and may carry some additional information with them regarding detauls of that specific
event. Check the [events](./events.md) section to see the available events.

```python hl_lines="18"
{!> ../docs_src/schedulers/add_event.py !}
```

## Final thoughts

Asyncz since it is a revamp, simplified and rewritten version of APScheduler, you will find very
common ground and similarities to it and that is intentional as you shouldn't be unfamiliar with
a lot of concepts if you are already familiar with APScheduler.
