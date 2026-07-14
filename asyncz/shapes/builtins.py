from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from inspect import isclass
from typing import Any, get_type_hints

from asyncz.shapes.base import Shape, ShapeContext, ShapeField, dump_plain
from asyncz.shapes.errors import (
    ShapeCapabilityError,
    ShapeDependencyError,
    ShapeSerializationError,
    ShapeValidationError,
)


class PydanticShape(Shape):
    """
    Default Shape implementation backed by Pydantic public APIs.

    This Shape preserves the current default Asyncz experience while moving
    Pydantic-specific validation, dumping, field inspection, and schema
    generation behind the Asyncz Shape contract.
    """

    name = "pydantic"

    def supports(self, value_or_type: Any) -> bool:
        """
        Return whether the value or type is a Pydantic model.

        Import failures return `False` so optional dependency checks can be
        handled at explicit selection points rather than during incidental type
        probing.
        """

        try:
            from pydantic import BaseModel
        except ImportError:
            return False

        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return isclass(candidate) and issubclass(candidate, BaseModel)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Construct a model using Pydantic validation when applicable.

        Pydantic's native validation error is retained as the exception cause so
        callers still get the field-level detail they expect from the default
        Shape.
        """

        if isinstance(values, model_type):
            return values
        if self.supports(model_type):
            try:
                return model_type.model_validate(values)
            except Exception as exc:
                raise ShapeValidationError(
                    f'Shape "{self.name}" could not validate {model_type.__name__}.'
                ) from exc
        return super().construct(model_type, values, context=context)

    def dump(
        self,
        value: Any,
        *,
        mode: str | None = None,
        context: ShapeContext | None = None,
        exclude_none: bool = False,
    ) -> Any:
        """
        Dump Pydantic models with `model_dump` and fall back to plain dumping.

        The optional mode is passed to Pydantic when supported. Older compatible
        surfaces that do not accept the mode parameter still work through the
        fallback path.
        """

        if hasattr(value, "model_dump"):
            try:
                return value.model_dump(mode=mode or "python", exclude_none=exclude_none)
            except TypeError:
                return value.model_dump(exclude_none=exclude_none)
            except Exception as exc:
                raise ShapeSerializationError(
                    f'Shape "{self.name}" could not dump {value.__class__.__name__}.'
                ) from exc
        return super().dump(value, mode=mode, context=context, exclude_none=exclude_none)

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        """
        Expose Pydantic model field metadata as Asyncz Shape fields.

        The returned field objects intentionally hide Pydantic internals so
        scheduler and documentation code do not depend on validator-specific
        field classes.
        """

        if self.supports(model_type):
            result: list[ShapeField] = []
            for name, field in model_type.model_fields.items():
                required = field.is_required()
                default = None if required else field.default
                result.append(
                    ShapeField(
                        name=name,
                        annotation=field.annotation,
                        default=default,
                        required=required,
                    )
                )
            return tuple(result)
        return super().fields(model_type, context=context)

    def schema(self, model_type: type[Any], *, context: ShapeContext | None = None) -> Any:
        """
        Return Pydantic's JSON schema for supported model types.

        Schema generation stays optional at the Shape boundary because other
        supported libraries may expose different schema capabilities.
        """

        if self.supports(model_type) and hasattr(model_type, "model_json_schema"):
            return model_type.model_json_schema()
        return super().schema(model_type, context=context)


class DataclassShape(Shape):
    """
    Shape implementation for standard-library dataclasses.

    Dataclasses provide construction and field metadata, but they do not provide
    Pydantic-equivalent runtime validation. This Shape therefore keeps its
    behavior explicit and conservative.
    """

    name = "dataclass"

    def supports(self, value_or_type: Any) -> bool:
        """
        Return whether the value or type is a dataclass.

        The standard `dataclasses.is_dataclass` check supports both dataclass
        classes and dataclass instances, which is exactly what scheduler
        configuration needs.
        """

        return dataclasses.is_dataclass(value_or_type)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Construct a dataclass from a mapping or return an existing instance.

        The constructor may run user-defined `__post_init__` logic, but this
        Shape does not imply stronger validation than dataclasses actually
        provide.
        """

        if dataclasses.is_dataclass(model_type):
            if isinstance(values, model_type):
                return values
            if isinstance(values, Mapping):
                try:
                    return model_type(**values)
                except Exception as exc:
                    raise ShapeValidationError(
                        f'Shape "{self.name}" could not construct {model_type.__name__}.'
                    ) from exc
        return super().construct(model_type, values, context=context)

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        """
        Return dataclass field metadata as Asyncz Shape fields.

        Type hints are resolved with `get_type_hints` where possible so callers
        receive ordinary Python annotations rather than dataclass internals.
        """

        if not dataclasses.is_dataclass(model_type):
            return super().fields(model_type, context=context)
        hints = get_type_hints(model_type)
        result: list[ShapeField] = []
        for field in dataclasses.fields(model_type):
            required = (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            )
            default = None if required else field.default
            result.append(
                ShapeField(
                    name=field.name,
                    annotation=hints.get(field.name, Any),
                    default=default,
                    required=required,
                )
            )
        return tuple(result)


class AttrsShape(Shape):
    """
    Shape implementation for attrs classes.

    Attrs support remains optional. The Shape uses public attrs APIs for
    construction, conversion, validators, defaults, and field inspection when
    the dependency is installed.
    """

    name = "attrs"

    def _attrs(self) -> Any:
        """
        Import attrs or raise an actionable Asyncz dependency error.

        Keeping the import lazy lets the public registry expose the built-in
        Shape name without requiring attrs for users who never select it.
        """

        try:
            import attr
        except ImportError as exc:
            raise ShapeDependencyError(self.name, "attrs", "attrs") from exc
        return attr

    def supports(self, value_or_type: Any) -> bool:
        """
        Return whether attrs recognizes the value or type.

        Missing optional dependencies make support probing return `False`
        instead of leaking raw import errors during unrelated scheduler setup.
        """

        try:
            attr = self._attrs()
        except ShapeDependencyError:
            return False
        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return attr.has(candidate)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Construct an attrs class through its public initializer.

        Attrs validators and converters remain owned by attrs and run through
        the class constructor rather than being reimplemented by Asyncz.
        """

        attr = self._attrs()
        if attr.has(model_type):
            if isinstance(values, model_type):
                return values
            if isinstance(values, Mapping):
                try:
                    return model_type(**values)
                except Exception as exc:
                    raise ShapeValidationError(
                        f'Shape "{self.name}" could not construct {model_type.__name__}.'
                    ) from exc
        return super().construct(model_type, values, context=context)

    def dump(
        self,
        value: Any,
        *,
        mode: str | None = None,
        context: ShapeContext | None = None,
        exclude_none: bool = False,
    ) -> Any:
        """
        Dump attrs instances into plain mapping payloads.

        The operation uses `attr.asdict` without recursive attrs conversion and
        then lets Asyncz's plain dumper normalize nested values consistently.
        """

        attr = self._attrs()
        if attr.has(value.__class__):
            return {
                key: dump_plain(item, exclude_none=exclude_none)
                for key, item in attr.asdict(value, recurse=False).items()
                if not exclude_none or item is not None
            }
        return super().dump(value, mode=mode, context=context, exclude_none=exclude_none)

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        """
        Return attrs field metadata as Asyncz Shape fields.

        Requiredness is derived from attrs defaults so callers do not need to
        understand attrs-specific sentinel values.
        """

        attr = self._attrs()
        if not attr.has(model_type):
            return super().fields(model_type, context=context)
        return tuple(
            ShapeField(
                name=field.name,
                annotation=field.type,
                default=None if field.default is attr.NOTHING else field.default,
                required=field.default is attr.NOTHING,
            )
            for field in attr.fields(model_type)
        )


class MsgspecShape(Shape):
    """
    Shape implementation for `msgspec.Struct` models.

    Msgspec support is optional and uses msgspec conversion, builtins dumping,
    struct field inspection, and schema generation through public APIs.
    """

    name = "msgspec"

    def _msgspec(self) -> Any:
        """
        Import msgspec or raise an actionable Asyncz dependency error.

        Lazy importing allows Asyncz to expose the built-in registry entry while
        keeping msgspec optional for default Pydantic installations.
        """

        try:
            import msgspec
        except ImportError as exc:
            raise ShapeDependencyError(self.name, "msgspec", "msgspec") from exc
        return msgspec

    def supports(self, value_or_type: Any) -> bool:
        """
        Return whether the value or type is a msgspec Struct.

        Missing optional dependencies make support probing return `False`, while
        explicit use still raises `ShapeDependencyError` with install guidance.
        """

        try:
            msgspec = self._msgspec()
        except ShapeDependencyError:
            return False
        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return isclass(candidate) and issubclass(candidate, msgspec.Struct)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Construct msgspec Struct values through `msgspec.convert`.

        The conversion path preserves msgspec's validation and conversion
        behavior instead of translating Structs through another model system.
        """

        msgspec = self._msgspec()
        if self.supports(model_type):
            if isinstance(values, model_type):
                return values
            try:
                return msgspec.convert(values, type=model_type)
            except Exception as exc:
                raise ShapeValidationError(
                    f'Shape "{self.name}" could not convert {model_type.__name__}.'
                ) from exc
        return super().construct(model_type, values, context=context)

    def dump(
        self,
        value: Any,
        *,
        mode: str | None = None,
        context: ShapeContext | None = None,
        exclude_none: bool = False,
    ) -> Any:
        """
        Dump msgspec Struct instances into Python builtins.

        The returned payload is suitable for Asyncz persistence envelopes and
        transport boundaries that expect validator-independent values.
        """

        msgspec = self._msgspec()
        if self.supports(value):
            try:
                return msgspec.to_builtins(value)
            except Exception as exc:
                raise ShapeSerializationError(
                    f'Shape "{self.name}" could not dump {value.__class__.__name__}.'
                ) from exc
        return super().dump(value, mode=mode, context=context, exclude_none=exclude_none)

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        """
        Return msgspec Struct field metadata as Asyncz Shape fields.

        The projection preserves the field names, annotations, defaults, and
        requiredness that Asyncz tooling needs without exposing msgspec field
        objects directly.
        """

        msgspec = self._msgspec()
        if not self.supports(model_type):
            return super().fields(model_type, context=context)
        return tuple(
            ShapeField(
                name=field.name,
                annotation=field.type,
                default=field.default,
                required=field.required,
            )
            for field in msgspec.structs.fields(model_type)
        )

    def schema(self, model_type: type[Any], *, context: ShapeContext | None = None) -> Any:
        """
        Return msgspec's JSON schema for supported Struct models.

        This capability is optional at the Shape contract level and only exists
        when the msgspec dependency is installed.
        """

        msgspec = self._msgspec()
        if not self.supports(model_type):
            return super().schema(model_type, context=context)
        return msgspec.json.schema(model_type)


class AnyShape(Shape):
    """
    Explicitly permissive Shape for trusted Python values.

    This Shape is opt-in and intentionally does not imply strong validation or
    schema guarantees. It is useful for controlled internal boundaries where the
    application already owns validation.
    """

    name = "any"

    def supports(self, value_or_type: Any) -> bool:
        """
        Return `True` for every value or type.

        This broad support is safe only because `AnyShape` must be explicitly
        selected and is never used as a silent fallback for unknown Shapes.
        """

        return True

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Construct a Python object with minimal assumptions.

        The method accepts existing instances, mapping-based constructors, and
        single-value constructors. Failures are translated into Shape validation
        errors without adding stronger guarantees than the model type provides.
        """

        if model_type in (Any, object):
            return values
        if isinstance(values, model_type):
            return values
        if isinstance(values, Mapping):
            try:
                return model_type(**values)
            except Exception as exc:
                raise ShapeValidationError(
                    f'Shape "{self.name}" could not construct {model_type.__name__}.'
                ) from exc
        try:
            return model_type(values)
        except Exception as exc:
            raise ShapeValidationError(
                f'Shape "{self.name}" could not construct {model_type.__name__}.'
            ) from exc

    def schema(self, model_type: type[Any], *, context: ShapeContext | None = None) -> Any:
        """
        Reject schema generation for permissive values.

        `AnyShape` cannot honestly describe the structure of arbitrary trusted
        Python values, so schema access fails with an explicit capability error.
        """

        raise ShapeCapabilityError('Shape "any" intentionally does not expose schemas.')
