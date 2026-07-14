# Asyncz Shapes

Asyncz Shapes make scheduler-facing representation validator-agnostic without
moving scheduler behavior into a validation library.

A Shape owns representation mechanics:

- validation and construction of scheduler-facing values;
- dumping values for configuration, diagnostics, or persistence boundaries;
- restoring values from stored representations;
- field inspection where the underlying library supports it;
- optional schema generation;
- translation of library-specific errors into Asyncz Shape errors.

A Shape does not own scheduling semantics. Triggers still calculate run times,
stores still own persistence and locking, executors still run tasks, and the
scheduler still owns lifecycle, misfire handling, coalescing, task acquisition,
events, and state transitions.

Pydantic remains the default Shape so existing installations continue to feel
familiar:

```python
from asyncz import Asyncz

scheduler = Asyncz()
```

You can select a Shape explicitly:

```python
from asyncz import Asyncz
from asyncz.shapes import DataclassShape

scheduler = Asyncz(shape=DataclassShape())
```

Or by registered name:

```python
from asyncz import Asyncz

scheduler = Asyncz(shape="dataclass")
```

## Built-in Shapes

| Shape | Name | Dependency | Notes |
| ----- | ---- | ---------- | ----- |
| `PydanticShape` | `pydantic` | default install | Default behavior and best compatibility with existing Asyncz usage |
| `DataclassShape` | `dataclass` | standard library | Construction and field inspection for dataclasses; no Pydantic-equivalent runtime validation |
| `AttrsShape` | `attrs` | `asyncz[attrs]` | Uses public attrs APIs, validators, converters, factories, and field metadata |
| `MsgspecShape` | `msgspec` | `asyncz[msgspec]` | Uses msgspec conversion, builtins dumping, Struct fields, and JSON schema support |
| `AnyShape` | `any` | default install | Opt-in permissive mode for trusted values with weak validation and no schema support |

Install optional Shapes with:

```bash
pip install "asyncz[attrs]"
pip install "asyncz[msgspec]"
pip install "asyncz[all-shapes]"
```

Selecting a Shape whose dependency is missing raises `ShapeDependencyError` with
the exact extra to install. Asyncz does not silently fall back to Pydantic or
`AnyShape`.

## Quick Start

Default Pydantic behavior needs no configuration:

```python
from asyncz import Asyncz

scheduler = Asyncz()
```

Dataclass-backed configuration:

```python
from dataclasses import dataclass

from asyncz import Asyncz


@dataclass
class TaskDefaults:
    mistrigger_grace_time: float = 5
    coalesce: bool = False
    max_instances: int = 3


scheduler = Asyncz(shape="dataclass", task_defaults=TaskDefaults())
```

Attrs-backed configuration:

```python
import attr

from asyncz import Asyncz


@attr.define
class TaskDefaults:
    mistrigger_grace_time: float = 5
    coalesce: bool = False
    max_instances: int = 3


scheduler = Asyncz(shape="attrs", task_defaults=TaskDefaults())
```

Msgspec-backed configuration:

```python
import msgspec

from asyncz import Asyncz


class TaskDefaults(msgspec.Struct):
    mistrigger_grace_time: float = 5
    coalesce: bool = False
    max_instances: int = 3


scheduler = Asyncz(shape="msgspec", task_defaults=TaskDefaults())
```

Permissive trusted configuration:

```python
from asyncz import Asyncz

scheduler = Asyncz(shape="any", task_defaults={"max_instances": "4"})
```

Check the active Shape:

```python
assert scheduler.shape.name == "pydantic"
```

## Registry

`ShapeRegistry` is the canonical registry owner. It supports deterministic
registration, lookup, duplicate rejection, replacement, unregistering, and
introspection:

```python
from asyncz.shapes import AnyShape, ShapeRegistry


class CompanyShape(AnyShape):
    """
    Company-specific Shape for trusted internal scheduler configuration.

    Production implementations usually override construction, dumping, loading,
    and error translation instead of inheriting all permissive behavior.
    """

    name = "company"


ShapeRegistry.register("company", CompanyShape)
assert ShapeRegistry.available()

scheduler = Asyncz(shape="company")
```

You can also use the decorator helper:

```python
from asyncz.shapes import Shape, register_shape


@register_shape("company")
class CompanyShape(Shape):
    """
    Company-specific Shape registered during application startup.

    The decorated class is returned unchanged, so tests and subclasses can use
    it normally after registration.
    """
```

Duplicate names fail unless `replace=True` is explicit. This prevents import
order from changing Shape resolution.

## Custom Shape Contract

Subclass `Shape` and implement only the capabilities your application needs.

```python
from collections.abc import Mapping
from typing import Any

from asyncz.shapes import (
    Shape,
    ShapeCapabilityError,
    ShapeContext,
    ShapeField,
    ShapeRegistry,
    ShapeValidationError,
)


class CompanyShape(Shape):
    """
    Example custom Shape using ordinary Python model classes.

    It validates mapping inputs, constructs model instances, dumps public
    attributes, and reports field metadata for classes that declare
    `__annotations__`.
    """

    name = "company"

    def supports(self, value_or_type: Any) -> bool:
        """
        Return whether the object follows the company model convention.

        The convention here is deliberately small: supported classes declare a
        `__company_shape__` marker attribute.
        """

        candidate = value_or_type if isinstance(value_or_type, type) else type(value_or_type)
        return bool(getattr(candidate, "__company_shape__", False))

    def construct(
        self, model_type: type[Any], values: Any, *, context: ShapeContext | None = None
    ) -> Any:
        """
        Build a company model from a mapping or return an existing instance.

        Real implementations can add stricter validation, nested conversion,
        and application-specific error messages here.
        """

        if isinstance(values, model_type):
            return values
        if not isinstance(values, Mapping):
            raise ShapeValidationError("CompanyShape expects a mapping.")
        try:
            return model_type(**values)
        except Exception as exc:
            raise ShapeValidationError("CompanyShape could not construct the model.") from exc

    def dump(
        self,
        value: Any,
        *,
        mode: str | None = None,
        context: ShapeContext | None = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """
        Dump public attributes from a company model.

        Private attributes are not included, and `None` values can be removed
        when Asyncz asks for a compact representation.
        """

        data = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        if exclude_none:
            return {key: item for key, item in data.items() if item is not None}
        return data

    def fields(
        self, model_type: type[Any], *, context: ShapeContext | None = None
    ) -> tuple[ShapeField, ...]:
        """
        Return field metadata for annotated company models.

        Classes without annotations do not have enough metadata for stable field
        inspection, so they fail with an explicit capability error.
        """

        annotations = getattr(model_type, "__annotations__", None)
        if not annotations:
            raise ShapeCapabilityError("CompanyShape requires annotations for fields.")
        return tuple(
            ShapeField(name=name, annotation=annotation)
            for name, annotation in annotations.items()
        )


ShapeRegistry.register("company", CompanyShape)
```

Custom Shapes should be stateless or safe to share across scheduler operations.
When a Shape wraps a third-party library, raise Asyncz Shape errors and keep the
original exception as the cause:

```python
raise ShapeValidationError("Could not validate company task defaults.") from exc
```

## Persistence

Durable stores persist a versioned task-state envelope. The envelope records:

- entity kind, currently `task_state`;
- representation version;
- selected Shape name;
- Asyncz's native task-state payload.

Existing raw `TaskState` pickle records are still accepted for compatibility.
New records include Shape metadata so future migrations can fail clearly instead
of guessing which representation wrote a record.

Store encryption remains a store concern. If `ASYNCZ_STORE_ENCRYPTION_KEY` is
set, the serialized envelope bytes are encrypted after the Shape boundary.

Unknown Shape names and unsupported envelope versions fail explicitly. Asyncz
does not import arbitrary application model paths from persisted records.

## Migration Notes

Existing users can keep constructing schedulers exactly as before. Pydantic is
still installed by default and remains the default Shape.

Compatibility preserved in this release:

- `AsyncIOScheduler()` and `NativeAsyncIOScheduler()` default behavior;
- Pydantic-style `task_defaults.model_dump()` for existing callers;
- legacy raw `TaskState` records in durable stores;
- existing task, trigger, executor, event, CLI, and dashboard scheduling behavior.

New behavior:

- `from asyncz import Asyncz` is an alias for `AsyncIOScheduler`;
- schedulers accept `shape=...`;
- built-in Shape names can be resolved through `ShapeRegistry`;
- new durable task records include a versioned Shape envelope.

Do not use `AnyShape` for untrusted input. It is intentionally permissive and
pushes validation responsibility to application code.

## Error Handling

Shape errors live in `asyncz.shapes`:

- `ShapeNotFoundError`
- `ShapeRegistrationError`
- `ShapeCapabilityError`
- `ShapeValidationError`
- `ShapeSerializationError`
- `ShapeDeserializationError`
- `ShapeCompatibilityError`
- `ShapeDependencyError`
- `ShapeMigrationError`

Each error identifies the representation boundary that failed. Third-party
validator exceptions are kept as causes where they contain useful detail.

## Testing Shapes

Application Shape tests should cover:

- construction from mappings and existing instances;
- invalid values and nested error paths;
- dump and load round trips;
- field inspection and schema capabilities;
- missing optional dependencies;
- durable store restart when the Shape is used by a scheduler;
- unknown Shape and incompatible version failures.

For scheduler behavior, assert outcomes rather than validator internals. Adding
or changing one Shape should not require branching in scheduler, trigger, store,
executor, or event logic.
