from __future__ import annotations

from inspect import isclass
from typing import Any

from asyncz.shapes.base import Shape
from asyncz.shapes.errors import ShapeError, ShapeNotFoundError, ShapeRegistrationError


class ShapeRegistry:
    """
    Canonical process-local registry for Asyncz Shape implementations.
    """

    _registry: dict[str, type[Shape]] = {}

    @classmethod
    def register(cls, name: str, shape: type[Shape], *, replace: bool = False) -> type[Shape]:
        if not isinstance(name, str) or not name:
            raise ShapeRegistrationError("Shape names must be non-empty strings.")
        if not isclass(shape) or not issubclass(shape, Shape):
            raise ShapeRegistrationError("Only Shape classes can be registered.")
        if name in cls._registry and not replace:
            raise ShapeRegistrationError(f'An Asyncz Shape named "{name}" is already registered.')
        cls._registry[name] = shape
        return shape

    @classmethod
    def unregister(cls, name: str) -> None:
        try:
            del cls._registry[name]
        except KeyError:
            raise ShapeNotFoundError(name) from None

    @classmethod
    def get(cls, name: str) -> Shape:
        try:
            shape_class = cls._registry[name]
        except KeyError:
            raise ShapeNotFoundError(name) from None
        return shape_class()

    @classmethod
    def available(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._registry))

    @classmethod
    def resolve(cls, shape: str | type[Shape] | Shape | None) -> Shape:
        if shape is None:
            return cls.get("pydantic")
        if isinstance(shape, Shape):
            return shape
        if isinstance(shape, str):
            return cls.get(shape)
        if isclass(shape) and issubclass(shape, Shape):
            return shape()
        raise ShapeError(
            "Shape must be None, a registered Shape name, a Shape class, or a Shape instance."
        )


shapes = ShapeRegistry()


def resolve_shape(shape: str | type[Shape] | Shape | None = None) -> Shape:
    return ShapeRegistry.resolve(shape)


def register_shape(name: str, *, replace: bool = False) -> Any:
    def decorator(shape: type[Shape]) -> type[Shape]:
        return ShapeRegistry.register(name, shape, replace=replace)

    return decorator
