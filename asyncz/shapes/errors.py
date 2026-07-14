from __future__ import annotations

from asyncz.exceptions import AsynczException


class ShapeError(AsynczException):
    """
    Base error for Asyncz Shape operations.

    Shape errors are raised at representation boundaries where Asyncz asks a
    Shape to validate, dump, restore, inspect, or describe scheduler-facing
    values.
    """


class ShapeNotFoundError(ShapeError):
    """
    Raised when a configured Shape name is not registered.

    This error is intentionally explicit so Asyncz never falls back to another
    validator silently when persisted data or scheduler configuration names a
    missing Shape.
    """

    def __init__(self, name: str) -> None:
        """
        Build an unknown-Shape error for the provided registry name.

        The registry name is preserved in the message because users normally
        fix this by installing an optional dependency or registering a custom
        Shape during process startup.
        """

        super().__init__(f"Unknown Asyncz Shape '{name}'.")


class ShapeRegistrationError(ShapeError):
    """
    Raised when Shape registration would make resolution ambiguous.

    Typical causes are empty names, non-Shape classes, or duplicate
    registrations without an explicit replacement request.
    """


class ShapeCapabilityError(ShapeError):
    """
    Raised when a Shape does not support an optional capability.

    Optional operations such as schema generation and field inspection must fail
    clearly instead of pretending every validation library can provide the same
    information.
    """


class ShapeValidationError(ShapeError):
    """
    Raised when a Shape cannot validate or construct a scheduler-facing value.

    The original validator exception should remain attached as the cause when a
    third-party library provides useful path or field-level detail.
    """


class ShapeSerializationError(ShapeError):
    """
    Raised when a Shape cannot dump a value for transport or persistence.

    Serialization failures are kept separate from validation failures so stores
    and operators can tell whether input was invalid or an existing value could
    not be represented safely.
    """


class ShapeDeserializationError(ShapeError):
    """
    Raised when a Shape cannot restore a value from a stored representation.

    This is used at persistence and transport boundaries where Asyncz has
    already accepted a payload but cannot reconstruct the expected runtime
    object.
    """


class ShapeCompatibilityError(ShapeError):
    """
    Raised when a Shape cannot honor a requested compatibility contract.

    Compatibility errors are reserved for cases where a representation is
    structurally valid but cannot be used with the selected Asyncz or Shape
    version.
    """


class ShapeDependencyError(ShapeError):
    """
    Raised when a built-in optional Shape is selected without its dependency.

    The message includes the exact Asyncz extra so users get an actionable
    installation command instead of a raw import error from the validator
    library.
    """

    def __init__(self, shape_name: str, dependency: str, extra: str) -> None:
        """
        Build a dependency error for an unavailable built-in Shape.

        The `extra` argument is the Asyncz optional dependency group that should
        be installed to make the selected Shape usable.
        """

        super().__init__(
            f'The "{shape_name}" Asyncz Shape requires the optional "{dependency}" dependency. '
            f'Install it with: pip install "asyncz[{extra}]"'
        )


class ShapeMigrationError(ShapeError):
    """
    Raised when persisted Shape data cannot be migrated or accepted.

    Migration errors protect stores from silently loading unsupported entity
    names, envelope versions, or record formats.
    """
