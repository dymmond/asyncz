import inspect
from typing import Any

from asyncz.typing import DictAny
from pydantic import BaseModel

object_setattr = object.__setattr__


class BaseState(BaseModel):
    __slots__ = ["__weakref__"]

    def __setstate__(self, state: "DictAny") -> Any:
        """
        Retrives the data pickled and sets the state for Pydantic compatible fashion.
        """
        object_setattr(self, "__dict__", state.__dict__)
        object_setattr(self, "__fields_set__", state.__fields_set__)
        for name, value in state.__private_attributes__.items():
            if callable(value) or inspect.iscoroutinefunction(value):
                value = value.__name__
            object_setattr(self, name, value)
        return self

    class Config:
        arbitrary_types_allowed = True


class BaseStateExtra(BaseState):
    """
    Allows extra fields and allows to treat the class as a normal python object.
    """

    class Config(BaseState.Config):
        extra = "allow"
