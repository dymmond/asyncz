from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task
from asyncz.utils import make_function

# Create a scheduler
scheduler = AsyncIOScheduler()


def lifecycle_task():
    # setup
    ...
    # we have to mask generator send so it could be set to a task
    scheduler.add_task(make_function(generator.send), args=[False], trigger="shutdown")
    running = yield
    while running:
        # do something
        running = yield
    # cleanup


# setup task
generator = lifecycle_task()
generator.send(None)

# Run every 5 minutes
scheduler.add_task(make_function(generator.send), args=[True], trigger="interval", minutes=5)

scheduler.start()
...
# Now the shutdown task is executed and the generator progresses in the cleanup
scheduler.stop()
