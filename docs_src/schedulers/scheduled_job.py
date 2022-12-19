import pytz
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger, IntervalTrigger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)


# Run every Monday, Wednesday and Friday
@scheduler.scheduled_job(
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5")
)
def send_email_newsletter():
    # Add logic to send emails here
    ...


# Run every 2 minutes
@scheduler.scheduled_job(
    trigger=IntervalTrigger(minutes=2),
    max_instances=1,
    coalesce=True,
)
def collect_www_info():
    # Add logic to collect information from the internet
    ...


@scheduler.scheduled_job(
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    coalesce=False,
)
def check_status():
    # Logic to check a given status of whatever needed
    ...


# Start the scheduler
scheduler.start()
