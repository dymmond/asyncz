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
    mistrigger_grace_time: float = 7
    coalesce: bool = False
    max_instances: int = 3


def test_top_level_asyncz_alias_uses_default_pydantic_shape():
    scheduler = Asyncz()

    assert isinstance(scheduler, AsyncIOScheduler)
    assert isinstance(scheduler.shape, PydanticShape)
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 1.0,
        "coalesce": True,
        "max_instances": 1,
    }


def test_scheduler_accepts_registered_shape_name_for_configuration():
    scheduler = AsyncIOScheduler(shape="dataclass", task_defaults=DataclassDefaults())

    assert isinstance(scheduler.shape, DataclassShape)
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 7.0,
        "coalesce": False,
        "max_instances": 3,
    }


def test_scheduler_accepts_shape_instance():
    shape = AnyShape()
    scheduler = AsyncIOScheduler(shape=shape, task_defaults={"max_instances": "4"})

    assert scheduler.shape is shape
    assert scheduler.task_defaults.model_dump() == {
        "mistrigger_grace_time": 1.0,
        "coalesce": True,
        "max_instances": 4,
    }


def test_shape_registry_is_deterministic_and_rejects_duplicates():
    class CompanyShape(AnyShape):
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
    with pytest.raises(ShapeNotFoundError):
        ShapeRegistry.get("does-not-exist")


def test_dataclass_shape_contract_round_trip():
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
