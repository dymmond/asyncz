import tempfile
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task
from asyncz.utils import make_function

# Create a scheduler
scheduler = AsyncIOScheduler(
    lock_path="/tmp/asyncz_{pgrp}_{store}.lock",
    stores={
        "default": {"type": "file", "directory": tempfile.mkdtemp(), "cleanup_directory": True},
    },
)


def lifecycle_task():
    # setup
    ...
    running = yield
    while running:
        # do something
        running = yield
    # cleanup


# setup task
generator = lifecycle_task()
generator.send(None)


# must be a global referencable function
def lifecycle_tick():
    generator.send(True)


# Run every 5 minutes
scheduler.add_task(lifecycle_tick, trigger="interval", minutes=5)

scheduler.start()
...
# Now the shutdown task is executed and the generator progresses in the cleanup
scheduler.stop()
