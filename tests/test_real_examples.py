import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time as freeze_time_freezegun

from asyncz.schedulers import NativeAsyncIOScheduler
from asyncz.triggers import CronTrigger


@pytest.mark.parametrize("tz", ["Etc/UTC", "Asia/Kolkata"])
@pytest.mark.asyncio(loop_scope="function")
async def test_tz_cron(tz):
    time_zone_string = "Asia/Kolkata"
    trigger = CronTrigger.from_crontab("0 8 * * *", time_zone_string)
    scheduler = NativeAsyncIOScheduler(timezone=tz)

    called: int = 0

    def execution_function():
        nonlocal called
        called += 1

    scheduler.add_task(
        execution_function,
        trigger=trigger,
        id="some_random_id",
    )
    with freeze_time_freezegun(
        datetime(2025, 5, 1, 7, 59, 59, tzinfo=ZoneInfo(time_zone_string)), tick=True
    ) as t:
        async with scheduler:
            assert called == 0
            await asyncio.sleep(2)
            assert called == 1
            t.move_to(
                datetime(2025, 5, 2, 7, 59, 59, tzinfo=ZoneInfo(time_zone_string)).astimezone(
                    timezone.utc
                )
            )
            assert called == 1
            await asyncio.sleep(2)
            assert called == 2
