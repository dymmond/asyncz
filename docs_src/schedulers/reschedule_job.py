import pytz
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.triggers import CronTrigger, IntervalTrigger

# Create the scheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)


def send_email_newsletter():
    # Add logic to send emails here
    ...


def check_status():
    # Logic to check a given status of whatever needed
    ...


# Create the jobs
# Run every Monday, Wednesday and Friday
scheduler.add_job(
    id="send_email_newsletter",
    fn=send_email_newsletter,
    trigger=CronTrigger(day_of_week="mon,wed,fri", hour="8", minute="1", second="5"),
)

# Run every 10 minutes
scheduler.add_job(
    id="check_status",
    fn=check_status,
    trigger=IntervalTrigger(minutes=10),
    max_instances=1,
    replace_existing=True,
    coalesce=False,
)

# Reschedule the jobs
scheduler.reschedule_job("send_email_newsletter", trigger="cron", day_of_week="mon", hour="1")
scheduler.reschedule_job("check_status", trigger="interval", minutes=20)

# Start the scheduler
scheduler.start()
