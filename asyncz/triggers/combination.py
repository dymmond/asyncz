from datetime import datetime
from typing import Optional, Union

from asyncz.triggers.base import BaseCombinationTrigger


class AndTrigger(BaseCombinationTrigger):
    """
    Always returns the earliest next trigger time that all the passed triggers agree on.
    The trigger is consideres to be finished when any of the given triggers finished its schedule.

    Args:
        triggers: List of triggers to combine.
        jitter: Delay the task execution by the jitter seconds at most.
    """

    alias: str = "and"

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        while True:
            trigger_times = [
                trigger.get_next_trigger_time(previous_time, now) for trigger in self.triggers
            ]

            if None in trigger_times:
                return None
            elif min(trigger_times) == max(trigger_times):
                return self.apply_jitter(trigger_times[0], self.jitter, now)
            else:
                now = max(trigger_times)


class OrTrigger(BaseCombinationTrigger):
    """
    Always returns the earliest next trigger time produced by any of the given triggers.
    The trigger is considered finished when all the given triggers have finished their schedules.

    Args:
        triggers: List of triggers to combine.
        jitter: Delay the task execution by the jitter seconds at most.
    """

    alias: str = "or"

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        trigger_times = [
            trigger.get_next_trigger_time(previous_time, now) for trigger in self.triggers
        ]
        trigger_times = [
            trigger_time for trigger_time in trigger_times if trigger_time is not None
        ]

        if trigger_times:
            return self.apply_jitter(min(trigger_times), self.jitter, now)
        else:
            return None
