
# ASGI and Contextmanager

The scheduler uses refcounting for start and stop calls. Only if refs drop to 0 it is shutdown.
This way it is compatible to lifespan and nested contextmanager calls.

=== "Wrapping an asgi application"

    ```python
    from asyncz.schedulers import AsyncIOScheduler
    ...

    # handle_lifespan is optional, set to True if you don't want to pass it down because the underlying app doesn't support it
    # this is true for django
    application = AsyncIOScheduler().asgi(application, handle_lifespan=False)
    # or more simple (please do not use both together)
    application = AsyncIOScheduler().asgi()(application)
    ```

=== "Using with lilya"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    # Lilya middleware doesn't pass lifespan events

    app = AsyncIOScheduler().asgi(Lilya(
        routes=[...],
    ))

    ```

    Or manually:

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    app = Lilya(
        routes=[...],
        on_startup=[scheduler.start],
        on_shutdown=[scheduler.shutdown],
    )

    ```


## Contextmanager support

=== "Use as sync contextmanager"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    with AsyncIOScheduler() as scheduler:
        # nesting is no problem
        with AsyncIOScheduler() as scheduler2:
            ...
    ```

=== "Use as async contextmanager"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    async with AsyncIOScheduler() as scheduler:
        # nesting is no problem
        async with AsyncIOScheduler() as scheduler2:
            ...
    ```


For using with lifespan of starlette


=== "Starlette"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    async lifespan(app):
        with AsyncIOScheduler() as scheduler:
            yield
            # or yield a state
    app = Starlette(
        lifespan=lifespan,
    )
    ```
