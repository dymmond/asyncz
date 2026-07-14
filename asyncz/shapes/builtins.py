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
    name = "pydantic"

    def supports(self, value_or_type: Any) -> bool:
        try:
            from pydantic import BaseModel
        except ImportError:
            return False

        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return isclass(candidate) and issubclass(candidate, BaseModel)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
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
        if self.supports(model_type) and hasattr(model_type, "model_json_schema"):
            return model_type.model_json_schema()
        return super().schema(model_type, context=context)


class DataclassShape(Shape):
    name = "dataclass"

    def supports(self, value_or_type: Any) -> bool:
        return dataclasses.is_dataclass(value_or_type)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
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
    name = "attrs"

    def _attrs(self) -> Any:
        try:
            import attr
        except ImportError as exc:
            raise ShapeDependencyError(self.name, "attrs", "attrs") from exc
        return attr

    def supports(self, value_or_type: Any) -> bool:
        try:
            attr = self._attrs()
        except ShapeDependencyError:
            return False
        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return attr.has(candidate)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
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
    name = "msgspec"

    def _msgspec(self) -> Any:
        try:
            import msgspec
        except ImportError as exc:
            raise ShapeDependencyError(self.name, "msgspec", "msgspec") from exc
        return msgspec

    def supports(self, value_or_type: Any) -> bool:
        try:
            msgspec = self._msgspec()
        except ShapeDependencyError:
            return False
        candidate = value_or_type if isclass(value_or_type) else value_or_type.__class__
        return isclass(candidate) and issubclass(candidate, msgspec.Struct)

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
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
        msgspec = self._msgspec()
        if not self.supports(model_type):
            return super().schema(model_type, context=context)
        return msgspec.json.schema(model_type)


class AnyShape(Shape):
    name = "any"

    def supports(self, value_or_type: Any) -> bool:
        return True

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
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
        raise ShapeCapabilityError('Shape "any" intentionally does not expose schemas.')
