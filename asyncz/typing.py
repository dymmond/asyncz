from typing import Any, Dict


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
# legacy shim
UndefinedType = Undefined

DictAny = Dict[Any, Any]
DictStrAny = Dict[str, Any]
