import pytz

from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)


def send_email_newsletter():
    # Add logic to send emails here
    ...


def check_status():
    # Logic to check a given status of whatever needed
    ...


# Create the tasks
# Run every Monday, Wednesday and Friday
scheduler.add_task(
    id="send_newsletter",
    fn=send_email_newsletter,
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5"),
)

# Run every hour and minute 1
scheduler.add_task(
    id="status",
    fn=check_status,
    trigger=CronTrigger(hour="0-23", minute="1"),
)

# Pause all tasks
scheduler.pause()

# Resume all tasks
scheduler.resume()
