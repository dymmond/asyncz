import pickle
import random
from datetime import date, datetime, timedelta, tzinfo
from typing import Optional

import pytest
import pytz

from asyncz.triggers import (
    AndTrigger,
    BaseTrigger,
    CronTrigger,
    DateTrigger,
    IntervalTrigger,
    OrTrigger,
)


class DummyTriggerWithJitter(BaseTrigger):
    dt: Optional[datetime] = None

    def __init__(self, dt: datetime, jitter: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dt = dt
        self.jitter = jitter

    def get_next_trigger_time(self, timezone: tzinfo, previous_time: datetime, now: datetime):
        dt = self.dt
        if dt and not dt.tzinfo:
            dt = self.dt.replace(tzinfo=timezone)
        return self.apply_jitter(dt, self.jitter, now)


class TestDateTrigger:
    @pytest.mark.parametrize(
        "run_at,alter_tz,previous,now,expected",
        [
            (datetime(2022, 11, 3), None, None, datetime(2008, 5, 4), datetime(2022, 11, 3)),
            (datetime(2022, 11, 3), None, None, datetime(2022, 11, 3), datetime(2022, 11, 3)),
            (datetime(2022, 11, 3), None, None, datetime(2022, 11, 5), datetime(2022, 11, 3)),
            ("2022-11-3", None, None, datetime(2022, 11, 5), datetime(2022, 11, 3)),
            (datetime(2022, 11, 3), None, datetime(2022, 11, 3), datetime(2022, 11, 5), None),
            (
                datetime(2022, 11, 3, 22),
                pytz.FixedOffset(-60),
                datetime(2022, 11, 3),
                datetime(2022, 11, 3),
                None,
            ),
            (
                None,
                pytz.FixedOffset(-120),
                None,
                datetime(2022, 11, 3, 18, 40),
                datetime(2022, 11, 3, 18, 40),
            ),
        ],
        ids=[
            "earlier",
            "exact",
            "later",
            "as text",
            "previously fired",
            "alternate timezone",
            "current_time",
        ],
    )
    def test_get_next_trigger_time(
        self, run_at, alter_tz, previous, now, expected, timezone, freeze_time
    ):
        tz = alter_tz or timezone
        trigger = DateTrigger(run_at=run_at, timezone=tz)
        previous = timezone.localize(previous) if previous else None
        now = timezone.localize(now)
        expected = timezone.localize(expected) if expected else None
        assert trigger.get_next_trigger_time(timezone, previous, now) == expected

    @pytest.mark.parametrize("is_dst", [True, False], ids=["daylight saving", "standard time"])
    def test_dst_change(self, is_dst):
        """
        Test that DateTrigger works during the ambiguous "fall-back" DST period.

        Note that you should explicitly compare datetimes as strings to avoid the internal datetime
        comparison which would test for equality in the UTC timezone.

        """
        eastern = pytz.timezone("US/Eastern")
        run_at = eastern.localize(datetime(2013, 10, 3, 1, 5), is_dst=is_dst)

        trigger_date = eastern.normalize(run_at + timedelta(minutes=55))
        trigger = DateTrigger(run_at=trigger_date, timezone=eastern)
        assert str(trigger.get_next_trigger_time(eastern, None, trigger_date)) == str(trigger_date)

    def test_repr(self, timezone):
        trigger = DateTrigger(datetime(2022, 11, 3), timezone)
        assert repr(trigger) == "<DateTrigger (run_at='2022-11-03 00:00:00 GMT')>"

    def test_pickle(self, timezone):
        """Test that the trigger is pickleable."""
        trigger = DateTrigger(date(2022, 11, 3), timezone=timezone)
        data = pickle.dumps(trigger)
        trigger2 = pickle.loads(data)
        assert trigger2.run_at == trigger.run_at


class TestIntervalTrigger:
    @pytest.fixture()
    def trigger(self, timezone):
        return IntervalTrigger(
            seconds=1, start_at=datetime(2022, 11, 3, second=2), timezone=timezone
        )

    def test_invalid_interval(self, timezone):
        pytest.raises(TypeError, IntervalTrigger, "1-6", timezone=timezone)

    def test_start_end_times_string(self):
        trigger = IntervalTrigger(start_at="2022-11-05 05:06:53", end_at="2023-11-05 05:11:32")
        assert trigger.start_at == datetime(2022, 11, 5, 5, 6, 53)
        assert trigger.end_at == datetime(2023, 11, 5, 5, 11, 32)

    def test_before(self, trigger, timezone):
        """Tests that if "start_at" is later than "now", it will return start_at."""
        now = trigger.start_at - timedelta(seconds=2)
        assert now.tzinfo is not None
        assert trigger.get_next_trigger_time(timezone, None, now) == trigger.start_at

    def test_within(self, trigger, timezone):
        """
        Tests that if "now" is between "start_at" and the next interval, it will return the next
        interval.
        """
        now = trigger.start_at + timedelta(microseconds=1000)
        assert now.tzinfo is not None
        assert (
            trigger.get_next_trigger_time(timezone, None, now)
            == trigger.start_at + trigger.interval
        )

    def test_no_start_at(self, timezone):
        trigger = IntervalTrigger(seconds=2, timezone=timezone)
        now = datetime.now(timezone)
        assert (trigger.get_next_trigger_time(timezone, None, now) - now) <= timedelta(seconds=2)

    def test_end_at(self, timezone):
        """Tests that the interval trigger won't return any datetimes past the set end time."""
        start_at = timezone.localize(datetime(2022, 11, 4))
        trigger = IntervalTrigger(
            minutes=5,
            start_at=start_at,
            end_at=datetime(2022, 11, 4, 0, 7),
            timezone=timezone,
        )
        assert trigger.get_next_trigger_time(
            timezone, None, start_at + timedelta(minutes=2)
        ) == start_at.replace(minute=5)
        assert (
            trigger.get_next_trigger_time(timezone, None, start_at + timedelta(minutes=6)) is None
        )

    def test_dst_change(self):
        """
        Making sure that IntervalTrigger works during the ambiguous "fall-back" DST period.
        Note that you should explicitly compare datetimes as strings to avoid the internal datetime
        comparison which would test for equality in the UTC timezone.
        """
        eastern = pytz.timezone("US/Eastern")
        start_at = datetime(2013, 3, 1)  # Start within EDT
        trigger = IntervalTrigger(hours=1, start_at=start_at, timezone=eastern)

        datetime_edt = eastern.localize(datetime(2013, 3, 10, 1, 5), is_dst=False)
        correct_next_date = eastern.localize(datetime(2013, 3, 10, 3), is_dst=True)
        assert str(trigger.get_next_trigger_time(eastern, None, datetime_edt)) == str(
            correct_next_date
        )

        datetime_est = eastern.localize(datetime(2013, 11, 3, 1, 5), is_dst=True)
        correct_next_date = eastern.localize(datetime(2013, 11, 3, 1), is_dst=False)
        assert str(trigger.get_next_trigger_time(eastern, None, datetime_est)) == str(
            correct_next_date
        )

    def test_space_in_expr(self, timezone):
        trigger = CronTrigger(day="1-2, 4-7", timezone=timezone)
        assert "Europe/London" in repr(trigger)

    def test_repr(self, trigger):
        timedelta_args = "seconds=1"

        assert repr(trigger) == (
            f"<IntervalTrigger (interval=datetime.timedelta({timedelta_args}), "
            "start_at='2022-11-03 00:00:02 GMT', "
            "timezone='Europe/London')>"
        )

    def test_str(self, trigger):
        assert str(trigger) == "interval[0:00:01]"

    def test_pickle(self, timezone):
        trigger = IntervalTrigger(
            weeks=2,
            days=6,
            minutes=13,
            seconds=2,
            start_at=date(2016, 4, 3),
            timezone=timezone,
            jitter=12,
        )
        data = pickle.dumps(trigger)
        trigger2 = pickle.loads(data)

        assert trigger.timezone == trigger2.timezone
        assert trigger.start_at == trigger2.start_at
        assert trigger.end_at == trigger2.end_at
        assert trigger.interval == trigger2.interval
        assert trigger.jitter == trigger2.jitter

    def test_jitter_produces_different_valid_results(self, timezone):
        trigger = IntervalTrigger(seconds=5, timezone=timezone, jitter=3)
        now = datetime.now(timezone)

        results = set()
        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, now)
            results.add(next_trigger_time)
            assert timedelta(seconds=2) <= (next_trigger_time - now) <= timedelta(seconds=8)
        assert len(results) > 1

    @pytest.mark.parametrize(
        "trigger_args, start_at, start_at_dst, correct_next_date",
        [
            ({"hours": 1}, datetime(2013, 3, 10, 1, 35), False, datetime(2013, 3, 10, 3, 35)),
            ({"hours": 1}, datetime(2013, 11, 3, 1, 35), True, datetime(2013, 11, 3, 1, 35)),
        ],
        ids=["interval_spring", "interval_autumn"],
    )
    def test_jitter_dst_change(self, trigger_args, start_at, start_at_dst, correct_next_date):
        timezone = pytz.timezone("US/Eastern")
        epsilon = timedelta(seconds=1)
        start_at = timezone.localize(start_at, is_dst=start_at_dst)
        trigger = IntervalTrigger(timezone=timezone, start_at=start_at, jitter=5, **trigger_args)
        correct_next_date = timezone.localize(correct_next_date, is_dst=not start_at_dst)

        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, start_at + epsilon)
            assert abs(next_trigger_time - correct_next_date) <= timedelta(seconds=5)

    def test_jitter_with_end_at(self, timezone):
        now = timezone.localize(datetime(2017, 11, 12, 6, 55, 58))
        end_at = timezone.localize(datetime(2017, 11, 12, 6, 56, 0))
        trigger = IntervalTrigger(seconds=5, jitter=5, end_at=end_at)

        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, now)
            assert next_trigger_time is None or next_trigger_time <= end_at


class TestOrTrigger:
    @pytest.fixture
    def trigger(self, timezone):
        return OrTrigger(
            [
                CronTrigger(
                    month="5-8", day="6-15", end_at=timezone.localize(datetime(2022, 8, 10))
                ),
                CronTrigger(
                    month="6-9", day="*/3", end_at=timezone.localize(datetime(2022, 9, 7))
                ),
            ]
        )

    @pytest.mark.parametrize(
        "start_time, expected",
        [(datetime(2022, 8, 6), datetime(2022, 8, 6)), (datetime(2022, 9, 7, 1), None)],
        ids=["earliest", "end"],
    )
    def test_next_fire_time(self, trigger, timezone, start_time, expected):
        expected = timezone.localize(expected) if expected else None
        assert (
            trigger.get_next_trigger_time(timezone, None, timezone.localize(start_time))
            == expected
        )

    def test_jitter(self, trigger, timezone):
        trigger.jitter = 5
        start_time = expected = timezone.localize(datetime(2022, 8, 6))
        for _ in range(100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, start_time)
            assert abs(expected - next_trigger_time) <= timedelta(seconds=5)

    @pytest.mark.parametrize("jitter", [None, 5], ids=["nojitter", "jitter"])
    def test_repr(self, trigger, jitter):
        trigger.jitter = jitter
        jitter_part = f", jitter={jitter}" if jitter else ""

        assert repr(trigger) == (
            "<OrTrigger([<CronTrigger (month='5-8', day='6-15', "
            "end_at='2022-08-10 00:00:00 BST', timezone='Europe/London')>, <CronTrigger "
            "(month='6-9', day='*/3', end_at='2022-09-07 00:00:00 BST', "
            f"timezone='Europe/London')>]{jitter_part})>"
        )

    def test_str(self, trigger):
        assert str(trigger) == "or[cron[month='5-8', day='6-15'], cron[month='6-9', day='*/3']]"

    @pytest.mark.parametrize("jitter", [None, 5], ids=["nojitter", "jitter"])
    def test_pickle(self, trigger, jitter):
        trigger.jitter = jitter
        data = pickle.dumps(trigger)
        trigger2 = pickle.loads(data)

        assert trigger.jitter == trigger2.jitter
        assert repr(trigger) == repr(trigger2)


class TestAndTrigger:
    @pytest.fixture
    def trigger(self, timezone):
        return AndTrigger(
            [
                CronTrigger(
                    month="5-8", day="6-15", end_at=timezone.localize(datetime(2022, 8, 10))
                ),
                CronTrigger(
                    month="6-9", day="*/3", end_at=timezone.localize(datetime(2022, 9, 7))
                ),
            ]
        )

    @pytest.mark.parametrize(
        "start_time, expected",
        [(datetime(2022, 8, 6), datetime(2022, 8, 7)), (datetime(2022, 8, 10, 1), None)],
        ids=["firstmatch", "end"],
    )
    def test_next_trigger_time(self, trigger, timezone, start_time, expected):
        expected = timezone.localize(expected) if expected else None
        assert (
            trigger.get_next_trigger_time(timezone, None, timezone.localize(start_time))
            == expected
        )

    def test_jitter(self, trigger, timezone):
        trigger.jitter = 5
        start_time = timezone.localize(datetime(2022, 8, 6))
        expected = timezone.localize(datetime(2022, 8, 7))
        for _ in range(100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, start_time)
            assert abs(expected - next_trigger_time) <= timedelta(seconds=5)

    @pytest.mark.parametrize("jitter", [None, 5], ids=["nojitter", "jitter"])
    def test_repr(self, trigger, jitter):
        trigger.jitter = jitter
        jitter_part = f", jitter={jitter}" if jitter else ""
        assert repr(trigger) == (
            "<AndTrigger([<CronTrigger (month='5-8', day='6-15', "
            "end_at='2022-08-10 00:00:00 BST', timezone='Europe/London')>, <CronTrigger "
            "(month='6-9', day='*/3', end_at='2022-09-07 00:00:00 BST', "
            f"timezone='Europe/London')>]{jitter_part})>"
        )

    def test_str(self, trigger):
        assert str(trigger) == "and[cron[month='5-8', day='6-15'], cron[month='6-9', day='*/3']]"

    @pytest.mark.parametrize("jitter", [None, 5], ids=["nojitter", "jitter"])
    def test_pickle(self, trigger, jitter):
        """Test that the trigger is pickleable."""
        trigger.jitter = jitter
        data = pickle.dumps(trigger)
        trigger2 = pickle.loads(data)

        assert trigger.jitter == trigger2.jitter
        assert repr(trigger) == repr(trigger2)


class TestJitter:
    def test_jitter_disabled(self, timezone):
        dt = datetime(2022, 5, 25, 14, 49, 50, tzinfo=timezone)
        trigger = DummyTriggerWithJitter(dt, None)

        now = datetime(2022, 5, 25, 13, 40, 44, tzinfo=timezone)
        assert trigger.get_next_trigger_time(timezone, None, now) == dt

    def test_jitter_with_none_next_fire_time(self, timezone):
        trigger = DummyTriggerWithJitter(None, 5)
        now = datetime(2022, 5, 25, 13, 40, 44, tzinfo=timezone)
        assert trigger.get_next_trigger_time(timezone, None, now) is None

    def test_jitter_positive(self, monkeypatch, timezone):
        monkeypatch.setattr(random, "uniform", lambda a, b: 30.0)

        now = datetime(2022, 5, 25, 13, 40, 44, tzinfo=timezone)
        dt = datetime(2022, 5, 25, 14, 49, 50)
        expected_dt = datetime(2022, 5, 25, 14, 50, 20, tzinfo=timezone)

        trigger = DummyTriggerWithJitter(dt, 60)
        assert trigger.get_next_trigger_time(timezone, None, now) == expected_dt

    def test_jitter_in_future_but_initial_date_in_past(self, monkeypatch, timezone):
        monkeypatch.setattr(random, "uniform", lambda a, b: 30.0)

        now = datetime(2022, 5, 25, 13, 40, 44, tzinfo=timezone)
        dt = datetime(2022, 5, 25, 13, 40, 30)
        expected_dt = datetime(2022, 5, 25, 13, 41, 0, tzinfo=timezone)

        trigger = DummyTriggerWithJitter(dt, 60)
        assert trigger.get_next_trigger_time(timezone, None, now) == expected_dt

    def test_jitter_is_now(self, monkeypatch, timezone):
        monkeypatch.setattr(random, "uniform", lambda a, b: 4.0)

        now = datetime(2022, 5, 25, 13, 40, 44, tzinfo=timezone)
        dt = datetime(2022, 5, 25, 13, 40, 40)
        expected_dt = now

        trigger = DummyTriggerWithJitter(dt, 60)
        assert trigger.get_next_trigger_time(timezone, None, now) == expected_dt

    def test_jitter(self, timezone):
        now = datetime(2022, 5, 25, 13, 36, 44, tzinfo=timezone)
        dt = datetime(2022, 5, 25, 13, 40, 45)
        min_expected_dt = datetime(2022, 5, 25, 13, 40, 40, tzinfo=timezone)
        max_expected_dt = datetime(2022, 5, 25, 13, 40, 50, tzinfo=timezone)

        trigger = DummyTriggerWithJitter(dt, 5)
        for _ in range(0, 100):
            assert (
                min_expected_dt
                <= trigger.get_next_trigger_time(timezone, None, now)
                <= max_expected_dt
            )


class TestCronTrigger:
    def test_cron_trigger_1(self, timezone):
        trigger = CronTrigger(year="2022/2", month="1/3", day="5-13", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2022/2', month='1/3', day='5-13', " "timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2022/2', month='1/3', day='5-13']"
        start_at = timezone.localize(datetime(2021, 12, 1))
        correct_next_date = timezone.localize(datetime(2022, 1, 5))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_trigger_2(self, timezone):
        trigger = CronTrigger(year="2022/2", month="1/3", day="5-13", timezone=timezone)
        start_at = timezone.localize(datetime(2022, 10, 14))
        correct_next_date = timezone.localize(datetime(2024, 1, 5))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_trigger_3(self, timezone):
        trigger = CronTrigger(year="2022", month="feb-dec", hour="8-10", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2022', month='feb-dec', hour='8-10', "
            "timezone='Europe/London')>"
        )
        start_at = timezone.localize(datetime(2022, 1, 1))
        correct_next_date = timezone.localize(datetime(2022, 2, 1, 8))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_trigger_4(self, timezone):
        trigger = CronTrigger(year="2022", month="2", day="last", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2022', month='2', day='last', timezone='Europe/London')>"
        )
        start_at = timezone.localize(datetime(2022, 2, 1))
        correct_next_date = timezone.localize(datetime(2022, 2, 28))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_start_end_times_string(self, timezone, monkeypatch):
        trigger = CronTrigger(start_at="2022-11-05 05:06:53", end_at="2023-11-05 05:11:32")
        assert trigger.start_at == datetime(2022, 11, 5, 5, 6, 53)
        assert trigger.end_at == datetime(2023, 11, 5, 5, 11, 32)

    def test_cron_zero_value(self, timezone):
        trigger = CronTrigger(year=2022, month=2, hour=0, timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2022', month='2', hour='0', " "timezone='Europe/London')>"
        )

    def test_cron_year_list(self, timezone):
        trigger = CronTrigger(year="2023,2022", timezone=timezone)
        assert repr(trigger) == "<CronTrigger (year='2023,2022', timezone='Europe/London')>"
        assert str(trigger) == "cron[year='2023,2022']"
        start_at = timezone.localize(datetime(2023, 1, 1))
        correct_next_date = timezone.localize(datetime(2023, 1, 1))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_start_at(self, timezone):
        trigger = CronTrigger(
            year="2022", month="2", hour="8-10", start_at="2022-02-03 11:00:00", timezone=timezone
        )
        assert repr(trigger) == (
            "<CronTrigger (year='2022', month='2', hour='8-10', "
            "start_at='2022-02-03 11:00:00 GMT', "
            "timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2022', month='2', hour='8-10']"
        start_at = timezone.localize(datetime(2022, 1, 1))
        correct_next_date = timezone.localize(datetime(2022, 2, 4, 8))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_previous_trigger_time_1(self, timezone):
        trigger = CronTrigger(day="*", timezone=timezone)
        previous_fire_time = timezone.localize(datetime(2022, 11, 23))
        now = timezone.localize(datetime(2022, 11, 26))
        correct_next_date = timezone.localize(datetime(2022, 11, 24))
        assert (
            trigger.get_next_trigger_time(timezone, previous_fire_time, now) == correct_next_date
        )

    def test_previous_trigger_time_2(self, timezone):
        trigger = CronTrigger(day="*", timezone=timezone)
        previous_fire_time = timezone.localize(datetime(2022, 11, 23))
        now = timezone.localize(datetime(2022, 11, 22))
        correct_next_date = timezone.localize(datetime(2022, 11, 22))
        assert (
            trigger.get_next_trigger_time(timezone, previous_fire_time, now) == correct_next_date
        )

    def test_previous_trigger_time_3(self, timezone):
        trigger = CronTrigger(day="*", timezone=timezone)
        previous_fire_time = timezone.localize(datetime(2022, 4, 25))
        now = timezone.localize(datetime(2022, 4, 25))
        correct_next_date = timezone.localize(datetime(2022, 4, 26))
        assert (
            trigger.get_next_trigger_time(timezone, previous_fire_time, now) == correct_next_date
        )

    def test_cron_weekday_overlap(self, timezone):
        trigger = CronTrigger(year=2009, month=1, day="6-10", day_of_week="2-4", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', month='1', day='6-10', "
            "day_of_week='2-4', timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', month='1', day='6-10', day_of_week='2-4']"
        start_at = timezone.localize(datetime(2009, 1, 1))
        correct_next_date = timezone.localize(datetime(2009, 1, 7))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_weekday_nomatch(self, timezone):
        trigger = CronTrigger(year=2009, month=1, day="6-10", day_of_week="0,6", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', month='1', day='6-10', "
            "day_of_week='0,6', timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', month='1', day='6-10', day_of_week='0,6']"
        start_at = timezone.localize(datetime(2009, 1, 1))
        correct_next_date = None
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_weekday_positional(self, timezone):
        trigger = CronTrigger(year=2009, month=1, day="6-10", day_of_week="0,6", timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', month='1', day='6-10', "
            "day_of_week='0,6', timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', month='1', day='6-10', day_of_week='0,6']"
        start_at = timezone.localize(datetime(2009, 1, 1))
        correct_next_date = None
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_week_1(self, timezone):
        trigger = CronTrigger(year=2009, month=2, week=8, timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', month='2', week='8', " "timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', month='2', week='8']"
        start_at = timezone.localize(datetime(2009, 1, 1))
        correct_next_date = timezone.localize(datetime(2009, 2, 16))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_week_2(self, timezone):
        trigger = CronTrigger(year=2009, week=15, day_of_week=2, timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', week='15', day_of_week='2', " "timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', week='15', day_of_week='2']"
        start_at = timezone.localize(datetime(2009, 1, 1))
        correct_next_date = timezone.localize(datetime(2009, 4, 8))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_extra_coverage(self, timezone):
        trigger = CronTrigger(day="6,8", timezone=timezone)
        assert repr(trigger) == "<CronTrigger (day='6,8', timezone='Europe/London')>"
        assert str(trigger) == "cron[day='6,8']"
        start_at = timezone.localize(datetime(2022, 12, 31))
        correct_next_date = timezone.localize(datetime(2023, 1, 6))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_cron_faulty_expr(self, timezone):
        pytest.raises(ValueError, CronTrigger, year="2009-fault", timezone=timezone)

    def test_cron_increment_weekday(self, timezone):
        """
        Tests that incrementing the weekday field in the process of calculating the next matching
        date won't cause problems.
        """
        trigger = CronTrigger(hour="5-6", timezone=timezone)
        assert repr(trigger) == "<CronTrigger (hour='5-6', timezone='Europe/London')>"
        assert str(trigger) == "cron[hour='5-6']"
        start_at = timezone.localize(datetime(2022, 9, 25, 7))
        correct_next_date = timezone.localize(datetime(2022, 9, 26, 5))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    def test_month_rollover(self, timezone):
        trigger = CronTrigger(timezone=timezone, day=30)
        now = timezone.localize(datetime(2022, 2, 1))
        expected = timezone.localize(datetime(2022, 3, 30))
        assert trigger.get_next_trigger_time(timezone, None, now) == expected

    def test_timezone_from_start_at(self, timezone):
        """
        Tests that the trigger takes the timezone from the start_at parameter if no timezone is
        supplied.

        """
        start_at = timezone.localize(datetime(2022, 4, 13, 5, 30))
        trigger = CronTrigger(year=2022, hour=4, start_at=start_at)
        assert trigger.timezone == start_at.tzinfo

    def test_end_at(self, timezone):
        end_at = timezone.localize(datetime(2022, 4, 13, 3))
        trigger = CronTrigger(year=2022, hour=4, end_at=end_at)

        start_at = timezone.localize(datetime(2022, 4, 13, 2, 30))
        assert trigger.get_next_trigger_time(
            timezone, None, start_at - timedelta(1)
        ) == start_at.replace(
            day=12,
            hour=4,
            minute=0,
        )
        assert trigger.get_next_trigger_time(timezone, None, start_at) is None

    def test_different_tz(self, timezone):
        alter_tz = pytz.FixedOffset(-600)
        trigger = CronTrigger(year=2009, week=15, day_of_week=2, timezone=timezone)
        assert repr(trigger) == (
            "<CronTrigger (year='2009', week='15', day_of_week='2', " "timezone='Europe/London')>"
        )
        assert str(trigger) == "cron[year='2009', week='15', day_of_week='2']"
        start_at = alter_tz.localize(datetime(2008, 12, 31, 22))
        correct_next_date = timezone.localize(datetime(2009, 4, 8))
        assert trigger.get_next_trigger_time(timezone, None, start_at) == correct_next_date

    @pytest.mark.parametrize(
        "trigger_args, start_at, start_at_dst, correct_next_date",
        [
            ({"hour": 8}, datetime(2013, 3, 9, 12), False, datetime(2013, 3, 10, 8)),
            ({"hour": 8}, datetime(2013, 11, 2, 12), True, datetime(2013, 11, 3, 8)),
            ({"minute": "*/30"}, datetime(2013, 3, 10, 1, 35), False, datetime(2013, 3, 10, 3)),
            ({"minute": "*/30"}, datetime(2013, 11, 3, 1, 35), True, datetime(2013, 11, 3, 1)),
        ],
        ids=["absolute_spring", "absolute_autumn", "interval_spring", "interval_autumn"],
    )
    def test_dst_change(self, trigger_args, start_at, start_at_dst, correct_next_date):
        """
        Making sure that CronTrigger works correctly when crossing the DST switch threshold.
        Note that you should explicitly compare datetimes as strings to avoid the internal datetime
        comparison which would test for equality in the UTC timezone.

        """
        timezone = pytz.timezone("US/Eastern")
        trigger = CronTrigger(timezone=timezone, **trigger_args)
        start_at = timezone.localize(start_at, is_dst=start_at_dst)
        correct_next_date = timezone.localize(correct_next_date, is_dst=not start_at_dst)
        assert str(trigger.get_next_trigger_time(timezone, None, start_at)) == str(
            correct_next_date
        )

    def test_timezone_change(self):
        """
        Ensure that get_next_fire_time method returns datetimes in the timezone of the trigger and
        not in the timezone of the passed in start_at.

        """
        est = pytz.FixedOffset(-300)
        cst = pytz.FixedOffset(-360)
        trigger = CronTrigger(hour=11, minute="*/5", timezone=est)
        start_at = cst.localize(datetime(2022, 9, 26, 10, 16))
        correct_next_date = est.localize(datetime(2022, 9, 26, 11, 20))
        assert str(trigger.get_next_trigger_time(est, None, start_at)) == str(correct_next_date)

    def test_pickle(self, timezone):
        trigger = CronTrigger(
            year=2022, month="5-6", day="20-28", hour=7, minute=25, second="*", timezone=timezone
        )
        data = pickle.dumps(trigger)
        trigger2 = pickle.loads(data)

        assert repr(trigger) == repr(trigger2)

    def test_jitter_produces_differrent_valid_results(self, timezone):
        trigger = CronTrigger(minute="*", jitter=5)
        now = timezone.localize(datetime(2022, 11, 12, 6, 55, 30))

        results = set()
        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, now)
            results.add(next_trigger_time)
            assert timedelta(seconds=25) <= (next_trigger_time - now) <= timedelta(seconds=35)

        assert len(results) > 1

    def test_jitter_with_timezone(self):
        est = pytz.FixedOffset(-300)
        cst = pytz.FixedOffset(-360)
        trigger = CronTrigger(hour=11, minute="*/5", timezone=est, jitter=5)
        start_at = cst.localize(datetime(2022, 9, 26, 10, 16))
        correct_next_date = est.localize(datetime(2022, 9, 26, 11, 20))
        for _ in range(0, 100):
            assert abs(
                trigger.get_next_trigger_time(est, None, start_at) - correct_next_date
            ) <= timedelta(seconds=5)

    @pytest.mark.parametrize(
        "trigger_args, start_at, start_at_dst, correct_next_date",
        [
            ({"hour": 8}, datetime(2013, 3, 9, 12), False, datetime(2013, 3, 10, 8)),
            ({"hour": 8}, datetime(2013, 11, 2, 12), True, datetime(2013, 11, 3, 8)),
            ({"minute": "*/30"}, datetime(2013, 3, 10, 1, 35), False, datetime(2013, 3, 10, 3)),
            ({"minute": "*/30"}, datetime(2013, 11, 3, 1, 35), True, datetime(2013, 11, 3, 1)),
        ],
        ids=["absolute_spring", "absolute_autumn", "interval_spring", "interval_autumn"],
    )
    def test_jitter_dst_change(self, trigger_args, start_at, start_at_dst, correct_next_date):
        timezone = pytz.timezone("US/Eastern")
        trigger = CronTrigger(timezone=timezone, jitter=5, **trigger_args)
        start_at = timezone.localize(start_at, is_dst=start_at_dst)
        correct_next_date = timezone.localize(correct_next_date, is_dst=not start_at_dst)

        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, start_at)
            assert abs(next_trigger_time - correct_next_date) <= timedelta(seconds=5)

    def test_jitter_with_end_at(self, timezone):
        now = timezone.localize(datetime(2022, 11, 12, 6, 55, 30))
        end_at = timezone.localize(datetime(2022, 11, 12, 6, 56, 0))
        trigger = CronTrigger(minute="*", jitter=5, end_at=end_at)

        for _ in range(0, 100):
            next_trigger_time = trigger.get_next_trigger_time(timezone, None, now)
            assert next_trigger_time is None or next_trigger_time <= end_at

    @pytest.mark.parametrize(
        "values, expected",
        [
            (
                {"day": "*/31"},
                r"Error validating expression '\*/31': The step value \(31\) is higher "
                r"than the total range of the expression \(30\).",
            ),
            (
                {"day": "4-6/3"},
                r"Error validating expression '4-6/3': The step value \(3\) is higher "
                r"than the total range of the expression \(2\).",
            ),
            (
                {"hour": "0-24"},
                r"Error validating expression '0-24': The last value \(24\) is higher "
                r"than the maximum value \(23\).",
            ),
            (
                {"day": "0-3"},
                r"Error validating expression '0-3': The first value \(0\) is lower "
                r"than the minimum value \(1\).",
            ),
        ],
        ids=["too_large_step_all", "too_large_step_range", "too_high_last", "too_low_first"],
    )
    def test_invalid_ranges(self, values, expected):
        pytest.raises(ValueError, CronTrigger, **values).match(expected)

    @pytest.mark.parametrize(
        "expr, expected_repr",
        [
            (
                "* * * * *",
                "<CronTrigger (month='*', day='*', day_of_week='*', hour='*', minute='*', "
                "timezone='Europe/London')>",
            ),
            (
                "0-14 * 14-28 jul fri",
                "<CronTrigger (month='jul', day='14-28', day_of_week='fri', hour='*', minute='0-14', "
                "timezone='Europe/London')>",
            ),
            (
                " 0-14   * 14-28   jul       fri",
                "<CronTrigger (month='jul', day='14-28', day_of_week='fri', hour='*', minute='0-14', "
                "timezone='Europe/London')>",
            ),
        ],
        ids=["always", "assorted", "multiple_spaces_in_format"],
    )
    def test_from_crontab(self, expr, expected_repr, timezone):
        trigger = CronTrigger.from_crontab(expr, timezone)
        assert repr(trigger) == expected_repr
