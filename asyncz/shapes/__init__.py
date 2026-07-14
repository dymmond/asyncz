from __future__ import annotations

from asyncz.shapes.base import Shape, ShapeContext, ShapeField
from asyncz.shapes.builtins import (
    AnyShape,
    AttrsShape,
    DataclassShape,
    MsgspecShape,
    PydanticShape,
)
from asyncz.shapes.errors import (
    ShapeCapabilityError,
    ShapeCompatibilityError,
    ShapeDependencyError,
    ShapeDeserializationError,
    ShapeError,
    ShapeMigrationError,
    ShapeNotFoundError,
    ShapeRegistrationError,
    ShapeSerializationError,
    ShapeValidationError,
)
from asyncz.shapes.registry import ShapeRegistry, register_shape, resolve_shape, shapes

ShapeRegistry.register("pydantic", PydanticShape, replace=True)
ShapeRegistry.register("msgspec", MsgspecShape, replace=True)
ShapeRegistry.register("attrs", AttrsShape, replace=True)
ShapeRegistry.register("dataclass", DataclassShape, replace=True)
ShapeRegistry.register("any", AnyShape, replace=True)

__all__ = [
    "AnyShape",
    "AttrsShape",
    "DataclassShape",
    "MsgspecShape",
    "PydanticShape",
    "Shape",
    "ShapeCapabilityError",
    "ShapeCompatibilityError",
    "ShapeContext",
    "ShapeDependencyError",
    "ShapeDeserializationError",
    "ShapeError",
    "ShapeField",
    "ShapeMigrationError",
    "ShapeNotFoundError",
    "ShapeRegistrationError",
    "ShapeRegistry",
    "ShapeSerializationError",
    "ShapeValidationError",
    "register_shape",
    "resolve_shape",
    "shapes",
]
