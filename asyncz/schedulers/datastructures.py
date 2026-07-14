from typing import Optional

from asyncz.tasks.types import TaskDefaultsType


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off"}:
            return False
    return bool(value)


class TaskDefaultStruct(TaskDefaultsType):
    """
    Asyncz-owned task defaults with Pydantic-style dump compatibility.

    The scheduler owns these defaults. Shapes may provide the incoming
    representation, but this object remains the canonical scheduler contract.
    """

    __slots__ = ("coalesce", "max_instances", "mistrigger_grace_time")

    def __init__(
        self,
        mistrigger_grace_time: Optional[float] = 1,
        coalesce: bool = True,
        max_instances: int = 1,
        **extra: object,
    ) -> None:
        self.mistrigger_grace_time = (
            None if mistrigger_grace_time is None else float(mistrigger_grace_time)
        )
        self.coalesce = _coerce_bool(coalesce)
        self.max_instances = int(max_instances)

    def model_dump(self, *, exclude_none: bool = False, **kwargs: object) -> dict[str, object]:
        data: dict[str, object] = {
            "mistrigger_grace_time": self.mistrigger_grace_time,
            "coalesce": self.coalesce,
            "max_instances": self.max_instances,
        }
        if exclude_none:
            return {key: value for key, value in data.items() if value is not None}
        return data
