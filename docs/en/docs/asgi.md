# ASGI and Context Managers

Asyncz schedulers use reference counting for `start()` and `shutdown()`. That makes them safe to use from nested context managers, lifespan handlers, and wrapper middleware without double-starting or double-shutting down the same scheduler instance.

## Wrapping an ASGI application

`AsyncIOScheduler.asgi()` can either wrap an application directly or return a decorator-style wrapper.

### Direct wrapping

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()
application = scheduler.asgi(application)
```

### Decorator-style wrapping

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()
application = scheduler.asgi()(application)
```

### Parameters

- `app`: the ASGI application to wrap. When omitted, `asgi()` returns a wrapper function.
- `handle_lifespan`: intercept lifespan events instead of passing them through. This is useful when the wrapped application does not implement the ASGI lifespan protocol.
- `wait`: forwarded to `shutdown()`. Set it to `False` if you want running tasks to be cancelled during shutdown.

## Manual startup and shutdown

Manual wiring is often the clearest option when your framework already has startup and shutdown hooks.

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()

app = Lilya(
    routes=[...],
    on_startup=[scheduler.start],
    on_shutdown=[scheduler.shutdown],
)
```

## Starlette lifespan example

```python
from asyncz.schedulers import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def lifespan(app):
    async with scheduler:
        yield


app = Starlette(lifespan=lifespan)
```

## Sync and async context managers

### Synchronous

```python
from asyncz.schedulers import AsyncIOScheduler

with AsyncIOScheduler() as scheduler:
    ...
```

### Asynchronous

```python
from asyncz.schedulers import AsyncIOScheduler

async with AsyncIOScheduler() as scheduler:
    ...
```

## Choosing between `AsyncIOScheduler` and `NativeAsyncIOScheduler`

- Use `AsyncIOScheduler` when Asyncz should manage or create the event loop integration for you.
- Use `NativeAsyncIOScheduler` when you are already inside a running event loop and want `start()` / `shutdown()` to be awaitable.
