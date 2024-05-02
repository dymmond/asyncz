from datetime import timezone as tz

from asyncz.schedulers.asyncio import AsyncIOScheduler

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
task = scheduler.add_task(send_email_newsletter, "cron", hour="0-23", minute="1")

# Pause task
task.pause()

# Run every hour and minute 1
task = scheduler.add_task(check_status, "cron", hour="0-23", minute="1")

# Pause task
task.pause()
