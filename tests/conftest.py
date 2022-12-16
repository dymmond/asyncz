# coding: utf-8
from datetime import datetime
from unittest.mock import Mock

import pytest
import pytz
from asyncz.jobs import Job
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.schedulers.base import BaseScheduler


@pytest.fixture
def timezone(monkeypatch):
    tz = pytz.timezone("Europe/London")
    monkeypatch.setattr("asyncz.schedulers.base.get_localzone", Mock(return_value=tz))
    return tz


@pytest.fixture
def freeze_time(monkeypatch, timezone):
    class TimeFreezer:
        def __init__(self, initial):
            self.current = initial
            self.increment = None

        def get(self, tzinfo=None):
            now = self.current.astimezone(tzinfo) if tzinfo else self.current.replace(tzinfo=None)
            if self.increment:
                self.current += self.increment
            return now

        def set(self, new_time):
            self.current = new_time

        def next(
            self,
        ):
            return self.current + self.increment

        def set_increment(self, delta):
            self.increment = delta

    freezer = TimeFreezer(timezone.localize(datetime(2022, 11, 3, 18, 40)))
    fake_datetime = Mock(datetime, now=freezer.get)
    monkeypatch.setattr("asyncz.schedulers.base.datetime", fake_datetime)
    monkeypatch.setattr("asyncz.executors.base.datetime", fake_datetime)
    monkeypatch.setattr("asyncz.triggers.interval.datetime", fake_datetime)
    monkeypatch.setattr("asyncz.triggers.date.datetime", fake_datetime)
    return freezer


@pytest.fixture
def job_defaults(timezone):
    run_at = timezone.localize(datetime(2022, 11, 3, 18, 40))
    return {
        "trigger": "date",
        "trigger_args": {"run_at": run_at, "timezone": timezone},
        "executor": "default",
        "args": (),
        "kwargs": {},
        "id": b"t\xc3\xa9st\xc3\xafd".decode("utf-8"),
        "mistrigger_grace_time": 1,
        "coalesce": False,
        "name": b"n\xc3\xa4m\xc3\xa9".decode("utf-8"),
        "max_instances": 1,
    }


@pytest.fixture
def create_job(job_defaults, timezone):
    def create(**kwargs):
        kwargs.setdefault("scheduler", Mock(BaseScheduler, timezone=timezone))
        job_kwargs = job_defaults.copy()
        job_kwargs.update(kwargs)
        job_kwargs["trigger"] = AsyncIOScheduler().create_trigger(
            job_kwargs.pop("trigger"), job_kwargs.pop("trigger_args")
        )
        job_kwargs.setdefault("next_run_time", None)
        return Job(**job_kwargs)

    return create
