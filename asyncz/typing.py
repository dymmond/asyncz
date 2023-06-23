from typing import Any, Dict, Type, TypeVar, Union


class Undefined:
    """
    Special type created to handle undefined placeholders.
    """

    def __nonzero__(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "<undefined>"


undefined = Undefined()
UndefinedTypeVar = TypeVar("UndefinedTypeVar", bound=Undefined)
UndefinedType = Union[Type[UndefinedTypeVar], Undefined]

DictAny = Dict[Any, Any]
