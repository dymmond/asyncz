"""Performance benchmarks for asyncz core components."""

from datetime import datetime, timedelta, timezone

import pytest

from asyncz.triggers.cron import CronTrigger
from asyncz.triggers.date import DateTrigger
from asyncz.triggers.interval import IntervalTrigger
from asyncz.utils import (
    check_callable_args,
    datetime_ceil,
    datetime_to_utc_timestamp,
    ref_to_obj,
    timedelta_seconds,
    to_datetime,
    to_timezone,
    utc_timestamp_to_datetime,
)

# --- Utility function benchmarks ---


@pytest.mark.benchmark
def test_to_timezone_from_string():
    to_timezone("America/New_York")


@pytest.mark.benchmark
def test_to_datetime_from_string():
    to_datetime("2025-06-15 10:30:00+00:00", timezone.utc, "run_at")


@pytest.mark.benchmark
def test_datetime_to_utc_timestamp():
    dt = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    datetime_to_utc_timestamp(dt)


@pytest.mark.benchmark
def test_utc_timestamp_to_datetime():
    utc_timestamp_to_datetime(1750000200.0)


@pytest.mark.benchmark
def test_timedelta_seconds():
    delta = timedelta(days=2, hours=5, minutes=30, seconds=15, microseconds=500000)
    timedelta_seconds(delta)


@pytest.mark.benchmark
def test_datetime_ceil():
    dt = datetime(2025, 6, 15, 10, 30, 0, 500000, tzinfo=timezone.utc)
    datetime_ceil(dt)


@pytest.mark.benchmark
def test_ref_to_obj():
    ref_to_obj("asyncz.triggers.cron:CronTrigger")


@pytest.mark.benchmark
def test_check_callable_args():
    def sample_func(a, b, c=10):
        pass

    check_callable_args(sample_func, [1, 2], {"c": 3})


# --- Trigger creation benchmarks ---


@pytest.mark.benchmark
def test_create_cron_trigger():
    CronTrigger(hour=8, minute=30, second=0, timezone="UTC")


@pytest.mark.benchmark
def test_create_cron_trigger_from_crontab():
    CronTrigger.from_crontab("30 8 * * 1-5", timezone="UTC")


@pytest.mark.benchmark
def test_create_interval_trigger():
    IntervalTrigger(hours=1, minutes=30, timezone="UTC")


@pytest.mark.benchmark
def test_create_date_trigger():
    DateTrigger(run_at="2025-12-31 23:59:59", timezone="UTC")


# --- Trigger computation benchmarks ---


@pytest.mark.benchmark
def test_cron_trigger_next_fire_time():
    trigger = CronTrigger(hour=8, minute=30, second=0, timezone="UTC")
    now = datetime(2025, 6, 15, 7, 0, 0, tzinfo=timezone.utc)
    trigger.get_next_trigger_time(timezone.utc, None, now=now)


@pytest.mark.benchmark
def test_cron_trigger_next_fire_time_with_previous():
    trigger = CronTrigger(hour="*/2", minute=0, second=0, timezone="UTC")
    now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    previous = datetime(2025, 6, 15, 8, 0, 0, tzinfo=timezone.utc)
    trigger.get_next_trigger_time(timezone.utc, previous, now=now)


@pytest.mark.benchmark
def test_crontab_trigger_next_fire_time():
    trigger = CronTrigger.from_crontab("*/15 9-17 * * 1-5", timezone="UTC")
    now = datetime(2025, 6, 16, 9, 0, 0, tzinfo=timezone.utc)  # Monday
    trigger.get_next_trigger_time(timezone.utc, None, now=now)


@pytest.mark.benchmark
def test_interval_trigger_next_fire_time():
    trigger = IntervalTrigger(hours=1, minutes=30, timezone="UTC")
    now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    trigger.get_next_trigger_time(timezone.utc, None, now=now)


@pytest.mark.benchmark
def test_interval_trigger_next_fire_time_with_previous():
    trigger = IntervalTrigger(minutes=15, timezone="UTC")
    now = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    previous = datetime(2025, 6, 15, 10, 15, 0, tzinfo=timezone.utc)
    trigger.get_next_trigger_time(timezone.utc, previous, now=now)


@pytest.mark.benchmark
def test_date_trigger_next_fire_time():
    trigger = DateTrigger(
        run_at=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc), timezone="UTC"
    )
    trigger.get_next_trigger_time(timezone.utc, None, now=datetime.now(timezone.utc))
