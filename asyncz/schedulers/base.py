import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from importlib import import_module
from threading import RLock
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from asyncz._mapping import AsynczObjectMapping
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
    MaxInterationsReached,
    SchedulerAlreadyRunningError,
    SchedulerNotRunningError,
    TaskLookupError,
)
from asyncz.executors.base import BaseExecutor
from asyncz.executors.pool import ThreadPoolExecutor
from asyncz.stores.base import BaseStore
from asyncz.stores.memory import MemoryStore
from asyncz.tasks import Task
from asyncz.triggers.base import BaseTrigger
from asyncz.typing import undefined
from asyncz.utils import (
    TIMEOUT_MAX,
    maybe_ref,
    timedelta_seconds,
    to_bool,
    to_int,
    to_timezone,
)
from loguru import logger
from tzlocal import get_localzone

try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping

from asyncz.enums import PluginInstance, SchedulerState
from asyncz.schedulers.datastructures import TaskDefaultStruct
from asyncz.state import BaseStateExtra

DictAny = Dict[Any, Any]

if TYPE_CHECKING:
    from asyncz.executors.types import ExecutorType
    from asyncz.stores.types import StoreType
    from asyncz.tasks.types import TaskType
    from asyncz.triggers.types import TriggerType


class BaseScheduler(BaseStateExtra, ABC):
    """
    Abstract base class for all schedulers.

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

    def __init__(self, global_config: Optional["DictAny"] = None, **kwargs: "DictAny") -> None:
        super().__init__(**kwargs)
        mapping = AsynczObjectMapping()
        self.global_config = global_config or {}
        self.trigger_plugins = dict((k, v) for k, v in mapping.triggers.items())
        self.trigger_classes = {}
        self.executor_plugins = dict((k, v) for k, v in mapping.executors.items())
        self.executor_classes = {}
        self.store_plugins = dict((k, v) for k, v in mapping.stores.items())
        self.store_classes = {}
        self.executors = {}
        self.executor_lock = self.create_lock()
        self.stores = {}
        self.store_lock = self.create_lock()
        self.listeners = []
        self.listeners_lock = self.create_lock()
        self.pending_tasks = []
        self.state = SchedulerState.STATE_STOPPED
        self.logger = logger
        self.setup(self.global_config, **kwargs)

    def __getstate__(self):
        raise TypeError(
            "Schedulers cannot be serialized. Ensure that you are not passing a "
            "scheduler instance as an argument to a task, or scheduling an instance "
            "method where the instance contains a scheduler as an attribute."
        )

    def setup(
        self,
        global_config: Optional["DictAny"] = None,
        prefix: Optional[str] = "asyncz.",
        **options: "DictAny",
    ):
        """
        Reconfigures the scheduler with the given options.
        Can only be done when the scheduler isn't running.

        Args:
            global_config: a "global" configuration dictionary whose values can be overridden by
                keyword arguments to this method.
            :prefix: pick only those keys from global_config that are prefixed with
                this string (pass an empty string or None to use all keys).
        """
        global_config = global_config or {}

        if self.state != SchedulerState.STATE_STOPPED:
            raise SchedulerAlreadyRunningError()

        if prefix:
            prefix_length = len(prefix)
            global_config = dict(
                (key[prefix_length:], value)
                for key, value in global_config.items()
                if key.startswith(prefix)
            )

        config = {}
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

    def start(self, paused: bool = False):
        """
        Start the configured executors and task stores and begin processing scheduled tasks.

        Args:
            paused: If True don't start the process until resume is called.
        """
        if self.state != SchedulerState.STATE_STOPPED:
            raise SchedulerAlreadyRunningError()

        self.check_uwsgi()

        with self.executor_lock:
            if "default" not in self.executors:
                self.add_executor(self.create_default_executor(), "default")

            for alias, executor in self.executors.items():
                executor.start(self, alias)

        with self.store_lock:
            if "default" not in self.stores:
                self.add_store(self.create_default_store(), "default")

            for alias, store in self.stores.items():
                store.start(self, alias)

            for task, store_alias, replace_existing in self.pending_tasks:
                self.real_add_task(task, store_alias, replace_existing)
            del self.pending_tasks[:]

        self.state = SchedulerState.STATE_PAUSED if paused else SchedulerState.STATE_RUNNING
        self.logger.info("Scheduler started.")
        self.dispatch_event(SchedulerEvent(code=SCHEDULER_START))

        if not paused:
            self.wakeup()

    @abstractmethod
    def shutdown(self, wait: bool = True):
        """
        Shuts down the scheduler, along with its executors and task stores.
        Does not interrupt any currently running tasks.

        Args:
            wait: True to wait until all currently executing tasks have finished.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError()

        self.state = SchedulerState.STATE_STOPPED

        with self.executor_lock, self.store_lock:
            for executor in self.executors.values():
                executor.shutdown(wait)

            for store in self.stores.values():
                store.shutdown()

        self.logger.info("Scheduler has been shutdown.")
        self.dispatch_event(SchedulerEvent(code=SCHEDULER_SHUTDOWN))

    def pause(self):
        """
        Pause task processing in the scheduler.

        This will prevent the scheduler from waking up to do task processing until resume
        is called. It will not however stop any already running task processing.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError()
        elif self.state == SchedulerState.STATE_RUNNING:
            self.state = SchedulerState.STATE_PAUSED
            self.logger.info("Paused scheduler task processing.")
            self.dispatch_event(SchedulerEvent(code=SCHEDULER_PAUSED))

    def resume(self):
        """
        Resume task processing in the scheduler.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError
        elif self.state == SchedulerState.STATE_PAUSED:
            self.state = SchedulerState.STATE_RUNNING
            self.logger.info("Resumed scheduler task processing.")
            self.dispatch_event(SchedulerEvent(code=SCHEDULER_RESUMED))
            self.wakeup()

    @property
    def running(self):
        """
        Return True if the scheduler has been started. This is a shortcut
        for scheduler.state != SchedulerState.STATE_STOPPED.
        """
        return self.state != SchedulerState.STATE_STOPPED

    def add_executor(
        self, executor: "ExecutorType", alias: str = "default", **executor_options: "DictAny"
    ):
        with self.executor_lock:
            if alias in self.executors:
                raise ValueError(
                    f"This scheduler already has an executor by the alias of '{alias}'."
                )

            if isinstance(executor, BaseExecutor):
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
                executor.start(self, alias)

        self.dispatch_event(SchedulerEvent(code=EXECUTOR_ADDED, alias=alias))

    def remove_executor(self, alias: str, shutdown: bool = True):
        """
        Removes the executor by the given alias from this scheduler.
        """
        with self.executor_lock:
            executor = self.lookup_executor(alias)
            del self.executors[alias]

        if shutdown:
            executor.shutdown()

        self.dispatch_event(SchedulerEvent(code=EXECUTOR_REMOVED, alias=alias))

    def add_store(self, store: "StoreType", alias: str = "default", **store_options: "DictAny"):
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

            if isinstance(store, BaseStore):
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
                store.start(self, alias)

        self.dispatch_event(SchedulerEvent(code=STORE_ADDED, alias=alias))

        if self.state == SchedulerState.STATE_STOPPED:
            self.wakeup()

    def remove_store(self, alias: str, shutdown: bool = True):
        """
        Removes the task store by the given alias from this scheduler.
        """
        with self.store_lock:
            store = self.lookup_store(alias)
            del self.stores[alias]

        if shutdown:
            store.shutdown()

        self.dispatch_event(SchedulerEvent(code=STORE_REMOVED, alias=alias))

    def add_listener(self, callback: Any, mask: Union[int, str] = ALL_EVENTS):
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

    def remove_listener(self, callback: Any):
        """
        Removes a previously added event listener.
        """
        with self.listeners_lock:
            for index, (_callback, _) in enumerate(self.listeners):
                if callback == _callback:
                    del self.listeners[index]

    def add_task(
        self,
        fn: Optional[Callable[..., Any]],
        trigger: Optional[Union["TriggerType", str]] = None,
        args: Optional[Any] = None,
        kwargs: Optional["DictAny"] = None,
        id: Optional[str] = None,
        name: Optional[str] = None,
        mistrigger_grace_time: Optional[int] = undefined,
        coalesce: Optional[bool] = undefined,
        max_instances: Optional[int] = undefined,
        next_run_time: Optional[Union[datetime, str]] = None,
        store: str = "default",
        executor: str = "default",
        replace_existing: bool = False,
        **trigger_args: "DictAny",
    ) -> "TaskType":
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
            replace_existing: True to replace an existing task with the same id (but retain the number of runs from the existing one).
        """
        task_struct = dict(
            trigger=self.create_trigger(trigger, trigger_args),
            executor=executor,
            fn=fn,
            args=tuple(args) if args is not None else (),
            kwargs=dict(kwargs) if kwargs is not None else {},
            id=id,
            name=name,
            mistrigger_grace_time=mistrigger_grace_time,
            coalesce=coalesce,
            max_instances=max_instances,
            next_run_time=next_run_time,
        )
        task_kwargs = dict(
            (key, value) for key, value in task_struct.items() if value is not undefined
        )
        task = Task(self, **task_kwargs)

        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                self.pending_tasks.append((task, store, replace_existing))
                self.logger.info(
                    f"Adding task tentatively. It will be properly scheduled when the scheduler starts."
                )
            else:
                self.real_add_task(task, store, replace_existing)
        return task

    def scheduled_task(
        self,
        trigger: Optional[Union["TriggerType", str]] = None,
        args: Optional[Any] = None,
        kwargs: Optional["DictAny"] = None,
        id: Optional[str] = None,
        name: Optional[str] = None,
        mistrigger_grace_time: Optional[int] = undefined,
        coalesce: Optional[bool] = undefined,
        max_instances: Optional[int] = undefined,
        next_run_time: Optional[Union[datetime, str]] = undefined,
        store: str = "default",
        executor: str = "default",
        **trigger_args: "DictAny",
    ):
        """
        Functionality that can be used as a decorator for any function to schedule a task with a difference that replace_existing is always True.

        Args:
            trigger: Trigger that determines when fn is called.
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
        """

        def wrap(fn):
            self.add_task(
                fn=fn,
                trigger=trigger,
                args=args,
                kwargs=kwargs,
                id=id,
                name=name,
                mistrigger_grace_time=mistrigger_grace_time,
                coalesce=coalesce,
                max_instances=max_instances,
                next_run_time=next_run_time,
                store=store,
                executor=executor,
                replace_existing=True,
                **trigger_args,
            )
            return fn

        return wrap

    def update_task(
        self, task_id: Union[int, str], store: Optional[str] = None, **updates: "DictAny"
    ) -> "TaskType":
        """
        Modifies the propertues of a single task.

        Modifications are passed to this method as extra keyword arguments.

        Args:
            task_id: The identifier of the task.
            store: Alias of the store that contains the task.
        """
        with self.store_lock:
            task, store = self.lookup_task(task_id, store)
            task.update(**updates)

            if store:
                self.lookup_store(store).update_task(task)

        self.dispatch_event(TaskEvent(code=TASK_MODIFIED, task_id=task_id, store=store))

        if self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()
        return task

    def reschedule_task(
        self,
        task_id: Union[int, str],
        store: Optional[str] = None,
        trigger: Optional[str] = None,
        **trigger_args: "DictAny",
    ) -> "TaskType":
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
        next_run_time = trigger.get_next_trigger_time(None, now)
        return self.update_task(task_id, store, trigger=trigger, next_run_time=next_run_time)

    def pause_task(self, task_id: Union[int, str], store: Optional[str] = None) -> "TaskType":
        """
        Causes the given task not to be executed until it is explicitly resumed.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """
        return self.update_task(task_id, store, next_run_time=None)

    def resume_task(
        self, task_id: Union[int, str], store: Optional[str] = None
    ) -> Union["TaskType", None]:
        """
        Resumes the schedule of the given task, or removes the task if its schedule is finished.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that contains the task.
        """
        with self.store_lock:
            task, store = self.lookup_task(task_id, store)
            now = datetime.now(self.timezone)
            next_run_time = task.trigger.get_next_trigger_time(None, now)

            if next_run_time:
                return self.update_task(task_id, store, next_run_time=next_run_time)
            else:
                self.delete_task(task.id, store)

    def get_tasks(self, store: Optional[str] = None) -> List["TaskType"]:
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
                for task, alias, _ in self.pending_tasks:
                    if store is None or alias == store:
                        tasks.append(task)
            else:
                for alias, _store in self.stores.items():
                    if store is None or alias == store:
                        tasks.extend(_store.get_all_tasks())

            return tasks

    def get_task(self, task_id: str, store: Optional[str] = None) -> Union["TaskType", None]:
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
                return

    def delete_task(self, task_id: str, store: Optional[str] = None) -> None:
        """
        Removes a task, preventing it from being run anymore.

        Args:
            task_id: The identifier of the task.
            store: Alias of the task store that most likely contains the task.
        """
        store_alias = None

        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                for index, (task, alias, _) in enumerate(self.pending_tasks):
                    if task.id == task_id and store in (None, alias):
                        del self.pending_tasks[index]
                        store_alias = alias
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

        event = TaskEvent(code=TASK_REMOVED, task_id=task_id, store_alias=store_alias)
        self.dispatch_event(event)

        self.logger.info(f"Removed task {task_id}.")

    def remove_all_tasks(self, store: Optional[str]) -> None:
        """
        Removes all tasks from the specified task store, or all task stores if none is given.
        """
        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                if store:
                    self.pending_tasks = [
                        pending for pending in self.pending_tasks if pending[1] != store
                    ]
                else:
                    self.pending_tasks = []
            else:
                for alias, _store in self.stores.items():
                    if store in (None, alias):
                        _store.remove_all_tasks()
        self.dispatch_event(SchedulerEvent(code=ALL_TASKS_REMOVED, alias=store))

    @abstractmethod
    def wakeup(self):
        """
        Notifies the scheduler that there may be tasks due for execution.
        Triggers process_tasks to be run in an implementation specific manner.
        """

    def _setup(self, config: "DictAny") -> None:
        """
        Applies initial configurations called by the Base constructor.
        """
        self.logger = maybe_ref(config.pop("logger", None)) or logger
        self.timezone = to_timezone(config.pop("timezone", None)) or get_localzone()
        self.store_retry_interval = float(config.pop("store_retry_interval", 10))

        task_defaults = config.get("task_defaults", {})
        self.task_defaults = (
            TaskDefaultStruct(
                mistrigger_grace_time=to_int(task_defaults.get("mistrigger_grace_time")),
                coalesce=to_bool(task_defaults.get("coalesce", True)),
                max_instances=to_int(task_defaults.get("max_instances", 1)),
            )
        ) or {}

        self.executors.clear()
        for alias, value in config.get("executors", {}).items():
            if isinstance(value, BaseExecutor):
                self.add_executor(value, alias)
            elif isinstance(value, MutableMapping):
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
            if isinstance(value, BaseStore):
                self.add_store(value, alias)
            elif isinstance(value, MutableMapping):
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

    def create_default_executor(self):
        """
        Creates a default executor store, specific to the articular scheduler type.
        """
        return ThreadPoolExecutor()

    def create_default_store(self):
        """
        Creates a default store, specific to the particular scheduler type.
        """
        return MemoryStore()

    def lookup_executor(self, alias: str) -> "ExecutorType":
        """
        Returns the executor instance by the given name from the list of executors that were added
        to this scheduler.

        Args:
            alias: The alias for the instance.
        """
        try:
            return self.executors[alias]
        except KeyError:
            raise KeyError(f"No such executor: {alias}.")

    def lookup_store(self, alias: str) -> "StoreType":
        """
        Returns the task store instance by the given name from the list of task stores that were
        added to this scheduler.

        Args:
            alias: The alias for the instance.
        """
        try:
            return self.stores[alias]
        except KeyError:
            raise KeyError(f"No such store: {alias}.")

    def lookup_task(self, task_id: Union[str, int], store_alias: str) -> Any:
        """
        Finds a task by its ID.

        Args:
            task_id: The id of the task to lookup.
            alias: Alias of a task store to look in.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            for task, alias, replace_existing in self.pending_tasks:
                if task.id == task_id:
                    return task, None
        else:
            for alias, store in self.stores.items():
                if store_alias in (None, alias):
                    task = store.lookup_task(task_id)
                    if task is not None:
                        return task, alias

        raise TaskLookupError(task_id)

    def dispatch_event(self, event: "SchedulerEvent"):
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
                    self.logger.exception("Error notifying listener.")

    def check_uwsgi(self):
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

    def real_add_task(self, task: "TaskType", store_alias: str, replace_existing: bool):
        """
        Adds the task.

        Args:
            task: Task instance.
            store_alias: The alias of the store to add the task to.
            replace_existing: The flag indicating the replacement of the task.
        """
        replacements = {}
        for key, value in self.task_defaults.dict(exclude_none=True).items():
            replacements[key] = value

        # Calculate the next run time if there is none defined
        if not getattr(task, "next_run_time", None):
            now = datetime.now(self.timezone)
            replacements["next_run_time"] = task.trigger.get_next_trigger_time(None, now)

        # Apply replacements
        task._update(**replacements)

        # Add the task to the given store
        store = self.lookup_store(store_alias)
        try:
            store.add_task(task)
        except ConflictIdError:
            if replace_existing:
                store.update_task(task)
            else:
                raise

        task.store_alias = store_alias

        event = TaskEvent(code=TASK_ADDED, task_id=task.id, alias=store_alias)
        self.dispatch_event(event)

        self.logger.info(f"Added task '{task.name}' to store '{store_alias}'.")

        # Notify the scheduler about the new task.
        if self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()

    def resolve_load_plugin(self, module_name: str):
        """
        Resolve the plugin from its module and attrs.
        """
        try:
            module_path, class_name = module_name.rsplit(":", 1)
        except ValueError as err:
            raise ImportError("%s doesn't look like a module path" % module_name) from err

        module = import_module(module_path)

        try:
            return getattr(module, class_name)
        except AttributeError as exc:
            raise ImportError(str(exc)) from exc

    def create_plugin_instance(self, _type: str, alias: str, constructor_args: "DictAny"):
        """
        Creates an instance of the given plugin type, loading the plugin first if necessary.
        """
        plugin_container, class_container, base_class = {
            "trigger": (self.trigger_plugins, self.trigger_classes, BaseTrigger),
            "store": (self.store_plugins, self.store_classes, BaseStore),
            "executor": (self.executor_plugins, self.executor_classes, BaseExecutor),
        }[_type]

        try:
            plugin_cls = class_container[alias]
        except KeyError:
            if alias in plugin_container:
                # plugin_cls = class_container[alias] = plugin_container[alias].load()
                plugin_cls = class_container[alias] = self.resolve_load_plugin(
                    plugin_container[alias]
                )
                if not issubclass(plugin_cls, base_class):
                    raise TypeError(
                        f"The {format(_type)} entry point does not point to a {format(_type)} class."
                    )
            else:
                raise LookupError(f"No {_type} by the name '{alias}' was found.")

        return plugin_cls(**constructor_args)

    def create_trigger(self, trigger: "TriggerType", trigger_args: "DictAny") -> Any:
        """
        Creates a trigger.
        """
        if isinstance(trigger, BaseTrigger):
            return trigger
        elif trigger is None:
            trigger = "date"
        elif not isinstance(trigger, str):
            raise TypeError(
                f"Expected a trigger instance or string, got '{trigger.__class__.__name__}' instead."
            )

        trigger_args.setdefault("timezone", self.timezone)

        return self.create_plugin_instance("trigger", trigger, trigger_args)

    def create_lock(self):
        """
        Creates a reentrant lock object.
        """
        return RLock()

    def process_tasks(self):
        """
        Iterates through tasks in every store, starts tasks that are due and figures out how long
        to wait for the next round.

        If the get_due_tasks() call raises an exception, a new wakeup is scheduled in at least
        store_retry_interval seconds.
        """
        if self.state == SchedulerState.STATE_PAUSED:
            self.logger.debug("Scheduler is paused. Not processing tasks.")
            return None

        self.logger.debug("Looking for tasks to run.")
        now = datetime.now(self.timezone)
        next_wakeup_time = None
        events = []

        with self.store_lock:
            for store_alias, store in self.stores.items():
                try:
                    due_tasks: List["TaskType"] = store.get_due_tasks(now)
                except Exception as e:
                    self.logger.warning(
                        f"Error getting due tasks from the store {store_alias}: {e}."
                    )
                    retry_wakeup_time = now + timedelta(seconds=self.store_retry_interval)
                    if not next_wakeup_time or next_wakeup_time > retry_wakeup_time:
                        next_wakeup_time = retry_wakeup_time
                    continue

                for task in due_tasks:
                    try:
                        executor = self.lookup_executor(task.executor)
                    except BaseException:
                        self.logger.error(
                            f"Executor lookup ('{task.executor}') failed for task '{task}'. Removing it from the store."
                        )
                        self.delete_task(task.id, store_alias)
                        continue

                    run_times = task.get_run_times(now)
                    run_times = run_times[-1:] if run_times and task.coalesce else run_times

                    if run_times:
                        try:
                            executor.send_task(task, run_times)
                        except MaxInterationsReached:
                            self.logger.warning(
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
                        except BaseException:
                            self.logger.exception(
                                f"Error submitting task '{task}' to executor '{task.executor}'."
                            )
                        else:
                            event = TaskSubmissionEvent(
                                code=TASK_SUBMITTED,
                                task_id=task.id,
                                store=store_alias,
                                scheduled_run_times=run_times,
                            )
                            events.append(event)

                        next_run = task.trigger.get_next_trigger_time(run_times[-1], now)
                        if next_run:
                            task._update(next_run_time=next_run)
                            store.update_task(task)
                        else:
                            self.delete_task(task.id, store_alias)

                store_next_run_time = store.get_next_run_time()
                if store_next_run_time and (
                    next_wakeup_time is None or store_next_run_time < next_wakeup_time
                ):
                    store_next_run_time.astimezone(self.timezone)

        for event in events:
            self.dispatch_event(event)

        if self.state == SchedulerState.STATE_PAUSED:
            wait_seconds = None
            self.logger.debug("Scheduler is paused. Waiting until resume() is called.")
        elif next_wakeup_time is None:
            wait_seconds = None
            self.logger.debug("No tasks. Waiting until task is added.")
        else:
            wait_seconds = min(max(timedelta_seconds(next_wakeup_time - now), 0), TIMEOUT_MAX)
            self.logger.debug(
                f"Next wakeup is die at {next_wakeup_time} (in {wait_seconds} seconds)."
            )
