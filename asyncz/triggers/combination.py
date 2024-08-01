from datetime import datetime, tzinfo
from typing import ClassVar, Optional, Union

from asyncz.triggers.base import BaseCombinationTrigger


class AndTrigger(BaseCombinationTrigger):
    """
    Always returns the earliest next trigger time that all the passed triggers agree on.
    The trigger is consideres to be finished when any of the given triggers finished its schedule.

    Args:
        triggers: List of triggers to combine.
        jitter: Delay the task execution by the jitter seconds at most.
    """

    alias: ClassVar[str] = "and"

    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        if now is None:
            now = datetime.now(timezone)
        while True:
            trigger_times = []
            for trigger in self.triggers:
                next_trigger_time = trigger.get_next_trigger_time(timezone, previous_time, now)
                # bail out early
                if next_trigger_time is None:
                    return None
                trigger_times.append(next_trigger_time)
            if min(trigger_times) == max(trigger_times):
                return self.apply_jitter(trigger_times[0], self.jitter, now)
            else:
                # recheck
                now = max(trigger_times)


class OrTrigger(BaseCombinationTrigger):
    """
    Always returns the earliest next trigger time produced by any of the given triggers.
    The trigger is considered finished when all the given triggers have finished their schedules.

    Args:
        triggers: List of triggers to combine.
        jitter: Delay the task execution by the jitter seconds at most.
    """

    alias: ClassVar[str] = "or"

    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        if now is None:
            now = datetime.now(timezone)
        trigger_times = []
        for trigger in self.triggers:
            next_trigger_time = trigger.get_next_trigger_time(timezone, previous_time, now)
            if next_trigger_time is not None:
                trigger_times.append(next_trigger_time)

        if trigger_times:
            return self.apply_jitter(min(trigger_times), self.jitter, now)
        else:
            return None
