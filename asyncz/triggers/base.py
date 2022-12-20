import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional, Union

from asyncz.datastructures import CombinationState
from asyncz.state import BaseStateExtra
from asyncz.typing import DictAny
from asyncz.utils import obj_to_ref, ref_to_obj

if TYPE_CHECKING:
    from asyncz.triggers.types import TriggerType


class BaseTrigger(BaseStateExtra, ABC):
    """
    Base model defining the protocol for every trigger.
    """
    alias: Optional[str] = None

    @abstractmethod
    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        """
        Returns the next datetime to trigger. If the datetime cannot be calculated, then returns None.

        Args:
            previous_time: The previous time the trigger was fired.
            now: The current datetime.
        """
        ...

    def apply_jitter(
        self, next_trigger_time: datetime, jitter: int, now: datetime
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

    def __init__(
        self,
        triggers: List["TriggerType"],
        jitter: Optional[int] = None,
        **kwargs: "DictAny",
    ):
        super().__init__(**kwargs)
        self.triggers = triggers
        self.jitter = jitter

    def __getstate__(self) -> "CombinationState":
        triggers = [
            (obj_to_ref(trigger.__class__), trigger.__getstate__()) for trigger in self.triggers
        ]
        state = CombinationState(
            triggers=triggers,
            jitter=self.jitter,
        )
        return state

    def __setstate__(self, state: "CombinationState") -> None:
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
