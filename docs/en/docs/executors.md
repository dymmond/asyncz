# Executors

Executors are responsible for actually running task callables after the scheduler decides they are due.

## Built-in executors

### `AsyncIOExecutor`

Runs work on the scheduler event loop. Coroutine functions are awaited directly. Regular callables run through the loop's default executor.

- Plugin alias: `asyncio`

```python
from asyncz.executors import AsyncIOExecutor
```

### `ThreadPoolExecutor`

Runs work in a `concurrent.futures.ThreadPoolExecutor`.

- Plugin aliases: `pool`, `threadpool`
- Best for: blocking I/O or code that should not block the event loop

```python
from asyncz.executors import ThreadPoolExecutor
```

Parameters:

- `max_workers`
- `pool_kwargs`
- `cancel_futures`
- `overwrite_wait`

### `ProcessPoolExecutor`

Runs work in a `concurrent.futures.ProcessPoolExecutor`.

- Plugin alias: `processpool`
- Best for: CPU-bound work that benefits from process isolation

```python
from asyncz.executors import ProcessPoolExecutor
```

Parameters:

- `max_workers`
- `pool_kwargs`
- `cancel_futures`
- `overwrite_wait`

### `DebugExecutor`

Executes the task inline instead of deferring it to another thread or process. This is useful in tests or while debugging task behavior.

- Plugin alias: `debug`

```python
from asyncz.executors import DebugExecutor
```

## Choosing an executor

- Use `asyncio` for coroutine-heavy workloads.
- Use `threadpool` for blocking I/O that should not block the loop.
- Use `processpool` for CPU-bound functions that are safe to pickle.
- Use `debug` for deterministic local testing.

## Logger namespaces

Executors log through:

```text
asyncz.executors.<alias>
```

## Custom executors

Custom executors must subclass `BaseExecutor` and implement at least:

- `start()`
- `shutdown()`
- `do_send_task()`

```python
{!> ../../../docs_src/executors/custom.py !}
```
