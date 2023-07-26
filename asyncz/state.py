import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict

object_setattr = object.__setattr__


class BaseState(BaseModel):
    __slots__ = ["__weakref__"]
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __setstate__(self, state: Any) -> Any:
        """
        Retrives the data pickled and sets the state for Pydantic compatible fashion.
        """
        state.model_config.update(self.model_config)
        object_setattr(self, "__dict__", state.__dict__)
        object_setattr(self, "__pydantic_fields_set__", state.__pydantic_fields_set__)
        object_setattr(self, "__pydantic_extra__", state.__pydantic_extra__)
        for name, value in state.__private_attributes__.items():
            if callable(value) or inspect.iscoroutinefunction(value):
                value = value.__name__
            object_setattr(self, name, value)

        return self


class BaseStateExtra(BaseState):
    """
    Allows extra fields and allows to treat the class as a normal python object.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
