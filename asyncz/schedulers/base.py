import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from importlib import import_module
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

from asyncz._mapping import AsynczObjectMapping
from asyncz.events.base import JobEvent, JobSubmissionEvent, SchedulerEvent
from asyncz.events.constants import (
    ALL_EVENTS,
    ALL_JOBS_REMOVED,
    EXECUTOR_ADDED,
    EXECUTOR_REMOVED,
    JOB_ADDED,
    JOB_MAX_INSTANCES,
    JOB_MODIFIED,
    JOB_REMOVED,
    JOB_SUBMITTED,
    SCHEDULER_PAUSED,
    SCHEDULER_RESUMED,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_START,
    STORE_ADDED,
    STORE_REMOVED,
)
from asyncz.exceptions import (
    ConflictIdError,
    JobLookupError,
    MaxInterationsReached,
    SchedulerAlreadyRunningError,
    SchedulerNotRunningError,
)
from asyncz.executors.base import BaseExecutor
from asyncz.executors.pool import ThreadPoolExecutor
from asyncz.jobs import Job
from asyncz.stores.base import BaseStore
from asyncz.stores.memory import MemoryStore
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
from asyncz.schedulers.datastructures import JobDefaultStruct
from asyncz.state import BaseStateExtra

DictAny = Dict[Any, Any]

if TYPE_CHECKING:
    from asyncz.executors.types import ExecutorType
    from asyncz.jobs.types import JobType
    from asyncz.stores.types import StoreType
    from asyncz.triggers.types import TriggerType


class BaseScheduler(BaseStateExtra, ABC):
    """
    Abstract base class for all schedulers.

    Takes the following keyword arguments:

    Args:
        logger: logger to use for the scheduler's logging (defaults to asyncz.scheduler).
        timezone: The default time zone (defaults to the local timezone).
        store_retry_interval: The minimum number of seconds to wait between
            retries in the scheduler's main loop if the job store raises an exception when getting
            the list of due jobs.
        job_defaults: Default values for newly added jobs.
        stores: A dictionary of job store alias -> job store instance or configuration dict.
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
        self.pending_jobs = []
        self.state = SchedulerState.STATE_STOPPED
        self.logger = logger
        self.configure(self.global_config, **kwargs)

    def __getstate__(self):
        raise TypeError(
            "Schedulers cannot be serialized. Ensure that you are not passing a "
            "scheduler instance as an argument to a job, or scheduling an instance "
            "method where the instance contains a scheduler as an attribute."
        )

    def configure(
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
        self._configure(config)

    def start(self, paused: bool = False):
        """
        Start the configured executors and job stores and begin processing scheduled jobs.

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

            for job, store_alias, replace_existing in self.pending_jobs:
                self.real_add_job(job, store_alias, replace_existing)
            del self.pending_jobs[:]

        self.state = SchedulerState.STATE_PAUSED if paused else SchedulerState.STATE_RUNNING
        self.logger.info("Scheduler started.")
        self.dispatch_event(SchedulerEvent(code=SCHEDULER_START))

        if not paused:
            self.wakeup()

    @abstractmethod
    def shutdown(self, wait: bool = True):
        """
        Shuts down the scheduler, along with its executors and job stores.
        Does not interrupt any currently running jobs.

        Args:
            wait: True to wait until all currently executing jobs have finished.
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
        Pause job processing in the scheduler.

        This will prevent the scheduler from waking up to do job processing until resume
        is called. It will not however stop any already running job processing.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError()
        elif self.state == SchedulerState.STATE_RUNNING:
            self.state = SchedulerState.STATE_PAUSED
            self.logger.info("Paused scheduler job processing.")
            self.dispatch_event(SchedulerEvent(code=SCHEDULER_PAUSED))

    def resume(self):
        """
        Resume job processing in the scheduler.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            raise SchedulerNotRunningError
        elif self.state == SchedulerState.STATE_PAUSED:
            self.state = SchedulerState.STATE_RUNNING
            self.logger.info("Resumed scheduler job processing.")
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
        Adds a job store to this scheduler.

        Any extra keyword arguments will be passed to the job store plugin's constructor, assuming
        that the first argument is the name of a job store plugin.
        """
        with self.store_lock:
            if alias in self.stores:
                raise ValueError(
                    f"This scheduler already has a job store by the alias of '{alias}'."
                )

            if isinstance(store, BaseStore):
                self.stores[alias] = store
            elif isinstance(store, str):
                self.stores[alias] = store = self.create_plugin_instance(
                    PluginInstance.STORE, store, store_options
                )
            else:
                raise TypeError(
                    f"Expected a job store instance or a string, got {store.__class__.__name__} instead."
                )

            if self.state != SchedulerState.STATE_STOPPED:
                store.start(self, alias)

        self.dispatch_event(SchedulerEvent(code=STORE_ADDED, alias=alias))

        if self.state == SchedulerState.STATE_STOPPED:
            self.wakeup()

    def remove_store(self, alias: str, shutdown: bool = True):
        """
        Removes the job store by the given alias from this scheduler.
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

    def add_job(
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
    ) -> "JobType":
        """
        Adds the given job to the job list and wakes up the scheduler if it's already running.

        Any option that defaults to undefined will be replaced with the corresponding default
        value when the job is scheduled (which happens when the scheduler is started, or
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
            id: Explicit identifier for the job (for modifying it later).
            name: Textual description of the job.
            mistriger_grace_time: Seconds after the designated runtime that the job is still
                allowed to be run (or None to allow the job to run no matter how late it is).
            coalesce: Run once instead of many times if the scheduler determines that the
                job should be run more than once in succession.
            max_instances: Maximum number of concurrently running instances allowed for this job.
            next_run_time: When to first run the job, regardless of the trigger (pass
                None to add the job as paused).
            store: Alias of the job store to store the job in.
            executor: Alias of the executor to run the job with.
            replace_existing: True to replace an existing job with the same id (but retain the number of runs from the existing one).
        """
        job_struct = dict(
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
        job_kwargs = dict(
            (key, value) for key, value in job_struct.items() if value is not undefined
        )
        job = Job(self, **job_kwargs)

        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                self.pending_jobs.append((job, store, replace_existing))
                self.logger.info(
                    f"Adding job tentatively. It will be properly scheduled when the scheduler starts."
                )
            else:
                self.real_add_job(job, store, replace_existing)
        return job

    def scheduled_job(
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
        Functionality that can be used as a decorator for any function to schedule a job with a difference that replace_existing is always True.

        Args:
            trigger: Trigger that determines when fn is called.
            args: List of positional arguments to call fn with.
            kwargs: Dict of keyword arguments to call fn with.
            id: Explicit identifier for the job (for modifying it later).
            name: Textual description of the job.
            mistriger_grace_time: Seconds after the designated runtime that the job is still
                allowed to be run (or None to allow the job to run no matter how late it is).
            coalesce: Run once instead of many times if the scheduler determines that the
                job should be run more than once in succession.
            max_instances: Maximum number of concurrently running instances allowed for this job.
            next_run_time: When to first run the job, regardless of the trigger (pass
                None to add the job as paused).
            store: Alias of the job store to store the job in.
            executor: Alias of the executor to run the job with.
        """

        def wrap(fn):
            self.add_job(
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

    def update_job(
        self, job_id: Union[int, str], store: Optional[str] = None, **updates: "DictAny"
    ) -> "JobType":
        """
        Modifies the propertues of a single job.

        Modifications are passed to this method as extra keyword arguments.

        Args:
            job_id: The identifier of the job.
            store: Alias of the store that contains the job.
        """
        with self.store_lock:
            job, store = self.lookup_job(job_id, store)
            job.update(**updates)

            if store:
                self.lookup_store(store).update_job(job)

        self.dispatch_event(JobEvent(code=JOB_MODIFIED, job_id=job_id, store=store))

        if self.state == SchedulerState.STATE_RUNNING:
            self.wakeup()
        return job

    def reschedule_job(
        self,
        job_id: Union[int, str],
        store: Optional[str] = None,
        trigger: Optional[str] = None,
        **trigger_args: "DictAny",
    ) -> "JobType":
        """
        Constructs a new trigger for a job and updates its next run time.

        Extra keyword arguments are passed directly to the trigger's constructor.

        Args:
            job_id: The identifier of the job.
            store: Alias of the job store that contains the job.
            trigger: Alias of the trigger type or a trigger instance.
        """
        trigger = self.create_trigger(trigger, trigger_args)
        now = datetime.now(self.timezone)
        next_run_time = trigger.get_next_trigger_time(None, now)
        return self.update_job(job_id, store, trigger=trigger, next_run_time=next_run_time)

    def pause_job(self, job_id: Union[int, str], store: Optional[str] = None) -> "JobType":
        """
        Causes the given job not to be executed until it is explicitly resumed.

        Args:
            job_id: The identifier of the job.
            store: Alias of the job store that contains the job.
        """
        return self.update_job(job_id, store, next_run_time=None)

    def resume_job(
        self, job_id: Union[int, str], store: Optional[str] = None
    ) -> Union["JobType", None]:
        """
        Resumes the schedule of the given job, or removes the job if its schedule is finished.

        Args:
            job_id: The identifier of the job.
            store: Alias of the job store that contains the job.
        """
        with self.store_lock:
            job, store = self.lookup_job(job_id, store)
            now = datetime.now(self.timezone)
            next_run_time = job.trigger.get_next_trigger_time(None, now)

            if next_run_time:
                return self.update_job(job_id, store, next_run_time=next_run_time)
            else:
                self.remove_job(job.id, store)

    def get_jobs(self, store: Optional[str] = None) -> List["JobType"]:
        """
        Returns a list of pending jobs (if the scheduler hasn't been started yet) and scheduled
        jobs, either from a specific job store or from all of them.

        If the scheduler has not been started yet, only pending jobs can be returned because the
        job stores haven't been started yet either.

        Args:
            store: alias of the job store.
        """
        with self.store_lock:
            jobs = []
            if self.state == SchedulerState.STATE_STOPPED:
                for job, alias, _ in self.pending_jobs:
                    if store is None or alias == store:
                        jobs.append(job)
            else:
                for alias, _store in self.stores.items():
                    if store is None or alias == store:
                        jobs.extend(_store.get_all_jobs())

            return jobs

    def get_job(self, job_id: str, store: Optional[str] = None) -> Union["JobType", None]:
        """
        Returms the Job that matches the given job_id.

        Args:
            job_id: The identifier of the job.
            store: Alias of the job store that most likely contains the job.
        """
        with self.store_lock:
            try:
                return self.lookup_job(job_id, store)[0]
            except JobLookupError:
                return

    def remove_job(self, job_id: str, store: Optional[str] = None) -> None:
        """
        Removes a job, preventing it from being run anymore.

        Args:
            job_id: The identifier of the job.
            store: Alias of the job store that most likely contains the job.
        """
        store_alias = None

        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                for index, (job, alias, _) in enumerate(self.pending_jobs):
                    if job.id == job_id and store in (None, alias):
                        del self.pending_jobs[index]
                        store_alias = alias
                        break
            else:
                for alias, _store in self.stores.items():
                    if store in (None, alias):
                        try:
                            _store.remove_job(job_id)
                            store_alias = alias
                            break
                        except JobLookupError:
                            continue

        if store_alias is None:
            raise JobLookupError(job_id)

        event = JobEvent(code=JOB_REMOVED, job_id=job_id, store_alias=store_alias)
        self.dispatch_event(event)

        self.logger.info(f"Removed job {job_id}.")

    def remove_all_jobs(self, store: Optional[str]) -> None:
        """
        Removes all jobs from the specified job store, or all job stores if none is given.
        """
        with self.store_lock:
            if self.state == SchedulerState.STATE_STOPPED:
                if store:
                    self.pending_jobs = [
                        pending for pending in self.pending_jobs if pending[1] != store
                    ]
                else:
                    self.pending_jobs = []
            else:
                for alias, _store in self.stores.items():
                    if store in (None, alias):
                        _store.remove_all_jobs()
        self.dispatch_event(SchedulerEvent(code=ALL_JOBS_REMOVED, alias=store))

    @abstractmethod
    def wakeup(self):
        """
        Notifies the scheduler that there may be jobs due for execution.
        Triggers process_jobs to be run in an implementation specific manner.
        """

    def _configure(self, config: "DictAny") -> None:
        """
        Applies initial configurations called by the Base constructor.
        """
        # General options
        self.logger = maybe_ref(config.pop("logger", None)) or logger
        self.timezone = to_timezone(config.pop("timezone", None)) or get_localzone()
        self.store_retry_interval = float(config.pop("store_retry_interval", 10))

        # Job options
        job_defaults = config.get("job_defaults", {})
        self.job_defaults = JobDefaultStruct(
            mistrigger_grace_time=to_int(job_defaults.get("mistrigger_grace_time")),
            coalesce=to_bool(job_defaults.get("coalesce", True)),
            max_instances=to_int(job_defaults.get("max_instances", 1)),
        )

        # Executors
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
        Returns the job store instance by the given name from the list of job stores that were
        added to this scheduler.

        Args:
            alias: The alias for the instance.
        """
        try:
            return self.stores[alias]
        except KeyError:
            raise KeyError(f"No such store: {alias}.")

    def lookup_job(self, job_id: Union[str, int], store_alias: str) -> Any:
        """
        Finds a job by its ID.

        Args:
            job_id: The id of the job to lookup.
            alias: Alias of a job store to look in.
        """
        if self.state == SchedulerState.STATE_STOPPED:
            for job, alias, replace_existing in self.pending_jobs:
                if job.id == job_id:
                    return job, None
        else:
            for alias, store in self.stores.items():
                if store_alias in (None, alias):
                    job = store.lookup_job(job_id)
                    if job is not None:
                        return job, alias

        raise JobLookupError(job_id)

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

    def real_add_job(self, job: "JobType", store_alias: str, replace_existing: bool):
        """
        Adds the job.

        Args:
            job: Job instance.
            store_alias: The alias of the store to add the job to.
            replace_existing: The flag indicating the replacement of the job.
        """
        replacements = {}
        for key, value in self.job_defaults.dict(exclude_none=True).items():
            replacements[key] = value

        # Calculate the next run time if there is none defined
        if not getattr(job, "next_run_time", None):
            now = datetime.now(self.timezone)
            replacements["next_run_time"] = job.trigger.get_next_trigger_time(None, now)

        # Apply replacements
        job._update(**replacements)

        # Add the job to the given store
        store = self.lookup_store(store_alias)
        try:
            store.add_job(job)
        except ConflictIdError:
            if replace_existing:
                store.update_job(job)
            else:
                raise

        # Mark the job as no longer pending
        job.store_alias = store_alias

        # Notify listeners that a new job has been added
        event = JobEvent(code=JOB_ADDED, job_id=job.id, alias=store_alias)
        self.dispatch_event(event)

        self.logger.info(f"Added job '{job.name}' to store '{store_alias}'.")

        # Notify the scheduler about the new job.
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

    def process_jobs(self):
        """
        Iterates through jobs in every jobstore, starts jobs that are due and figures out how long
        to wait for the next round.

        If the get_due_jobs() call raises an exception, a new wakeup is scheduled in at least
        store_retry_interval seconds.
        """
        if self.state == SchedulerState.STATE_PAUSED:
            self.logger.debug("Scheduler is paused --- not processing jobs.")
            return None

        self.logger.debug("Looking for jobs to run.")
        now = datetime.now(self.timezone)
        next_wakeup_time = None
        events = []

        with self.store_lock:
            for store_alias, store in self.stores.items():
                try:
                    due_jobs: List["JobType"] = store.get_due_jobs(now)
                except Exception as e:
                    self.logger.warning(
                        f"Error getting due jobs from the store {store_alias}: {e}."
                    )
                    retry_wakeup_time = now + timedelta(seconds=self.store_retry_interval)
                    if not next_wakeup_time or next_wakeup_time > retry_wakeup_time:
                        next_wakeup_time = retry_wakeup_time
                    continue

                for job in due_jobs:
                    try:
                        executor = self.lookup_executor(job.executor)
                    except BaseException:
                        self.logger.error(
                            f"Executor lookup ('{job.executor}') failed for job '{job}'. Removing it from the store."
                        )
                        self.remove_job(job.id, store_alias)
                        continue

                    run_times = job.get_run_times(now)
                    run_times = run_times[-1:] if run_times and job.coalesce else run_times

                    if run_times:
                        try:
                            executor.send_job(job, run_times)
                        except MaxInterationsReached:
                            self.logger.warning(
                                f"Execution of job '{job}' skipped: Maximum number of running "
                                f"instances reached '({job.max_instances})'."
                            )
                            event = JobSubmissionEvent(
                                code=JOB_MAX_INSTANCES,
                                job_id=job.id,
                                store=store_alias,
                                scheduled_run_times=run_times,
                            )
                            events.append(event)
                        except BaseException:
                            self.logger.exception(
                                f"Error submitting job '{job}' to executor '{job.executor}'."
                            )
                        else:
                            event = JobSubmissionEvent(
                                code=JOB_SUBMITTED,
                                job_id=job.id,
                                store=store_alias,
                                scheduled_run_times=run_times,
                            )
                            events.append(event)

                        next_run = job.trigger.get_next_trigger_time(run_times[-1], now)
                        if next_run:
                            job._update(next_run_time=next_run)
                            store.update_job(job)
                        else:
                            self.remove_job(job.id, store_alias)

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
            self.logger.debug("No jobs. Waiting until job is added.")
        else:
            wait_seconds = min(max(timedelta_seconds(next_wakeup_time - now), 0), TIMEOUT_MAX)
            self.logger.debug(
                f"Next wakeup is die at {next_wakeup_time} (in {wait_seconds} seconds)."
            )
