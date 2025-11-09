from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import sys
import warnings
from abc import abstractmethod
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from importlib import import_module
from inspect import isawaitable
from threading import TIMEOUT_MAX, Lock, RLock
from typing import TYPE_CHECKING, Any, Optional, Union, cast, overload

from monkay.asgi import ASGIApp, LifespanHook

from asyncz.enums import PluginInstance, SchedulerState
from asyncz.events.base import SchedulerEvent, TaskEvent, TaskSubmissionEvent
from asyncz.events.constants import (
    ALL_EVENTS,
    ALL_TASKS_REMOVED,
    EXECUTOR_ADDED,
    EXECUTOR_REMOVED,
    SCHEDULER_PAUSED,
    SCHEDULER_RESUMED,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_START,
    STORE_ADDED,
    STORE_REMOVED,
    TASK_ADDED,
    TASK_MAX_INSTANCES,
    TASK_MODIFIED,
    TASK_REMOVED,
    TASK_SUBMITTED,
)
from asyncz.exceptions import (
    ConflictIdError,
    MaximumInstancesError,
    SchedulerAlreadyRunningError,
    SchedulerNotRunningError,
    TaskLookupError,
)
from asyncz.executors.pool import ThreadPoolExecutor
from asyncz.executors.types import ExecutorType
from asyncz.locks import RLockProtected
from asyncz.schedulers import defaults
from asyncz.schedulers.datastructures import TaskDefaultStruct
from asyncz.schedulers.types import LoggersType, SchedulerType
from asyncz.stores.memory import MemoryStore
from asyncz.stores.types import StoreType
from asyncz.tasks.types import TaskType
from asyncz.triggers.types import TriggerType
from asyncz.typing import Undefined, undefined
from asyncz.utils import maybe_ref, timedelta_seconds, to_timezone_with_fallback

if TYPE_CHECKING:
    from asyncz.protocols import LockProtectedProtocol


class ClassicLogging(LoggersType):
    def __missing__(self, item: str) -> logging.Logger:
        return logging.getLogger(item)


class LoguruLoggerFnWrapper:
    def __init__(self, logger: Any, fn_name: str) -> None:
        self.logger = logger
        self.fn_name = fn_name

    def __call__(self, *args: Any, exc_info: bool = False, **kwargs: Any) -> Any:
        logger = self.logger
        logger = logger.opt(exception=True, depth=2) if exc_info else logger.opt(depth=2)
        return getattr(logger, self.fn_name)(*args, **kwargs)


class LoguruLoggerWrapper:
    def __init__(self, logger: Any) -> None:
        self.logger = logger

    def __getattr__(self, item: str) -> LoguruLoggerFnWrapper:
        return LoguruLoggerFnWrapper(self.logger, item)


default_loggers_class: type[LoggersType] = ClassicLogging

try:
    from loguru import logger

    class LoguruLogging(LoggersType):
        def __missing__(self, item: str) -> logging.Logger:
            return cast(logging.Logger, LoguruLoggerWrapper(logger.bind(name=item)))

    default_loggers_class = LoguruLogging
except ImportError:
    pass


class BaseScheduler(SchedulerType):
    """
    Abstract base class for all schedulers. Implement the base logic.

    Takes the following keyword arguments:

    Args:
        logger: logger to use for the scheduler's logging (defaults to asyncz.scheduler).
        timezone: The default time zone (defaults to the local timezone).
        store_retry_interval: The minimum number of seconds to wait between
            retries in the scheduler's main loop if the task store raises an exception when getting
            the list of due tasks.
        task_defaults: Default values for newly added tasks.
        stores: A dictionary of task store alias -> task store instance or configuration dict.
        executors: A dictionary of executor alias -> executor instance or configuration dict.
        state: current running state of the scheduler.
    """

    def __init__(
        self,
        global_config: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.trigger_plugins = dict(defaults.triggers.items())
        self.trigger_classes: dict[str, type[TriggerType]] = {}
        self.executor_plugins: dict[str, str] = dict(defaults.executors.items())
        self.executor_classes: dict[str, type[ExecutorType]] = {}
        self.store_plugins: dict[str, str] = dict(defaults.stores.items())
        self.store_classes: dict[str, type[StoreType]] = {}
        self.executors: dict[str, ExecutorType] = {}
        self.executor_lock: RLock = self.create_lock()
        self.stores: dict[str, StoreType] = {}
        self.store_processing_lock: LockProtectedProtocol = self.create_processing_lock()
        self.store_lock: RLock = self.create_lock()
        self.listeners: list[Any] = []
        self.listeners_lock: RLock = self.create_lock()
        self.pending_tasks: list[tuple[TaskType, bool, bool]] = []
        self.state: Union[SchedulerState, Any] = SchedulerState.STATE_STOPPED

        self.ref_counter: int = 0
        self.ref_lock: Lock = Lock()
        self.instances: dict[str, int] = defaultdict(lambda: 0)
        self.setup(global_config, **kwargs)

    def __getstate__(self) -> None:
        raise TypeError(
            "Schedulers cannot be serialized. Ensure that you are not passing a "
            "scheduler instance as an argument to a task, or scheduling an instance "
            "method where the instance contains a scheduler as an attribute."
        )

    def setup(
        self,
        global_config: Optional[dict[str, Any]] = None,
        prefix: Optional[str] = "asyncz.",
        **options: Any,
    ) -> None:
        """
        Reconfigures the scheduler with the given options.
        Can only be done when the scheduler isn't running.

        Args:
            global_config: a "global" configuration dictionary whose values can be overridden by
                keyword arguments to this method.
            :prefix: pick only those keys from global_config that are prefixed with
                this string (pass an empty string or None to use all keys).
        """
        if global_config is None:
            global_config = {}

        if self.state != SchedulerState.STATE_STOPPED:
            raise SchedulerAlreadyRunningError()

        if prefix:
            prefix_length = len(prefix)
            global_config = {
                key[prefix_length:]: value
                for key, value in global_config.items()
                if key.startswith(prefix)
            }

        config: dict[str, Any] = {}
        for key, value in global_config.items():
            parts = key.split(".")
            parent = config
            key = parts.pop(0)
            while parts:
                parent = parent.setdefault(key, {})
                key = parts.pop(0)
            parent[key] = value

        config.update(options)
        self._setup(config)

    def inc_refcount(self) -> bool:
        with self.ref_lock:
            self.ref_counter += 1
            # first start with 1
            if self.ref_counter > 1:
                return False
        return True

    def decr_refcount(self) -> bool:
        with self.ref_lock:
            self.ref_counter -= 1
            # first start with 0
            if self.ref_counter > 0:
                return False
        return True

    def start(self, paused: bool = False) -> bool:
        """
        Start the configured executors and task stores and begin processing scheduled tasks.

        Args:
            paused: If True don't start the process until resume is called.
        """
        if not self.inc_refcount():
            return False
        # should not happen, ref_counter should protect
        assert self.state == SchedulerState.STATE_STOPPED

        self.check_uwsgi()
        with self.executor_lock:
            if "default" not in self.executors:
                self.add_executor(self.create_default_executor(), "default")

            for alias, executor in self.executors.items():
                executor.start(self, alias)
        #
        min_dtime = None
        if self.lock_path:
            min_dtime = datetime.now(self.timezone) + timedelta(seconds=self.startup_delay)

        with self.store_lock:
            if "default" not in self.stores:
                self.add_store(self.create_default_store(), "default")

            for alias, store in self.stores.items():
                store.start(self, alias)

            for task, replace_existing, start_task in self.pending_tasks:
                with contextlib.suppress(ConflictIdError):
                    self.real_add_task(task, replace_existing, start_task, min_dtime)
            del self.pending_tasks[:]

        self.state = SchedulerState.STATE_PAUSED if paused else SchedulerState.STATE_RUNNING
        self.loggers[self.logger_name].info("Scheduler started.")
        self.dispatch_event(SchedulerEvent(code=SCHEDULER_START))

        if not paused:
            self.wakeup()
        return True

    def _shutdown_fn_helper(self, task: TaskType) -> None:
        assert task.fn is not None
        try:
            with contextlib.suppress(StopIteration):
                task.fn(*task.args, **task.kwargs)
            self.loggers[self.logger_name].info(
                f"Shutdown task {task} has been successfully executed,"
            )
        except BaseException:
            self.loggers[self.logger_name].exception(f"Error executing shutdown task {task}.")

    async def _ashutdown_fn_helper(self, task: TaskType) -> None:
        assert task.fn is not None
        try:
            with contextlib.suppress(StopAsyncIteration):
                await task.fn(*task.args, **task.kwargs)
            self.loggers[self.logger_name].info(
                f"Shutdown task {task} has been successfully executed,"
            )
        except BaseException:
            self.loggers[self.logger_name].exception(f"Error executing shutdown task {task}.")

    def handle_shutdown_coros(self, coros: Sequence[Any]) -> None:
        if coros:
            self.event_loop.call_soon_threadsafe(asyncio.gather, *coros)

    def shutdown(self, wait: bool = True) -> bool:
        """
        Shuts down the scheduler, along with its executors and task stores.
        Does not interrupt any currently running tasks.

        Args:
            wait: True to wait until all currently executing tasks have finished.
        """
        if not self.decr_refcount():
            return False

        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError()

        self.state = SchedulerState.STATE_STOPPED

        with self.executor_lock, self.store_lock:
            for executor in self.executors.values():
                executor.shutdown(wait)
            coros = []
            for _store in self.stores.values():
                for task in _store.get_all_tasks():
                    assert task.trigger is not None
                    if task.trigger.alias == "shutdown":
                        _store.delete_task(cast(str, task.id))
                        if inspect.iscoroutinefunction(task.fn):
                            coros.append(self._ashutdown_fn_helper(task))
                        else:
                            self._shutdown_fn_helper(task)
            self.handle_shutdown_coros(coros)
            for store in self.stores.values():
                store.shutdown()

        self.loggers[self.logger_name].info("Scheduler has been shutdown.")
        self.dispatch_event(SchedulerEvent(code=SCHEDULER_SHUTDOWN))
        return True

    def pause(self) -> None:
        """
        Pause task processing in the scheduler.

        This will prevent the scheduler from waking up to do task processing until resume
        is called. It will not however stop any already running task processing.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError()
        elif self.state == SchedulerState.STATE_RUNNING:
            self.state = SchedulerState.STATE_PAUSED
            self.loggers[self.logger_name].info("Paused scheduler task processing.")
            self.dispatch_event(SchedulerEvent(code=SCHEDULER_PAUSED))

    def resume(self) -> None:
        """
        Resume task processing in the scheduler.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError
        elif self.state == SchedulerState.STATE_PAUSED:
            self.state = SchedulerState.STATE_RUNNING
            self.loggers[self.logger_name].info("Resumed scheduler task processing.")
            self.dispatch_event(SchedulerEvent(code=SCHEDULER_RESUMED))
            self.wakeup()

    @property
    def running(self) -> bool:
        """
        Return True if the scheduler has been started. This is a shortcut
        for scheduler.state != SchedulerState.STATE_STOPPED.
        """
        return self.state != SchedulerState.STATE_STOPPED

    @overload
    def asgi(
        self,
        app: None,
        handle_lifespan: bool = False,
        wait: bool = False,
    ) -> Callable[[ASGIApp], ASGIApp]: ...

    @overload
    def asgi(
        self,
        app: ASGIApp,
        handle_lifespan: bool = False,
        wait: bool = False,
    ) -> ASGIApp: ...

    def asgi(
        self,
        app: Optional[ASGIApp] = None,
        handle_lifespan: bool = False,
        wait: bool = False,
    ) -> Union[ASGIApp, Callable[[ASGIApp], ASGIApp]]:
        """Return wrapper for asgi integration."""

        async def shutdown() -> None:
            result: Any = self.shutdown(wait)
            if isawaitable(result):
                await result

        async def setup() -> contextlib.AsyncExitStack:
            cm = contextlib.AsyncExitStack()
            result: Any = self.start()
            if isawaitable(result):
                await result
            cm.push_async_callback(shutdown)
            return cm

        return LifespanHook(app, setup=setup, do_forward=not handle_lifespan)

    def add_executor(
        self,
        executor: Union[ExecutorType, str],
        alias: str = "default",
        **executor_options: Any,
    ) -> None:
        with self.executor_lock:
            if alias in self.executors:
                raise ValueError(
                    f"This scheduler already has an executor by the alias of '{alias}'."
                )

            if isinstance(executor, ExecutorType):
                self.executors[alias] = executor
            elif isinstance(executor, str):
                self.executors[alias] = executor = self.create_plugin_instance(
                    PluginInstance.EXECUTOR, executor, executor_options
                )
            else:
                raise TypeError(
                    f"Expected an executor instance or a string, got {executor.__class__.__name__} instead."
                )
            if self.state != SchedulerState.STATE_STOPPED:
                cast("ExecutorType", executor).start(self, alias)

        self.dispatch_event(SchedulerEvent(code=EXECUTOR_ADDED, alias=alias))

    def remove_executor(self, alias: str, shutdown: bool = True) -> None:
        """
        Removes the executor by the given alias from this scheduler.
        """
        with self.executor_lock:
            executor = self.lookup_executor(alias)
            del self.executors[alias]

        if shutdown:
            executor.shutdown()

        self.dispatch_event(SchedulerEvent(code=EXECUTOR_REMOVED, alias=alias))

    def add_store(
        self, store: Union[StoreType, str], alias: str = "default", **store_options: Any
    ) -> None:
        """
        Adds a task store to this scheduler.

        Any extra keyword arguments will be passed to the task store plugin's constructor, assuming
        that the first argument is the name of a task store plugin.
        """
        with self.store_lock:
            if alias in self.stores:
                raise ValueError(
                    f"This scheduler already has a task store by the alias of '{alias}'."
                )

            if isinstance(store, StoreType):
                self.stores[alias] = store
            elif isinstance(store, str):
                self.stores[alias] = store = self.create_plugin_instance(
                    PluginInstance.STORE, store, store_options
                )
            else:
                raise TypeError(
                    f"Expected a task store instance or a string, got {store.__class__.__name__} instead."
                )

            if self.state != SchedulerState.STATE_STOPPED:
                cast("StoreType", store).start(self, alias)

        self.dispatch_event(SchedulerEvent(code=STORE_ADDED, alias=alias))

        if self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()

    def remove_store(self, alias: str, shutdown: bool = True) -> None:
        """
        Removes the task store by the given alias from this scheduler.
        """
        with self.store_lock:
            store = self.lookup_store(alias)
            del self.stores[alias]

        if shutdown:
            store.shutdown()

        self.dispatch_event(SchedulerEvent(code=STORE_REMOVED, alias=alias))

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
        with self.listeners_lock:
            self.listeners.append((callback, mask))

    def remove_listener(self, callback: Any) -> bool:
        """
        Removes a previously added event listener.
        """
        with self.listeners_lock:
            for index, (_callback, _) in enumerate(self.listeners):
                if callback == _callback:
                    del self.listeners[index]
                    return True
        return False

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
        store: Union[str, Undefined, None] = None,
        executor: Union[str, Undefined, None] = None,
        replace_existing: bool = False,
        # old name
        fn: Optional[Any] = None,
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
        from asyncz.tasks import Task

        if fn is not None:
            warnings.warn(
                "The parameter 'fn' was renamed to 'fn_or_task'",
                DeprecationWarning,
                stacklevel=2,
            )
            fn_or_task = fn
        if isinstance(fn_or_task, TaskType):
            assert fn_or_task.submitted is False, "Can submit tasks only once"
            fn_or_task.submitted = True
            # tweak task before submitting
            # WARNING: in contrast to the decorator mode this really updates the task
            # by providing an id (e.g. autogenerated) you can make a real task from decorator type task while submitting
            task_update_kwargs: dict[str, Any] = {
                "scheduler": self,
                "args": tuple(args) if args is not None else undefined,
                "kwargs": dict(kwargs) if kwargs is not None else undefined,
                "id": id or undefined,
                "name": name or undefined,
                "mistrigger_grace_time": mistrigger_grace_time,
                "coalesce": coalesce,
                "max_instances": max_instances,
                "next_run_time": next_run_time,
                "executor": executor if executor is not None else undefined,
                "store_alias": store if store is not None else undefined,
            }
            if trigger:
                task_update_kwargs["trigger"] = self.create_trigger(trigger, trigger_args)
                # WARNING: when submitting a task object allow_mistrigger_by_default has no effect
            task_update_kwargs = {
                key: value for key, value in task_update_kwargs.items() if value is not undefined
            }
            fn_or_task.update_task(**task_update_kwargs)
            # fallback if still not set. Set manually executor and store_alias to default.
            if fn_or_task.executor is None:
                fn_or_task.executor = "default"
            if fn_or_task.store_alias is None:
                fn_or_task.store_alias = "default"
            assert fn_or_task.trigger is not None, "Cannot submit a task without a trigger."
            assert fn_or_task.id is not None, "Cannot submit a decorator type task."
            with self.store_lock:
                if self.state == SchedulerState.STATE_STOPPED:
                    self.pending_tasks.append(
                        (
                            fn_or_task,
                            replace_existing,
                            next_run_time is not None,
                        )
                    )
                    self.loggers[self.logger_name].info(
                        "Adding task tentatively. It will be properly scheduled when the scheduler starts."
                    )
                else:
                    self.real_add_task(
                        fn_or_task, replace_existing, next_run_time is not None, None
                    )
            return fn_or_task
        task_kwargs: dict[str, Any] = {
            "scheduler": self,
            "trigger": self.create_trigger(trigger, trigger_args),
            "fn": fn_or_task,
            "args": tuple(args) if args is not None else (),
            "kwargs": dict(kwargs) if kwargs is not None else {},
            "id": id,
            "name": name,
            "mistrigger_grace_time": mistrigger_grace_time,
            "coalesce": coalesce,
            "max_instances": max_instances,
            "next_run_time": next_run_time,
            "executor": executor if executor is not None else undefined,
            "store_alias": store if store is not None else undefined,
        }
        task_kwargs = {key: value for key, value in task_kwargs.items() if value is not undefined}
        if task_kwargs["trigger"].allow_mistrigger_by_default:
            # we want to be able, to just use add_task, and the task is scheduled
            task_kwargs.setdefault("mistrigger_grace_time", None)
        for key, value in self.task_defaults.model_dump(exclude_none=True).items():
            task_kwargs.setdefault(key, value)

        task = Task(**task_kwargs)
        if task.fn is not None:
            return self.add_task(
                task, replace_existing=replace_existing, next_run_time=next_run_time
            )
        return task

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
        if isinstance(task_id, TaskType):
            assert task_id.id, "Cannot update a decorator type Task"
            new_updates = task_id.model_dump()
            new_updates.update(**updates)
            task_id = task_id.id
        else:
            new_updates = updates

        with self.store_lock:
            task, store = self.lookup_task(task_id, store)
            task.update(**new_updates)

            if store:
                self.lookup_store(store).update_task(task)

        self.dispatch_event(TaskEvent(code=TASK_MODIFIED, task_id=task_id, store=store))

        if self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()
        return task

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
        trigger = self.create_trigger(trigger, trigger_args)
        now = datetime.now(self.timezone)
        next_run_time = trigger.get_next_trigger_time(self.timezone, None, now)
        return self.update_task(task_id, store, trigger=trigger, next_run_time=next_run_time)

    def pause_task(self, task_id: Union[TaskType, str], store: Optional[str] = None) -> TaskType:
        """
        Causes the given task not to be executed until it is explicitly resumed.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """
        return self.update_task(task_id, store, next_run_time=None)

    def resume_task(
        self, task_id: Union[TaskType, str], store: Optional[str] = None
    ) -> Union[TaskType, None]:
        """
        Resumes the schedule of the given task, or removes the task if its schedule is finished.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """
        if isinstance(task_id, TaskType):
            assert task_id.id, "Cannot resume decorator style Task"
            task_id = task_id.id
        with self.store_lock:
            task, store = self.lookup_task(task_id, store)
            now = datetime.now(self.timezone)
            next_run_time = task.trigger.get_next_trigger_time(self.timezone, None, now)  # type: ignore

            if next_run_time:
                return self.update_task(task_id, store, next_run_time=next_run_time)
            else:
                self.delete_task(task.id, store)
                return None

    def get_tasks(self, store: Optional[str] = None) -> list[TaskType]:
        """
        Returns a list of pending tasks (if the scheduler hasn't been started yet) and scheduled
        tasks, either from a specific task store or from all of them.

        If the scheduler has not been started yet, only pending tasks can be returned because the
        task stores haven't been started yet either.

        Args:
            store: alias of the task store.
        """
        with self.store_lock:
            tasks = []
            if self.state == SchedulerState.STATE_STOPPED:
                for task, _, _ in self.pending_tasks:
                    if store is None or task.store_alias == store:
                        tasks.append(task)
            else:
                for alias, _store in self.stores.items():
                    if store is None or alias == store:
                        tasks.extend(_store.get_all_tasks())

            return tasks

    def get_task(self, task_id: str, store: Optional[str] = None) -> Union[TaskType, None]:
        """
        Returms the Task that matches the given task_id.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that most likely contains the task.
        """
        with self.store_lock:
            try:
                return self.lookup_task(task_id, store)[0]
            except TaskLookupError:
                return None

    def delete_task(
        self, task_id: Union[TaskType, str, None], store: Optional[str] = None
    ) -> None:
        """
        Removes a task, preventing it from being run anymore.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that most likely contains the task.
        """
        if isinstance(task_id, TaskType):
            task_id = task_id.id
        if not task_id:
            return
        store_alias = None

        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                for index, (task, _, _) in enumerate(self.pending_tasks):
                    if task.id == task_id and store in (None, task.store_alias):
                        del self.pending_tasks[index]
                        store_alias = task.store_alias
                        break
            else:
                for alias, _store in self.stores.items():
                    if store in (None, alias):
                        try:
                            _store.delete_task(task_id)
                            store_alias = alias
                            break
                        except TaskLookupError:
                            continue

        if store_alias is None:
            raise TaskLookupError(task_id)

        event = TaskEvent(code=TASK_REMOVED, task_id=task_id, store=store_alias)
        self.dispatch_event(event)

        self.loggers[self.logger_name].info(f"Removed task {task_id}.")

    def remove_all_tasks(self, store: Optional[str]) -> None:
        """
        Removes all tasks from the specified task store, or all task stores if none is given.
        """
        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                if store:
                    self.pending_tasks = [
                        pending
                        for pending in self.pending_tasks
                        if pending[0].store_alias != store
                    ]
                else:
                    self.pending_tasks = []
            else:
                for alias, _store in self.stores.items():
                    if store in (None, alias):
                        _store.remove_all_tasks()
        self.dispatch_event(SchedulerEvent(code=ALL_TASKS_REMOVED, alias=store))

    @abstractmethod
    def wakeup(self) -> None:
        """
        Notifies the scheduler that there may be tasks due for execution.
        Triggers process_tasks to be run in an implementation specific manner.
        """
        ...

    def _setup(self, config: Any) -> None:
        """
        Applies initial configurations called by the Base constructor.
        """
        self.timezone = to_timezone_with_fallback(config.pop("timezone", None))
        self.lock_path = str(config.pop("lock_path", "") or "")
        self.store_retry_interval = float(config.pop("store_retry_interval", 10))
        self.startup_delay = float(config.pop("startup_delay", 0 if not self.lock_path else 1))

        self.task_defaults = TaskDefaultStruct(**(config.get("task_defaults", None) or {}))
        loggers_class: type[LoggersType] = (
            maybe_ref(config.pop("loggers_class", None)) or default_loggers_class
        )
        self.loggers = loggers_class()
        logger_name = config.pop("logger_name", None)
        if logger_name:
            self.logger_name = f"asyncz.schedulers.{logger_name}"
        else:
            self.logger_name = "asyncz.schedulers"
        # initialize logger for scheduler
        self.loggers[self.logger_name]

        self.executors.clear()
        for alias, value in config.get("executors", {}).items():
            if isinstance(value, ExecutorType):
                self.add_executor(value, alias)
            elif isinstance(value, Mapping):
                value = dict(value)
                executor_class = value.pop("class", None)
                plugin = value.pop("type", None)
                if plugin:
                    executor = self.create_plugin_instance("executor", plugin, value)
                elif executor_class:
                    cls = maybe_ref(executor_class)
                    executor = cls(**value)
                else:
                    raise ValueError(
                        f"Cannot create executor '{alias}'. Either 'type' or 'class' must be defined."
                    )
                self.add_executor(executor, alias)
            else:
                raise TypeError(
                    f"Expected executor instance or dict for executors['{alias}'], got {value.__class__.__name__} instead."
                )

        # Stores
        self.stores.clear()
        for alias, value in config.get("stores", {}).items():
            if isinstance(value, StoreType):
                self.add_store(value, alias)
            elif isinstance(value, Mapping):
                value = dict(value)
                store_class = value.pop("class", None)
                plugin = value.pop("type", None)
                if plugin:
                    store = self.create_plugin_instance("store", plugin, value)
                elif store_class:
                    cls = maybe_ref(store_class)
                    store = cls(**value)
                else:
                    raise ValueError(
                        f"Cannot create store '{alias}'. Either 'type' or 'class' must be defined."
                    )
                self.add_store(store, alias)
            else:
                raise TypeError(
                    f"Expected store instance or dict for stores['{alias}'], got {value.__class__.__name__} instead."
                )

    def create_default_executor(self) -> ExecutorType:
        """
        Creates a default executor store, specific to the articular scheduler type.
        """
        return ThreadPoolExecutor()

    def create_default_store(self) -> StoreType:
        """
        Creates a default store, specific to the particular scheduler type.
        """
        return MemoryStore()

    def lookup_executor(self, alias: str) -> ExecutorType:
        """
        Returns the executor instance by the given name from the list of executors that were added
        to this scheduler.

        Args:
            alias: The alias for the instance.
        """
        try:
            return self.executors[alias]
        except KeyError:
            raise KeyError(f"No such executor: {alias}.") from None

    def lookup_store(self, alias: str) -> StoreType:
        """
        Returns the task store instance by the given name from the list of task stores that were
        added to this scheduler.

        Args:
            alias: The alias for the instance.
        """
        try:
            return self.stores[alias]
        except KeyError:
            raise KeyError(f"No such store: {alias}.") from None

    def lookup_task(
        self, task_id: str, store_alias: Optional[str]
    ) -> tuple[TaskType, Optional[str]]:
        """
        Finds a task by its ID.

        Args:
            task_id: The id of the task to lookup.
            alias: Alias of a task store to look in.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            for task, _, _ in self.pending_tasks:
                if task.id == task_id and store_alias in (None, task.store_alias):
                    return task, None
        else:
            for alias, store in self.stores.items():
                if store_alias in (None, alias):
                    task2 = store.lookup_task(task_id)
                    if task2 is not None:
                        return task2, alias

        raise TaskLookupError(task_id)

    def dispatch_event(self, event: SchedulerEvent) -> None:
        """
        Dispatches the given event to interested listeners.

        Args:
            event: The SchedulerEvent to be sent.
        """
        with self.listeners_lock:
            listeners = tuple(self.listeners)

        for callback, mask in listeners:
            if event.code & mask:
                try:
                    callback(event)
                except BaseException:
                    self.loggers[self.logger_name].exception("Error notifying listener.")

    def check_uwsgi(self) -> None:
        """
        Check if we are running under uWSGI with threads disabled.
        """
        uwsgi_module = sys.modules.get("uwsgi")
        if not getattr(uwsgi_module, "has_threads", True):
            raise RuntimeError(
                "The scheduler seems to be running under uWSGI, but threads have "
                "been disabled. You must run uWSGI with the --enable-threads "
                "option for the scheduler to work."
            )

    def real_add_task(
        self,
        task: TaskType,
        replace_existing: bool,
        start_task: bool,
        min_dtime: datetime | None = None,
    ) -> None:
        """
        Adds the task.

        Args:
            task: Task instance.
            store_alias: The alias of the store to add the task to.
            replace_existing: The flag indicating the replacement of the task.
        """
        assert task.trigger is not None, "Submitted task has no trigger set."
        assert task.store_alias is not None, "Submitted task has no store_alias set."
        assert task.executor is not None, "Submitted task has no executor set."
        replacements: dict[str, Any] = {}

        # Calculate the next run time if there is none defined
        if task.next_run_time is None and start_task:
            now = datetime.now(self.timezone)
            replacements["next_run_time"] = task.trigger.get_next_trigger_time(
                self.timezone, None, now
            )
            if min_dtime is not None and isinstance(replacements["next_run_time"], datetime):
                replacements["next_run_time"] = max(min_dtime, replacements["next_run_time"])
        elif isinstance(task.next_run_time, datetime) and min_dtime is not None:
            replacements["next_run_time"] = max(min_dtime, task.next_run_time)

        # Apply replacements
        task.update_task(**replacements)
        # Add the task to the given store
        store = self.lookup_store(task.store_alias)
        try:
            store.add_task(task)
        except ConflictIdError as exc:
            if replace_existing:
                try:
                    store.update_task(task)
                except TaskLookupError:
                    # was executed and is now gone
                    return
            else:
                raise exc
        task.pending = False

        event = TaskEvent(code=TASK_ADDED, task_id=task.id, alias=task.store_alias)
        self.dispatch_event(event)

        self.loggers[self.logger_name].info(
            f"Added task '{task.name}' to store '{task.store_alias}'."
        )

        # Notify the scheduler about the new task.
        if start_task and self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()

    @classmethod
    def resolve_load_plugin(cls, module_name: str) -> Any:
        """
        Resolve the plugin from its module and attrs.
        """
        try:
            module_path, class_name = module_name.rsplit(":", 1)
        except ValueError as err:
            raise ImportError(f"{module_name} doesn't look like a module path") from err

        module = import_module(module_path)

        try:
            return getattr(module, class_name)
        except AttributeError as exc:
            raise ImportError(str(exc)) from exc

    def create_plugin_instance(self, _type: str, alias: str, constructor_args: Any) -> Any:
        """
        Creates an instance of the given plugin type, loading the plugin first if necessary.
        """
        plugin_container, class_container, base_class = {
            "trigger": (self.trigger_plugins, self.trigger_classes, TriggerType),
            "store": (self.store_plugins, self.store_classes, StoreType),
            "executor": (self.executor_plugins, self.executor_classes, ExecutorType),
        }[_type]

        try:
            plugin_cls = class_container[alias]  # type: ignore
        except KeyError:
            if alias in plugin_container:
                # plugin_cls = class_container[alias] = plugin_container[alias].load()
                plugin_cls = class_container[alias] = self.resolve_load_plugin(  # type: ignore
                    plugin_container[alias]
                )
                if not issubclass(plugin_cls, base_class):
                    raise TypeError(
                        f"The {format(_type)} entry point does not point to a {format(_type)} class."
                    ) from None
            else:
                raise LookupError(f"No {_type} by the name '{alias}' was found.") from None

        return plugin_cls(**constructor_args)

    def create_trigger(
        self, trigger: Union[TriggerType, str, None], trigger_args: Any
    ) -> TriggerType:
        """
        Creates a trigger.
        """
        if isinstance(trigger, TriggerType):
            return trigger
        elif trigger is None:
            trigger = "date"
        elif not isinstance(trigger, str):
            raise TypeError(
                f"Expected a trigger instance or string, got '{trigger.__class__.__name__}' instead."
            )

        trigger_args.setdefault("timezone", self.timezone)

        return cast("TriggerType", self.create_plugin_instance("trigger", trigger, trigger_args))

    def create_lock(self) -> RLock:
        """
        Creates a reentrant lock object.
        """
        return RLock()

    def create_processing_lock(self) -> LockProtectedProtocol:
        """
        Creates a non-reentrant lock object used to distribute between threads for processing.
        """
        return RLockProtected()

    def _process_tasks_of_store(
        self,
        now: datetime,
        next_wakeup_time: Optional[datetime],
        store_alias: str,
        store: StoreType,
        events: list[SchedulerEvent],
    ) -> Optional[datetime]:
        # mt lock
        with store.lock.protected(blocking=False) as success_blocking:
            if not success_blocking:
                retry_wakeup_time = now + timedelta(seconds=self.store_retry_interval)
                if not next_wakeup_time or next_wakeup_time > retry_wakeup_time:
                    next_wakeup_time = retry_wakeup_time
                return next_wakeup_time

            try:
                due_tasks: list[TaskType] = store.get_due_tasks(now)
            except Exception as e:
                self.loggers[self.logger_name].warning(
                    f'Error getting due tasks from the store "{store_alias}": {e}.'
                )
                retry_wakeup_time = now + timedelta(seconds=self.store_retry_interval)
                if not next_wakeup_time or next_wakeup_time > retry_wakeup_time:
                    next_wakeup_time = retry_wakeup_time
                return next_wakeup_time

            for task in due_tasks:
                try:
                    executor = self.lookup_executor(task.executor)  # type: ignore
                except Exception:
                    self.loggers[self.logger_name].error(
                        f"Executor lookup ('{task.executor}') failed for task '{task}'. Removing it from the store."
                    )
                    self.delete_task(task.id, store_alias)
                    continue

                run_times = task.get_run_times(self.timezone, now)
                run_times = run_times[-1:] if run_times and task.coalesce else run_times

                if run_times:
                    try:
                        executor.send_task(task, run_times)
                    except MaximumInstancesError:
                        self.loggers[self.logger_name].warning(
                            f"Execution of task '{task}' skipped: Maximum number of running "
                            f"instances reached '({task.max_instances})'."
                        )
                        event = TaskSubmissionEvent(
                            code=TASK_MAX_INSTANCES,
                            task_id=task.id,
                            store=store_alias,
                            scheduled_run_times=run_times,
                        )
                        events.append(event)
                    except Exception:
                        self.loggers[self.logger_name].exception(
                            f"Error submitting task '{task}' to executor '{task.executor}'.",
                            exc_info=True,
                        )
                    else:
                        event = TaskSubmissionEvent(
                            code=TASK_SUBMITTED,
                            task_id=task.id,
                            store=store_alias,
                            scheduled_run_times=run_times,
                        )
                        events.append(event)

                    next_run = task.trigger.get_next_trigger_time(  # type: ignore
                        self.timezone, run_times[-1], now
                    )
                    if next_run:
                        task.update_task(next_run_time=next_run)
                        store.update_task(task)
                    else:
                        self.delete_task(task.id, store_alias)

            store_next_run_time = store.get_next_run_time()
            if store_next_run_time and (
                next_wakeup_time is None or store_next_run_time < next_wakeup_time
            ):
                next_wakeup_time = store_next_run_time.astimezone(self.timezone)
            return next_wakeup_time

    def process_tasks(self) -> Optional[float]:
        """
        Iterates through tasks in every store, starts tasks that are due and figures out how long
        to wait for the next round.

        If the get_due_tasks() call raises an exception, a new wakeup is scheduled in at least
        store_retry_interval seconds.
        """
        if self.state == SchedulerState.STATE_PAUSED:
            self.loggers[self.logger_name].debug("Scheduler is paused. Not processing tasks.")
            return None

        self.loggers[self.logger_name].debug("Looking for tasks to run.")
        now = datetime.now(self.timezone)
        next_wakeup_time: Optional[datetime] = None
        events: list[SchedulerEvent] = []

        # check for other processing thread
        with self.store_processing_lock.protected(blocking=False) as blocking_success:
            if blocking_success:
                # threading lock
                with self.store_lock:
                    for store_alias, store in self.stores.items():
                        next_wakeup_time = self._process_tasks_of_store(
                            now, next_wakeup_time, store_alias, store, events
                        )
            else:
                retry_wakeup_time = now + timedelta(seconds=self.store_retry_interval)
                if not next_wakeup_time or next_wakeup_time > retry_wakeup_time:
                    next_wakeup_time = retry_wakeup_time

        for event in events:
            self.dispatch_event(event)

        wait_seconds: Optional[float] = None
        if self.state == SchedulerState.STATE_PAUSED:
            self.loggers[self.logger_name].debug(
                "Scheduler is paused. Waiting until resume() is called."
            )
        elif next_wakeup_time is None:
            if self.lock_path:
                wait_seconds = self.store_retry_interval
                self.loggers[self.logger_name].debug(f"No tasks found. Recheck in {wait_seconds}.")
            else:
                self.loggers[self.logger_name].debug("No tasks. Waiting until task is added.")

        else:
            wait_seconds = min(max(timedelta_seconds(next_wakeup_time - now), 0), TIMEOUT_MAX)
            self.loggers[self.logger_name].debug(
                f"Next wakeup is due at {next_wakeup_time} (in {wait_seconds} seconds)."
            )
        return wait_seconds
