import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, tzinfo
from typing import Any, Optional, Union, cast
from uuid import uuid4

from pydantic import Field

from asyncz.datastructures import TaskState
from asyncz.schedulers.types import SchedulerType
from asyncz.state import BaseState
from asyncz.tasks.types import DecoratedFn, TaskType
from asyncz.triggers.types import TriggerType
from asyncz.utils import (
    check_callable_args,
    datetime_repr,
    get_callable_name,
    obj_to_ref,
    ref_to_obj,
    to_datetime,
)

object_setattr = object.__setattr__


class Task(BaseState, TaskType):  # type: ignore
    """
    Contains the options given when scheduling callables and its current schedule and other state.
    This class should never be instantiated by the user.

    Args:

        id: The unique identifier of this task.
        name: The description of this task.
        fn: The callable to execute.
        args: Positional arguments to the callable.
        kwargs: Keyword arguments to the callable.
        coalesce: Whether to only run the task once when several run times are due.
        trigger: The trigger object that controls the schedule of this task.
        executor: The name of the executor that will run this task.
        mistrigger_grace_time: The time (in seconds) how much this task's execution is allowed to
            be late (`None` means "allow the task to run no matter how late it is").
        max_instances: The maximum number of concurrently executing instances allowed for this
            task.
        next_run_time: The next scheduled run time of this task.
    """

    fn_reference: Optional[str] = None
    args: Sequence[Any] = ()
    kwargs: dict[str, Any] = Field(default_factory=dict)

    def __init__(
        self,
        fn: Union[Callable[..., Any], str, None] = None,
        *,
        id: Optional[str] = None,
        **kwargs: Any,
    ):
        if id is None and fn is not None:
            id = uuid4().hex
        super().__init__(id=id, **kwargs)
        self.update_task(fn=fn, **kwargs)

    def get_run_times(self, timezone: tzinfo, now: datetime) -> list[datetime]:
        """
        Computes the scheduled run times `next_run_time` and `now`, inclusive.
        """
        run_times = []
        next_run_time = self.next_run_time
        assert self.trigger
        while next_run_time and next_run_time <= now:
            run_times.append(next_run_time)
            next_run_time = self.trigger.get_next_trigger_time(timezone, next_run_time, now)
        return run_times

    def update_task(  # type: ignore
        self,
        *,
        fn: Union[Callable[..., Any], str, None] = None,
        scheduler: Optional[SchedulerType] = None,
        **updates: Any,
    ) -> None:
        """
        Validates the updates to the Task and makes the modifications if and only if all of them
        validate.
        """
        approved: dict[str, Any] = {}
        if scheduler is not None:
            if self.scheduler is not None and self.scheduler is not scheduler:
                raise ValueError("The task scheduler may not be changed.")
            approved["scheduler"] = scheduler
        else:
            scheduler = self.scheduler

        if "id" in updates:
            raise ValueError("The task ID may not be changed.")

        if fn or "args" in updates or "kwargs" in updates:
            if not fn:
                fn = self.fn
            args = updates.pop("args") if "args" in updates else self.args
            kwargs = updates.pop("kwargs") if "kwargs" in updates else self.kwargs

            if fn is None:
                fn_reference = None
            elif isinstance(fn, str):
                fn_reference = fn
                fn = ref_to_obj(fn)
            elif callable(fn):
                try:
                    fn_reference = obj_to_ref(fn)
                except ValueError:
                    fn_reference = None
            else:
                raise TypeError("fn must be a callable or a textual reference to a callable.")

            if fn is not None and not getattr(self, "name", None) and updates.get("name") is None:
                updates["name"] = get_callable_name(cast(Callable[..., Any], fn))

            if isinstance(args, str) or not isinstance(args, Iterable):
                raise TypeError("args must be a non-string iterable.")
            if isinstance(kwargs, str) or not isinstance(kwargs, Mapping):
                raise TypeError("kwargs must be a dict-like object.")

            if fn is not None:
                check_callable_args(cast(Callable[..., Any], fn), args, kwargs)

            approved["fn"] = fn
            approved["fn_reference"] = fn_reference
            approved["args"] = args
            approved["kwargs"] = kwargs

        if updates.get("name") is not None:
            name = updates.pop("name")
            if not name or not isinstance(name, str):
                raise TypeError("name must be a non empty string.")
            approved["name"] = name
        else:
            # pop Nones
            updates.pop("name", None)

        if "mistrigger_grace_time" in updates:
            mistrigger_grace_time = updates.pop("mistrigger_grace_time")
            if mistrigger_grace_time is not None and (
                not isinstance(mistrigger_grace_time, (float, int)) or mistrigger_grace_time <= 0
            ):
                raise TypeError(
                    "mistrigger_grace_time must be either None or a positive float/integer."
                )
            approved["mistrigger_grace_time"] = mistrigger_grace_time

        if "coalesce" in updates:
            coalesce = bool(updates.pop("coalesce"))
            approved["coalesce"] = coalesce

        if "store_alias" in updates:
            store_alias = updates.pop("store_alias")
            if not isinstance(store_alias, str):
                raise TypeError("store_alias must be a string.")
            approved["store_alias"] = store_alias

        if "max_instances" in updates:
            max_instances = updates.pop("max_instances")
            if not isinstance(max_instances, int) or max_instances <= 0:
                raise TypeError("max_instances must be a positive integer.")
            approved["max_instances"] = max_instances

        if "trigger" in updates:
            trigger = updates.pop("trigger")
            if not isinstance(trigger, TriggerType):
                raise TypeError(
                    f"Expected a trigger instance, got {trigger.__class__.__name__} instead."
                )
            approved["trigger"] = trigger

        if "executor" in updates:
            executor = updates.pop("executor")
            if not isinstance(executor, str):
                raise TypeError("executor must be a string.")
            approved["executor"] = executor

        if "next_run_time" in updates:
            if not isinstance(scheduler, SchedulerType):
                raise TypeError("Cannot set next_run_time without scheduler.")

            next_run_time = updates.pop("next_run_time")
            approved["next_run_time"] = to_datetime(
                next_run_time, scheduler.timezone, "next_run_time"
            )

        if updates:
            raise AttributeError(
                f"The following are not modifiable attributes of Task: {', '.join(updates)}."
            )

        for key, value in approved.items():
            setattr(self, key, value)

    def __setstate__(self, state: "TaskState") -> "Task":  # type: ignore
        object_setattr(self, "__dict__", state.__dict__)
        object_setattr(self, "__pydantic_fields_set__", state.__pydantic_fields_set__)
        object_setattr(self, "__pydantic_extra__", state.__pydantic_extra__)
        state.model_config.update(self.model_config)

        for name, value in self.__dict__.items():
            if name == "fn":
                self.__dict__[name] = ref_to_obj(value)
        # the task was serialized in a store, so it is active
        self.submitted = True
        self.pending = False
        return self

    def __getstate__(self) -> "TaskState":  # type: ignore
        if not self.fn_reference:
            raise ValueError(
                f"This Task cannot be serialized since the reference to its callable ({self.fn!r}) could not "
                "be determined. Consider giving a textual reference (module:function name) "
                "instead."
            )

        fn = self.fn
        if (
            inspect.ismethod(fn)
            and not inspect.isclass(fn.__self__)
            and obj_to_ref(fn) == self.fn_reference
        ):
            args = (fn.__self__, *self.args)
        else:
            args = tuple(self.args)

        task_state = TaskState(
            id=self.id,
            fn=self.fn_reference,
            trigger=self.trigger,
            executor=self.executor,
            args=args,
            kwargs=self.kwargs if self.kwargs else {},
            name=self.name,
            mistrigger_grace_time=self.mistrigger_grace_time,
            coalesce=self.coalesce,
            max_instances=self.max_instances,
            next_run_time=self.next_run_time,
            fn_reference=self.fn_reference,
        )
        return task_state

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Task):
            if self.id is None:
                return False
            return self.id == other.id
        return NotImplemented

    def __repr__(self) -> str:
        return f"<Task (id={self.id} name={self.name})>"

    def __str__(self) -> str:
        if not self.pending:
            status = (
                "next run at: " + datetime_repr(self.next_run_time)
                if self.next_run_time
                else "paused"
            )
        else:
            status = "pending"

        return f"{self.name} (trigger: {self.trigger}, {status})"

    def __call__(self, fn: DecoratedFn) -> DecoratedFn:
        new_dict: dict[str, Any] = dict(self.__dict__)
        new_dict.pop("pending", None)
        new_dict.pop("submitted", None)
        new_dict.pop("fn_reference", None)
        new_dict["fn"] = fn
        if new_dict["store_alias"] is None:
            del new_dict["store_alias"]
        if new_dict["executor"] is None:
            del new_dict["executor"]
        replace_existing = True
        if not new_dict.get("id"):
            replace_existing = False
            new_dict["id"] = uuid4().hex

        task = self.__class__(**new_dict)
        scheduler = self.scheduler
        if scheduler is not None:
            # in decorator mode tasks are simply started
            scheduler.add_task(task, replace_existing=replace_existing)
        if not replace_existing:
            if not hasattr(fn, "asyncz_tasks"):
                object_setattr(fn, "asyncz_tasks", [])
            fn.asyncz_tasks.append(task)
        return fn
