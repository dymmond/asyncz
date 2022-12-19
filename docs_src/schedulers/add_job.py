import pytz
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger, IntervalTrigger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)


def send_email_newsletter():
    # Add logic to send emails here
    ...


def collect_www_info():
    # Add logic to collect information from the internet
    ...


def check_status():
    # Logic to check a given status of whatever needed
    ...


# Createthe jobs
# Run every Monday, Wednesday and Friday
scheduler.add_job(
    fn=send_email_newsletter,
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5"),
)

# Run every 2 minutes
scheduler.add_job(
    fn=collect_www_info,
    trigger=IntervalTrigger(minutes=2),
    max_instances=1,
    replace_existing=True,
    coalesce=True,
)

# Run every 10 minutes
scheduler.add_job(
    fn=check_status,
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)

# Start the scheduler
scheduler.start()
