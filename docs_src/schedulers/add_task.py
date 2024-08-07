from datetime import timezone as tz

from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger, IntervalTrigger
from asyncz.tasks import Task

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=tz.utc)


def send_email_newsletter():
    # Add logic to send emails here
    ...


def collect_www_info():
    # Add logic to collect information from the internet
    ...


def check_status():
    # Logic to check a given status of whatever needed
    ...


# Create the tasks
# Run every Monday, Wednesday and Friday
scheduler.add_task(
    send_email_newsletter,
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5"),
)

# Run every 2 minutes
scheduler.add_task(
    collect_www_info,
    trigger=IntervalTrigger(minutes=2),
    max_instances=1,
    replace_existing=True,
    coalesce=True,
)

# Run every 10 minutes
scheduler.add_task(
    check_status,
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)

# Run every 10 minutes collect_www_info before sending the newsletter
feed_data = collect_www_info()

scheduler.add_task(
    fn_or_task=send_email_newsletter,
    args=[feed_data],
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)

# Add Task object

task = Task(
    fn=send_email_newsletter,
    args=[feed_data],
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)
# you can update most attributes here. Note: a task can be only submitted once
scheduler.add_task(task)

# Use Task as decorator (leave fn empty)
decorator = scheduler.add_task(
    args=[feed_data],
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)
decorator(send_email_newsletter)


# Start the scheduler
scheduler.start()

# Add paused Task
scheduler.add_task(
    send_email_newsletter,
    args=[feed_data],
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
    # this pauses the task on submit
    next_run_time=None,
)
