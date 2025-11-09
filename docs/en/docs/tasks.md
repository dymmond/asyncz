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
{!> ../../../docs_src/tasks/create_task.py !}
```

## Update a task

You can also update a specific task and its properties directly.

```python hl_lines="26-30"
{!> ../../../docs_src/tasks/update_task.py !}
```

Internally the task is using the given scheduler to be updated and then executed.

!!! Warning
    All attributes can be updated **but the id** as this is immutable.

## Reschedule a task

You can also reschedule a task when need and by that what it means is **changing its trigger only**.

The trigger must be the [alias of the trigger object](./triggers.md#alias).

```python hl_lines="26-30"
{!> ../../../docs_src/tasks/reschedule_task.py !}
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
{!> ../../../docs_src/tasks/lifecycle.py !}
```

Note the `make_function` and `make_async_function` decorators. They are required because the generator
methods have no signature. It is especially required for asend/athrow.

This is also possible with asynchronous generators.


!!! Warning
    Lifecycle tasks are only valid for the memory store. Generators cannot be pickled.


### Tasks with lifecycle in multi-processing environments

Natively we cannot add tasks with a lifecycle to other stores than the MemoryStore.
But we can combine both paradigmas with multiple stores or keeping the lifecycle task out of stores.

We have a memory store for the lifecycle and optionally an other store for the ticks in the lifecycle.
For multi-process synchronization we have the `asyncz.locks.FileProtectedLock`.

Here are some options:

#### Option 1: Multiple life-cycle tasks, tick only one

Here the setup of the life-cycle tasks is executed simultanously. In case of a setting up database
connections and having four worker processes, there will be after the setup 4 connections to the database.

When this is no problem, this is the easiest way.

lifecycle:

```python title="Tick only one lifecycle task, with shutdown"
{!> ../../../docs_src/tasks/lifecycle_mp_tick_only_one.py !}
```

The memory store is just required for the shutdown task and can be left out when having no shutdown tasks or the shutdown tasks use a global referencable function
like `lifecycle_tick`.


```python title="Tick only one lifecycle task, without shutdown"
{!> ../../../docs_src/tasks/lifecycle_mp_tick_only_one_simple.py !}
```

#### Option 2: Single life-cycle task, setup on demand

When there should be only one task creating for example connections to a database, this
type is the way to go.

Here we split the setup and the cleanup process each in two phases.

Next to the global setup/cleanup exists a file lock protected setup.
Here we start the clients and clean in the lock protected cleanup phase the clients up (e.g. disconnecting).

The clever part of the design is: whenever a process is stopped the next scheduler picks up:

```python title="Only one concurrent lifecycle task"
{!> ../../../docs_src/tasks/lifecycle_mp_only_one_instance.py !}
```

Can we simplify this? Yes. By sacrificing execution accuracy of the background job we can just remove the store lock from the scheduler
and remove the file store.
When a worker process is stopped, it is here possible that one cycle is skipped. But when this is no problem,
this is the way to go.

```python title="Only one concurrent lifecycle task with lower accuracy"
{!> ../../../docs_src/tasks/lifecycle_mp_only_one_instance_simple.py !}
```

#### Conclusions

That are only some options. In real-life setups it is even possible to mix the non-simplified options.
