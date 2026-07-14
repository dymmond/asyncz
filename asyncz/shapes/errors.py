from __future__ import annotations

from asyncz.exceptions import AsynczException


class ShapeError(AsynczException):
    """
    Base error for Asyncz Shape operations.
    """


class ShapeNotFoundError(ShapeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown Asyncz Shape '{name}'.")


class ShapeRegistrationError(ShapeError):
    pass


class ShapeCapabilityError(ShapeError):
    pass


class ShapeValidationError(ShapeError):
    pass


class ShapeSerializationError(ShapeError):
    pass


class ShapeDeserializationError(ShapeError):
    pass


class ShapeCompatibilityError(ShapeError):
    pass


class ShapeDependencyError(ShapeError):
    def __init__(self, shape_name: str, dependency: str, extra: str) -> None:
        super().__init__(
            f'The "{shape_name}" Asyncz Shape requires the optional "{dependency}" dependency. '
            f'Install it with: pip install "asyncz[{extra}]"'
        )


class ShapeMigrationError(ShapeError):
    pass
