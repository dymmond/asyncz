from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from inspect import isclass
from typing import Any, ClassVar

from asyncz.shapes.errors import (
    ShapeCapabilityError,
    ShapeDeserializationError,
    ShapeSerializationError,
    ShapeValidationError,
)


@dataclass(frozen=True)
class ShapeContext:
    """
    Scheduler-owned context for representation operations.

    Shapes receive only representation metadata, not scheduler internals. This keeps
    validation and serialization separate from task execution and scheduling decisions.
    """

    entity: str
    operation: str
    scheduler_identity: str | None = None
    strict: bool | None = None
    schema_version: int | None = None
    mode: str | None = None


@dataclass(frozen=True)
class ShapeField:
    name: str
    annotation: Any = Any
    default: Any = None
    required: bool = True


def dump_plain(value: Any, *, exclude_none: bool = False) -> Any:
    """
    Dump common Python objects into scheduler-safe builtins when possible.
    """

    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=exclude_none)

    if dataclasses.is_dataclass(value) and not isclass(value):
        return {
            field.name: dump_plain(getattr(value, field.name), exclude_none=exclude_none)
            for field in dataclasses.fields(value)
            if not exclude_none or getattr(value, field.name) is not None
        }

    try:
        import attr
    except ImportError:
        attr = None  # type: ignore[assignment]

    if attr is not None and attr.has(value.__class__):
        return {
            key: dump_plain(item, exclude_none=exclude_none)
            for key, item in attr.asdict(value, recurse=False).items()
            if not exclude_none or item is not None
        }

    if isinstance(value, Mapping):
        return {
            key: dump_plain(item, exclude_none=exclude_none)
            for key, item in value.items()
            if not exclude_none or item is not None
        }

    if isinstance(value, tuple):
        return tuple(dump_plain(item, exclude_none=exclude_none) for item in value)

    if isinstance(value, list):
        return [dump_plain(item, exclude_none=exclude_none) for item in value]

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dump_plain(item, exclude_none=exclude_none) for item in value]

    return value


class Shape:
    """
    Asyncz-owned contract for validation and representation mechanics.

    A Shape may validate, construct, dump, restore, inspect, and optionally expose
    schemas for scheduler-facing values. It must not own scheduling behavior.
    """

    name: ClassVar[str] = "shape"
    version: ClassVar[int] = 1

    def supports(self, value_or_type: Any) -> bool:
        return False

    def validate(
        self, model_type: type[Any], value: Any, *, context: ShapeContext | None = None
    ) -> Any:
        return self.construct(model_type, value, context=context)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        if isinstance(values, model_type):
            return values
        if isinstance(values, Mapping):
            try:
                return model_type(**values)
            except Exception as exc:
                raise ShapeValidationError(
                    f'Shape "{self.name}" could not construct {model_type.__name__}.'
                ) from exc
        raise ShapeValidationError(
            f'Shape "{self.name}" expected a mapping or {model_type.__name__} instance.'
        )

    def dump(
        self,
        value: Any,
        *,
        mode: str | None = None,
        context: ShapeContext | None = None,
        exclude_none: bool = False,
    ) -> Any:
        try:
            return dump_plain(value, exclude_none=exclude_none)
        except Exception as exc:
            raise ShapeSerializationError(f'Shape "{self.name}" could not dump value.') from exc

    def load(
        self, model_type: type[Any], value: Any, *, context: ShapeContext | None = None
    ) -> Any:
        try:
            return self.construct(model_type, value, context=context)
        except ShapeValidationError as exc:
            raise ShapeDeserializationError(str(exc)) from exc

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        raise ShapeCapabilityError(f'Shape "{self.name}" does not expose field inspection.')

    def schema(self, model_type: type[Any], *, context: ShapeContext | None = None) -> Any:
        raise ShapeCapabilityError(f'Shape "{self.name}" does not expose schema generation.')
