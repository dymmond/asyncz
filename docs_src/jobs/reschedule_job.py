from asyncz.jobs import Job
from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers import CronTrigger

# Create a scheduler
scheduler = AsyncIOScheduler()


def check_status():
    # Logic to check statuses
    ...


# Create a job
job = Job(
    id="my-job",
    fn=check_status,
    name="my-func",
    scheduler=scheduler,
    trigger=CronTrigger(day_of_week="mon,tue,wed,thu,fri,sat,sun", hour=8, minute=1),
    max_instances=3,
    coalesce=True,
)

# Reschedule the job
job.reschedule("my-job", trigger="cron", hour=10, minute=5)
