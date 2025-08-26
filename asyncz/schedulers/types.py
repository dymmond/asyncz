from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Optional, Union

from asyncz.events.constants import (
    ALL_EVENTS,
)
from asyncz.typing import Undefined, undefined

if TYPE_CHECKING:
    from datetime import datetime
    from logging import Logger
    from threading import RLock

    from asyncz.events.base import SchedulerEvent
    from asyncz.executors.types import ExecutorType
    from asyncz.stores.types import StoreType
    from asyncz.tasks.types import TaskType
    from asyncz.triggers.types import TriggerType


class LoggersType(ABC):
    def __init__(self) -> None:
        self.data: dict[str, Logger] = {}

    @abstractmethod
    def __missing__(self, item: str) -> Logger: ...

    def __getitem__(self, item: str) -> Logger:
        if item not in self.data:
            self.data[item] = self.__missing__(item)
        return self.data[item]


class SchedulerType(ABC):
    event_loop: Any = None
    loggers: LoggersType
    instances: dict[str, int]

    @abstractmethod
    def start(self, paused: bool = False) -> Union[bool, Awaitable[bool]]:
        """
        Start the configured executors and task stores and begin processing scheduled tasks.

        Args:
            paused: If True don't start the process until resume is called.

        Return:
            bool: True when scheduler is really started
        """

    @abstractmethod
    def shutdown(self, wait: bool = True) -> Union[bool, Awaitable[bool]]:
        """
        Shuts down the scheduler, along with its executors and task stores.
        Does not interrupt any currently running tasks.

        Args:
            wait: True to wait until all currently executing tasks have finished.

        Return:
            bool: True when scheduler is terminated
        """

    @abstractmethod
    def pause(self) -> None:
        """
        Pause task processing in the scheduler.

        This will prevent the scheduler from waking up to do task processing until resume
        is called. It will not however stop any already running task processing.
        """

    @abstractmethod
    def resume(self) -> None:
        """
        Resume task processing in the scheduler.
        """

    @property
    @abstractmethod
    def running(self) -> bool:
        """
        Return True if the scheduler has been started. This is a shortcut
        for scheduler.state != SchedulerState.STATE_STOPPED.
        """

    @abstractmethod
    def add_executor(
        self, executor: Union[ExecutorType, str], alias: str = "default", **executor_options: Any
    ) -> None:
        """
        Add executor with the given alias to the scheduler
        """

    @abstractmethod
    def remove_executor(self, alias: str, shutdown: bool = True) -> None:
        """
        Removes the executor by the given alias from this scheduler.
        """

    @abstractmethod
    def add_store(
        self, store: Union[StoreType, str], alias: str = "default", **store_options: Any
    ) -> None:
        """
        Adds a task store to this scheduler.

        Any extra keyword arguments will be passed to the task store plugin's constructor, assuming
        that the first argument is the name of a task store plugin.
        """

    @abstractmethod
    def remove_store(self, alias: str, shutdown: bool = True) -> None:
        """
        Removes the task store by the given alias from this scheduler.
        """

    @abstractmethod
    def add_listener(self, callback: Any, mask: Union[int, str] = ALL_EVENTS) -> None:
        """
        add_listener(callback, mask=EVENT_ALL)

        Adds a listener for scheduler events.

        When a matching event  occurs, callback is executed with the event object as its
        sole argument. If the mask parameter is not provided, the callback will receive events
        of all types.

        Args:
            callback: any callable that takes one argument.
            mask: bitmask that indicates which events should be listened to.
        """

    @abstractmethod
    def remove_listener(self, callback: Any) -> bool:
        """
        Removes a previously added event listener.
        """

    @abstractmethod
    def add_task(
        self,
        fn_or_task: Optional[Union[Callable[..., Any], TaskType]] = None,
        trigger: Optional[Union[TriggerType, str]] = None,
        args: Optional[Any] = None,
        kwargs: Optional[Any] = None,
        id: Optional[str] = None,
        name: Optional[str] = None,
        mistrigger_grace_time: Union[int, Undefined, None] = undefined,
        coalesce: Union[bool, Undefined] = undefined,
        max_instances: Union[int, Undefined, None] = undefined,
        next_run_time: Union[datetime, str, Undefined, None] = undefined,
        store: Optional[str] = None,
        executor: Optional[str] = None,
        replace_existing: bool = False,
        **trigger_args: Any,
    ) -> TaskType:
        """
        Adds the given task to the task list and wakes up the scheduler if it's already running.

        Any option that defaults to undefined will be replaced with the corresponding default
        value when the task is scheduled (which happens when the scheduler is started, or
        immediately if the scheduler is already running).

        The fn argument can be given either as a callable object or a textual reference in
        the package.module:some.object format, where the first half (separated by :) is an
        importable module and the second half is a reference to the callable object, relative to
        the module.

        The trigger argument can either be:
          . The alias name of the trigger (e.g. date, interval or cron), in which case
            any extra keyword arguments to this method are passed on to the trigger's constructor.
          . An instance of a trigger class (TriggerType).


        Args:
            fn: Callable (or a textual reference to one) to run at the given time.
            trigger: Trigger instance that determines when fn is called.
            args: List of positional arguments to call fn with.
            kwargs: Dict of keyword arguments to call fn with.
            id: Explicit identifier for the task (for modifying it later).
            name: Textual description of the task.
            mistriger_grace_time: Seconds after the designated runtime that the task is still
                allowed to be run (or None to allow the task to run no matter how late it is).
            coalesce: Run once instead of many times if the scheduler determines that the
                task should be run more than once in succession.
            max_instances: Maximum number of concurrently running instances allowed for this task.
            next_run_time: When to first run the task, regardless of the trigger (pass
                None to add the task as paused).
            store: Alias of the task store to store the task in.
            executor: Alias of the executor to run the task with.
            replace_existing: True to replace an existing task with the same id
                              (but retain the number of runs from the existing one).
        """

    @abstractmethod
    def update_task(
        self, task_id: Union[TaskType, str], store: Optional[str] = None, **updates: Any
    ) -> TaskType:
        """
        Modifies the properties of a single task.

        Modifications are passed to this method as extra keyword arguments.

        Args:
            task_id: The identifier of the task.
            store: Alias of the store that contains the task.
        """

    @abstractmethod
    def reschedule_task(
        self,
        task_id: Union[TaskType, str],
        store: Optional[str] = None,
        trigger: Optional[Union[str, TriggerType]] = None,
        **trigger_args: Any,
    ) -> TaskType:
        """
        Constructs a new trigger for a task and updates its next run time.

        Extra keyword arguments are passed directly to the trigger's constructor.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
            trigger: Alias of the trigger type or a trigger instance.
        """

    @abstractmethod
    def pause_task(self, task_id: Union[TaskType, str], store: Optional[str] = None) -> TaskType:
        """
        Causes the given task not to be executed until it is explicitly resumed.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """

    @abstractmethod
    def resume_task(
        self, task_id: Union[TaskType, str], store: Optional[str] = None
    ) -> Union[TaskType, None]:
        """
        Resumes the schedule of the given task, or removes the task if its schedule is finished.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """

    @abstractmethod
    def get_tasks(self, store: Optional[str] = None) -> list[TaskType]:
        """
        Returns a list of pending tasks (if the scheduler hasn't been started yet) and scheduled
        tasks, either from a specific task store or from all of them.

        If the scheduler has not been started yet, only pending tasks can be returned because the
        task stores haven't been started yet either.

        Args:
            store: alias of the task store.
        """

    @abstractmethod
    def get_task(self, task_id: str, store: Optional[str] = None) -> Union[TaskType, None]:
        """
        Returms the Task that matches the given task_id.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that most likely contains the task.
        """

    @abstractmethod
    def delete_task(
        self, task_id: Union[TaskType, str, None], store: Optional[str] = None
    ) -> None:
        """
        Removes a task, preventing it from being run anymore.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that most likely contains the task.
        """

    @abstractmethod
    def remove_all_tasks(self, store: Optional[str]) -> None:
        """
        Removes all tasks from the specified task store, or all task stores if None is given.
        """

    @abstractmethod
    def wakeup(self) -> None:
        """
        Notifies the scheduler that there may be tasks due for execution.
        Triggers process_tasks to be run in an implementation specific manner.
        """
        ...

    @abstractmethod
    def create_default_executor(self) -> ExecutorType:
        """
        Creates a default executor store, specific to the articular scheduler type.
        """

    @abstractmethod
    def create_default_store(self) -> StoreType:
        """
        Creates a default store, specific to the particular scheduler type.
        """

    @abstractmethod
    def lookup_executor(self, alias: str) -> ExecutorType:
        """
        Returns the executor instance by the given name from the list of executors that were added
        to this scheduler.

        Args:
            alias: The alias for the instance.
        """

    @abstractmethod
    def lookup_store(self, alias: str) -> StoreType:
        """
        Returns the task store instance by the given name from the list of task stores that were
        added to this scheduler.

        Args:
            alias: The alias for the instance.
        """

    @abstractmethod
    def lookup_task(
        self, task_id: str, store_alias: Optional[str]
    ) -> tuple[TaskType, Optional[str]]:
        """
        Finds a task by its ID.

        Args:
            task_id: The id of the task to lookup.
            alias: Alias of a task store to look in.
        """

    @abstractmethod
    def dispatch_event(self, event: SchedulerEvent) -> None:
        """
        Dispatches the given event to interested listeners.

        Args:
            event: The SchedulerEvent to be sent.
        """

    @abstractmethod
    def create_lock(self) -> RLock:
        """
        Creates a reentrant lock object.
        """

    @abstractmethod
    def process_tasks(self) -> Optional[float]:
        """
        Iterates through tasks in every store, starts tasks that are due and figures out how long
        to wait for the next round.

        If the get_due_tasks() call raises an exception, a new wakeup is scheduled in at least
        store_retry_interval seconds.
        """

    # provide context manager defaults

    def __enter__(self) -> SchedulerType:
        result = self.start()
        if isawaitable(result):
            raise RuntimeError("Use __aenter__ instead")
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        result = self.shutdown()
        if isawaitable(result):
            raise RuntimeError("Use __aexit__ instead")
        return None

    async def __aenter__(self) -> SchedulerType:
        result = self.start()
        if isawaitable(result):
            await result
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        result = self.shutdown()
        if isawaitable(result):
            await result
        return None
