# Executors

Have you ever wondered what handles the tasks? Well, those are the executors and since Asyncz is
designed to be more focused on ASGI and asyncio that also means it only provides the
[AsyncIOExecutor](#asyncioexecutor) and the
[ThreadPoolExecutor](#threadpoolexecutor)/[ProcessPoolExecutor](#processpoolexecutor) out of the
box but you can also create your own [custom executor](#custom-executor) if you which as well.

When a task is done, it sends a notification to the scheduler informing that the task is done which
triggers the appropriate event.

## AsyncIOExecutor

Runs the default executor on the event loop. If the task is a couroutine, meaning, `async def`,
then it runs the task in the event loop directly or else it will run in the default that is
usually a thread pool.

**Plugin Alias**: `asyncio`

```python
from asyncz.executors import AsyncIOExecutor
```

### Parameters

* **scheduler** - The scheduler that is starting the executor.
* **alias** - The alias of the executor like it was assigned to the scheduler.

## ThreadPoolExecutor

An executor that runs the tasks in a concurrent.futures thread pool.

**Plugin Alias**: `threadpool`

```python
from asyncz.executors import ThreadPoolExecutor
```

### Parameters

* **max_workers** – Maximum number of spawned threads.
* **pool_kwargs** – Dict of keyword arguments to pass to the underlying ThreadPoolExecutor
constructor.
* **cancel_futures** – (Default: False) Cancel futures on shutdown. Has only an effect since python 3.9.
* **overwrite_wait** – (Default: Unset) Overwrite wait method used.

## ProcessPoolExecutor

**Plugin Alias**: `processpool`

```python
from asyncz.executors import ProcessPoolExecutor
```

### Parameters

* **max_workers** – Maximum number of spawned processes.
* **pool_kwargs** – Dict of keyword arguments to pass to the underlying ProcessPoolExecutor
constructor.
* **cancel_futures** – (Default: False) Cancel futures on shutdown. Has only an effect since python 3.9.
* **overwrite_wait** – (Default: Unset) Overwrite wait method used.

## Custom executor

You can also create a custom executor by subclassing the `BaseExecutor`.

```python
from asyncz.executors.base import BaseExecutor
```

You should also implement the `start()` and `shutdown()` of that same executor.
The executor has some responsabilities such as:

* Initialiase when call `start()`
* Release resources when `shutdown()`
* Track the number of instances of each task running on it and refusing to run more than the
maximum.
* Notify the scheduler of the results of the task.

All the states are done via pydantic models so you should also keep that in mind.

```python
{!> ../docs_src/executors/custom.py !}
```
