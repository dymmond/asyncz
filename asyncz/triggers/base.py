import random
from datetime import datetime, timedelta
from typing import Any, Optional, Union, overload

from asyncz.datastructures import CombinationState
from asyncz.state import BaseStateExtra
from asyncz.triggers.types import TriggerType
from asyncz.utils import obj_to_ref, ref_to_obj


class BaseTrigger(BaseStateExtra, TriggerType):
    """
    Base model defining the protocol for every trigger.
    """

    @overload
    def apply_jitter(
        self, next_trigger_time: datetime, jitter: Optional[int], now: datetime
    ) -> datetime: ...

    @overload
    def apply_jitter(
        self, next_trigger_time: None, jitter: Optional[int], now: datetime
    ) -> None: ...

    def apply_jitter(
        self, next_trigger_time: Optional[datetime], jitter: Optional[int], now: datetime
    ) -> Union[datetime, None]:
        """
        Makes the next trigger time random by ading a random value (jitter).

        Args:
            next_trigger_time: The next triger time without the jitter.
            jitter: The maximum number of second to add to the next_trigger_time.
            now: The next trigger time with the jitter.
        """
        if next_trigger_time is None or not jitter:
            return next_trigger_time
        return next_trigger_time + timedelta(seconds=random.uniform(0, jitter))


class BaseCombinationTrigger(BaseTrigger):
    """
    Base combination for the triggers.

    Args:
        triggers: A list of triggers.
        jitter: he maximum number of second to add to the next_trigger_time.
    """

    triggers: list[TriggerType]

    def __init__(
        self,
        triggers: list[TriggerType],
        jitter: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        kwargs["triggers"] = triggers
        super().__init__(jitter=jitter, **kwargs)

    def __getstate__(self) -> "CombinationState":  # type: ignore
        triggers = [
            (obj_to_ref(trigger.__class__), trigger.__getstate__()) for trigger in self.triggers
        ]
        state = CombinationState(
            triggers=triggers,
            jitter=self.jitter,
        )
        return state

    def __setstate__(self, state: "CombinationState") -> None:  # type: ignore
        trigger = super().__setstate__(state)
        triggers = []

        for class_reference, state in trigger.triggers:
            klass = ref_to_obj(class_reference)
            trigger = klass.__new__(klass)
            trigger.__setstate__(state)
            triggers.append(trigger)

        self.triggers = triggers

    def __repr__(self) -> str:
        if self.jitter:
            jitters = f", jitter={self.jitter}"
            return f"<{self.__class__.__name__}({self.triggers}{jitters})>"
        return f"<{self.__class__.__name__}({self.triggers})>"

    def __str__(self) -> str:
        return f"{self.alias}[{', '.join(str(trigger) for trigger in self.triggers)}]"
