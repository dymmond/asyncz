import inspect
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Optional
from uuid import uuid4

from asyncz.datastructures import TaskState
from asyncz.state import BaseStateExtra
from asyncz.triggers.base import BaseTrigger
from asyncz.typing import DictAny
from asyncz.utils import (
    check_callable_args,
    datetime_repr,
    get_callable_name,
    obj_to_ref,
    ref_to_obj,
    repr_escape,
    to_datetime,
)

object_setattr = object.__setattr__


class Task(BaseStateExtra):
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

    def __init__(
        self,
        scheduler: Any,
        id: Optional[str] = None,
        store_alias: Optional[str] = None,
        **kwargs: "DictAny",
    ):
        super().__init__(**kwargs)
        self.scheduler = scheduler
        self.store_alias = store_alias
        self._update(id=id or uuid4().hex, **kwargs)

    @property
    def pending(self):
        """
        Returns true if the referenced task is still waiting to be added to its designated task
        store.
        """
        return self.store_alias is None

    def update(self, **updates: "DictAny") -> "Task":
        """
        Makes the given updates to this jon and save it in the associated store.
        Accepted keyword args are the same as the class variables.
        """
        self.scheduler.update_task(self.id, self.store_alias, **updates)
        return self

    def reschedule(self, trigger, **trigger_args) -> "Task":
        """
        Shortcut for switching the trigger on this task.
        """
        self.scheduler.reschedule_task(self.id, self.store_alias, trigger, **trigger_args)
        return self

    def pause(self) -> "Task":
        """
        Temporarily suspenses the execution of a given task.
        """
        self.scheduler.pause_task(self.id, self.store_alias)

    def resume(self) -> "Task":
        """
        Resume the schedule of this task if previously paused.
        """
        self.scheduler.resume_task(self.id, self.store_alias)
        return self

    def delete(self) -> None:
        """
        Unschedules this task and removes it from its associated store.
        """
        self.scheduler.delete_task(self.id, self.store_alias)

    def get_run_times(self, now: datetime) -> List[datetime]:
        """
        Computes the scheduled run times `next_run_time` and `now`, inclusive.
        """
        run_times = []
        next_run_time = self.next_run_time
        while next_run_time and next_run_time <= now:
            run_times.append(next_run_time)
            next_run_time = self.trigger.get_next_trigger_time(next_run_time, now)
        return run_times

    def _update(self, **updates: "DictAny") -> None:
        """
        Validates the updates to the Task and makes the modifications if and only if all of them
        validate.
        """
        approved = {}
        if "id" in updates:
            _id = updates.pop("id")
            if not isinstance(_id, str):
                raise TypeError("Id must be a non empty string.")
            if hasattr(self, "id") and getattr(self, "id", None):
                raise ValueError("The task ID may not be changed.")
            approved["id"] = _id

        if "fn" in updates or "args" in updates or "kwargs" in updates:
            fn = updates.pop("fn") if "fn" in updates else self.fn
            args = updates.pop("args") if "args" in updates else self.args
            kwargs = updates.pop("kwargs") if "kwargs" in updates else self.kwargs

            if isinstance(fn, str):
                fn_reference = fn
                fn = ref_to_obj(fn)
            elif callable(fn):
                try:
                    fn_reference = obj_to_ref(fn)
                except ValueError:
                    fn_reference = None
            else:
                raise TypeError("fn must be a callable or a textual reference to a callable.")

            if not getattr(self, "name", None) and updates.get("name", None) is None:
                updates["name"] = get_callable_name(fn)

            if isinstance(args, str) or not isinstance(args, Iterable):
                raise TypeError("args must be a non-string iterable.")
            if isinstance(kwargs, str) or not isinstance(kwargs, Mapping):
                raise TypeError("kwargs must be a dict-like object.")

            check_callable_args(fn, args, kwargs)

            approved["fn"] = fn
            approved["fn_reference"] = fn_reference
            approved["args"] = args
            approved["kwargs"] = kwargs

        if "name" in updates:
            name = updates.pop("name")
            if not name or not isinstance(name, str):
                raise TypeError("name must be a non empty string.")
            approved["name"] = name

        if "mistrigger_grace_time" in updates:
            mistrigger_grace_time = updates.pop("mistrigger_grace_time")
            if mistrigger_grace_time is not None and (
                not isinstance(mistrigger_grace_time, int) or mistrigger_grace_time <= 0
            ):
                raise TypeError("mistrigger_grace_time must be either None or a positive integer.")
            approved["mistrigger_grace_time"] = mistrigger_grace_time

        if "coalesce" in updates:
            coalesce = bool(updates.pop("coalesce"))
            approved["coalesce"] = coalesce

        if "max_instances" in updates:
            max_instances = updates.pop("max_instances")
            if not isinstance(max_instances, int) or max_instances <= 0:
                raise TypeError("max_instances must be a positive integer.")
            approved["max_instances"] = max_instances

        if "trigger" in updates:
            trigger = updates.pop("trigger")
            if not isinstance(trigger, BaseTrigger):
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
            next_run_time = updates.pop("next_run_time")
            approved["next_run_time"] = to_datetime(
                next_run_time, self.scheduler.timezone, "next_run_time"
            )

        if updates:
            raise AttributeError(
                f"The following are not modifiable attributes of Task: {', '.join(updates)}."
            )

        for key, value in approved.items():
            setattr(self, key, value)

    def __setstate__(self, state):
        object_setattr(self, "__dict__", state.__dict__)
        object_setattr(self, "__fields_set__", state.__fields_set__)

        for name, value in self.__dict__.items():
            if name == "fn":
                self.__dict__[name] = ref_to_obj(value)

        for name, value in state.__private_attributes__.items():
            if name == "fn":
                value = ref_to_obj(value)
            object_setattr(self, name, value)
        return self

    def __getstate__(self) -> "TaskState":
        if not self.fn_reference:
            raise ValueError(
                "This Task cannot be serialized since the reference to its callable (%r) could not "
                "be determined. Consider giving a textual reference (module:function name) "
                "instead." % (self.func,)
            )

        fn = self.fn
        if (
            inspect.ismethod(fn)
            and not inspect.isclass(fn.__self__)
            and obj_to_ref(fn) == self.fn_reference
        ):
            args = (fn.__self__,) + tuple(self.args)
        else:
            args = self.args

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

    def __eq__(self, other):
        if isinstance(other, Task):
            return self.id == other.id
        return NotImplemented

    def __repr__(self):
        return f"<Task (id={repr_escape(self.id)} name={repr_escape(self.name)})>"

    def __str__(self):
        return repr_escape(self.__unicode__())

    def __unicode__(self):
        if hasattr(self, "next_run_time"):
            status = (
                "next run at: " + datetime_repr(self.next_run_time)
                if self.next_run_time
                else "paused"
            )
        else:
            status = "pending"

        return f"{self.name} (trigger: {self.trigger}, {status})"
