from __future__ import annotations

from dataclasses import dataclass

import pytest

from asyncz import Asyncz
from asyncz.schedulers import AsyncIOScheduler
from asyncz.shapes import (
    AnyShape,
    DataclassShape,
    PydanticShape,
    ShapeContext,
    ShapeNotFoundError,
    ShapeRegistrationError,
    ShapeRegistry,
    shapes,
)


@dataclass
class DataclassDefaults:
    """
    Test-only dataclass that mirrors scheduler task default configuration.

    It proves the scheduler can accept a non-Pydantic configuration object
    through the same Shape resolution path used by production code.
    """

    mistrigger_grace_time: float = 7
    coalesce: bool = False
    max_instances: int = 3


def test_top_level_asyncz_alias_uses_default_pydantic_shape():
    """
    Confirm the top-level `Asyncz` alias keeps the default Pydantic experience.

    The ordinary constructor should require no Shape configuration and should
    still expose task defaults through the compatibility `model_dump()` surface.
    """

    scheduler = Asyncz()

    assert isinstance(scheduler, AsyncIOScheduler)
    assert isinstance(scheduler.shape, PydanticShape)
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 1.0,
        "coalesce": True,
        "max_instances": 1,
    }


def test_scheduler_accepts_registered_shape_name_for_configuration():
    """
    Verify scheduler configuration can select a registered Shape by name.

    The dataclass defaults object exercises a non-Pydantic representation while
    still normalizing into Asyncz-owned task defaults.
    """

    scheduler = AsyncIOScheduler(shape="dataclass", task_defaults=DataclassDefaults())

    assert isinstance(scheduler.shape, DataclassShape)
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 7.0,
        "coalesce": False,
        "max_instances": 3,
    }


def test_scheduler_accepts_shape_instance():
    """
    Verify scheduler configuration accepts an already-instantiated Shape.

    This covers applications that want to configure Shape instances explicitly
    instead of relying on global registry lookup.
    """

    shape = AnyShape()
    scheduler = AsyncIOScheduler(shape=shape, task_defaults={"max_instances": "4"})

    assert scheduler.shape is shape
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 1.0,
        "coalesce": True,
        "max_instances": 4,
    }


def test_shape_registry_is_deterministic_and_rejects_duplicates():
    """
    Prove registry lookup is deterministic and duplicate names fail clearly.

    A custom test Shape is registered temporarily to ensure the public registry
    path works without relying on internal imports.
    """

    class CompanyShape(AnyShape):
        """
        Test-only custom Shape used to exercise public registry behavior.

        It inherits permissive behavior because this test is about registry
        ownership rather than validation semantics.
        """

        name = "company"

    ShapeRegistry.register("company-test", CompanyShape)
    try:
        assert isinstance(shapes.get("company-test"), CompanyShape)
        assert "company-test" in shapes.available()
        with pytest.raises(ShapeRegistrationError):
            ShapeRegistry.register("company-test", CompanyShape)
    finally:
        ShapeRegistry.unregister("company-test")


def test_shape_registry_reports_unknown_shapes():
    """
    Verify unknown Shape names fail instead of falling back silently.

    This protects scheduler configuration and persisted records from changing
    validator behavior because of missing registrations.
    """

    with pytest.raises(ShapeNotFoundError):
        ShapeRegistry.get("does-not-exist")


def test_dataclass_shape_contract_round_trip():
    """
    Exercise the dataclass Shape contract directly.

    The test covers construction, dumping, and field inspection so dataclasses
    prove the first non-Pydantic contract path without scheduler branching.
    """

    shape = DataclassShape()
    context = ShapeContext(entity="task_defaults", operation="round_trip")
    defaults = shape.construct(
        DataclassDefaults,
        {"mistrigger_grace_time": 2, "coalesce": False, "max_instances": 5},
        context=context,
    )

    assert defaults == DataclassDefaults(2, False, 5)
    assert shape.dump(defaults, context=context) == {
        "mistrigger_grace_time": 2,
        "coalesce": False,
        "max_instances": 5,
    }
    assert [field.name for field in shape.fields(DataclassDefaults)] == [
        "mistrigger_grace_time",
        "coalesce",
        "max_instances",
    ]
