from typing import Optional  # noqa: F401

from pydantic import BaseModel

from asyncz.tasks.types import TaskDefaultsType


class TaskDefaultStruct(BaseModel, TaskDefaultsType):
    pass
