from datetime import timezone as tz

from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger, IntervalTrigger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=tz.utc)


def send_email_newsletter():
    # Add logic to send emails here
    ...


def check_status():
    # Logic to check a given status of whatever needed
    ...


# Create the tasks
# Run every Monday, Wednesday and Friday
scheduler.add_task(
    id="send_email_newsletter",
    fn=send_email_newsletter,
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5"),
)

# Run every 10 minutes
scheduler.add_task(
    id="check_status",
    fn=check_status,
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)

# Reschedule the tasks
scheduler.reschedule_task(
    "send_email_newsletter", trigger="cron", day_of_week="mon", hour="1"
)
scheduler.reschedule_task("check_status", trigger="interval", minutes=20)

# Start the scheduler
scheduler.start()
