from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task
from asyncz.triggers import CronTrigger

# Create a scheduler
scheduler = AsyncIOScheduler()


def check_status():
    # Logic to check statuses
    ...


# Create a task
task = Task(
    id="my-task",
    fn=check_status,
    name="my-func",
    scheduler=scheduler,
    trigger=CronTrigger(day_of_week="mon,tue,wed,thu,fri,sat,sun", hour=8, minute=1),
    max_instances=3,
    coalesce=True,
)

# Reschedule the task
task.reschedule("my-task", trigger="cron", hour=10, minute=5)
