import tempfile
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task
from asyncz.utils import make_function
from asyncz.locks import FileLockProtected

# Create a scheduler
scheduler = AsyncIOScheduler(
    lock_path="/tmp/asyncz_{pgrp}_{store}.lock",
    stores={
        "default": {"type": "file", "directory": tempfile.mkdtemp(), "cleanup_directory": True},
        "memory": {"type": "memory"},
    },
)


def lifecycle_task(name: str):
    # setup initial
    ...
    # intialize a file lock (multi-processing safe)
    file_lock = FileLockProtected(f"/tmp/asyncz_bg_{name}_{{pgrp}}.lock")
    while True:
        # don't block the generator
        with file_lock.protected(False) as got_the_lock:
            if not got_the_lock:
                running = yield
                if not running:
                    break
                continue
            # delayed setup phase. Only executed when the lock was grabbed. e.g. for  creating db clients.
            ...
            # we have to mask generator send so it could be set to a task
            scheduler.add_task(
                make_function(generator.send), args=[False], trigger="shutdown", store="memory"
            )
            running = yield
            while running:
                # do something safe
                try:
                    # do something risky
                    ...
                except Exception:
                    # log
                    ...
                running = yield
            try:
                # cleanup the loop setup
                ...
            except Exception:
                # log
                ...
            # break the loop
            break
    # extra cleanup which is always executed except an exception was raised


# setup task
generator = lifecycle_task("foo")
generator.send(None)


# must be a global referencable function
def lifecycle_tick():
    generator.send(True)


# Run every 5 minutes
scheduler.add_task(lifecycle_tick, trigger="interval", minutes=5)

# should be better a context manager or lifespan wrapper (.asgi) to cleanup on unexpected errors
with scheduler:
    ...
    # Now the shutdown task is executed and the generator progresses in the cleanup
