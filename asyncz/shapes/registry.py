from __future__ import annotations

from inspect import isclass
from typing import Any

from asyncz.shapes.base import Shape
from asyncz.shapes.errors import ShapeError, ShapeNotFoundError, ShapeRegistrationError


class ShapeRegistry:
    """
    Canonical process-local registry for Asyncz Shape implementations.

    The registry is the single owner of Shape name resolution. Built-in and
    custom Shapes use the same registration path so scheduler configuration and
    persisted Shape identifiers remain deterministic.
    """

    _registry: dict[str, type[Shape]] = {}

    @classmethod
    def register(cls, name: str, shape: type[Shape], *, replace: bool = False) -> type[Shape]:
        """
        Register a Shape class under a stable name.

        Duplicate names are rejected unless `replace` is explicit. This prevents
        import order from silently changing how schedulers validate and restore
        persisted data.
        """

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
        """
        Remove a Shape registration by name.

        This is primarily useful in tests and controlled application startup
        flows. Unknown names fail clearly so callers do not assume a cleanup
        happened when it did not.
        """

        try:
            del cls._registry[name]
        except KeyError:
            raise ShapeNotFoundError(name) from None

    @classmethod
    def get(cls, name: str) -> Shape:
        """
        Return a new Shape instance for a registered name.

        Shape instances are created on demand so implementations can remain
        stateless and scheduler-specific context stays outside the registry.
        """

        try:
            shape_class = cls._registry[name]
        except KeyError:
            raise ShapeNotFoundError(name) from None
        return shape_class()

    @classmethod
    def available(cls) -> tuple[str, ...]:
        """
        Return registered Shape names in deterministic order.

        Sorted output is useful for diagnostics, documentation, and tests where
        import order should not affect visible registry state.
        """

        return tuple(sorted(cls._registry))

    @classmethod
    def resolve(cls, shape: str | type[Shape] | Shape | None) -> Shape:
        """
        Resolve scheduler configuration into a Shape instance.

        Accepted inputs are `None`, a registered name, a Shape class, or a Shape
        instance. Anything else is rejected instead of being coerced into an
        ambiguous representation boundary.
        """

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
    """
    Resolve a Shape selection through the canonical registry.

    This convenience function is the public helper used by schedulers, stores,
    and applications that need the same deterministic resolution behavior.
    """

    return ShapeRegistry.resolve(shape)


def register_shape(name: str, *, replace: bool = False) -> Any:
    """
    Create a decorator for registering custom Shape classes.

    The decorator keeps registration close to the custom class definition while
    still using the same duplicate-name policy as direct registry calls.
    """

    def decorator(shape: type[Shape]) -> type[Shape]:
        """
        Register the decorated Shape and return it unchanged.

        Returning the original class preserves normal class usage, inheritance,
        and testing patterns after registration.
        """

        return ShapeRegistry.register(name, shape, replace=replace)

    return decorator
