from typing import Optional, Union

from pydantic import BaseModel, ConfigDict

from asyncz.typing import UndefinedType


class TaskDefaultStruct(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    mistrigger_grace_time: Optional[Union[int, "UndefinedType"]]
    coalesce: Optional[Union[bool, "UndefinedType"]]
    max_instances: Optional[Union[int, "UndefinedType"]]
