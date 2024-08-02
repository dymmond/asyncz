from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task
from asyncz.triggers import CronTrigger

# Create a scheduler
scheduler = AsyncIOScheduler()


def check_status():
    # Logic to check statuses
    ...


Task(
    id="my-task",
    fn=check_status,
    name="my-func",
    scheduler=scheduler,
    trigger=CronTrigger(day_of_week="mon,tue,wed,thu,fri,sat,sun", hour=8, minute=1),
    max_instances=3,
    coalesce=True,
)

scheduler.start()

# or manually submit one with a changed trigger

t = Task(
    id="my-task2",
    fn=check_status,
    max_instances=1,
    coalesce=True,
)

scheduler.add_task(
    t, trigger=CronTrigger(day_of_week="mon,tue,wed,thu,fri,sat,sun", hour=8, minute=1)
)
