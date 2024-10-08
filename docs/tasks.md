# Tasks

Big part of the Asyncz are the Tasks. Those are special objects with instructions and parameters
that are created/sent to the [scheduler](./schedulers.md) and then executed.

Importing a task is as simple as:

```python
from asyncz.tasks import Task
```

## Parameters

* **id** - The unique identifier of this task.
* **name** - The description of this task.
* **fn** - The callable function to execute.
* **args** - Positional arguments to the callable.
* **kwargs** - Keyword arguments to the callable.
* **coalesce** - Whether to only run the task once when several run times are due.
* **trigger** - The trigger object that controls the schedule of this task.
* **executor** - The name of the executor that will run this task.
* **mistrigger_grace_time** - The time (in seconds) how much this task's execution is allowed to
be late (None means "allow the task to run no matter how late it is").
* **max_instances** - The maximum number of concurrently executing instances allowed for this task.
* **next_run_time** - The next scheduled run time of this task. (Note: this has not the pause mode effect like in add_task)


## Create a task

Creating a task is as simple as:

```python
{!> ../docs_src/tasks/create_task.py !}
```

## Update a task

You can also update a specific task and its properties directly.

```python hl_lines="26-30"
{!> ../docs_src/tasks/update_task.py !}
```

Internally the task is using the given scheduler to be updated and then executed.

!!! Warning
    All attributes can be updated **but the id** as this is immutable.

## Reschedule a task

You can also reschedule a task when need and by that what it means is **changing its trigger only**.

The trigger must be the [alias of the trigger object](./triggers.md#alias).

```python hl_lines="26-30"
{!> ../docs_src/tasks/reschedule_task.py !}
```

## Tasks with lifecyle

Sometimes tasks need a setup and a cleanup routine. This is possible to implement via generators,
no matter if asynchronous or synchronous.

Generators have two methods: send, throw (for asynchronous generators there are asend and athrow).
The send methods take a parameter which is returned from yield:

``` python
def generator():
    print(yield)

g = generator()
# start generator, it is  required to be None
g.send(None)
# raises StopIteration
g.send("hello world")
```

Now let's adapt this for tasks with lifecycle:

```python
{!> ../docs_src/tasks/lifecycle.py !}
```

Note the `make_function` and `make_async_function` decorators. They are required because the generator
methods have no signature. It is especially required for asend/athrow.

This is also possible with asynchronous generators.
