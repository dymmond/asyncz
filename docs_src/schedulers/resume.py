import pytz
from asyncz.schedulers.asyncio import AsyncIOScheduler

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
job = scheduler.add_job(send_email_newsletter, "cron", hour="0-23", minute="1")

# resume job
job.resume()

# Run every hour and minute 1
job = scheduler.add_job(check_status, "cron", hour="0-23", minute="1")

# Resume job
job.resume()
