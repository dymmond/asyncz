import warnings
from datetime import datetime
from datetime import timezone as dtimezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from asyncz.schedulers.types import SchedulerType
from asyncz.triggers.types import TriggerType
from asyncz.typing import undefined

try:
    from esmerald.conf import settings
    from esmerald.exceptions import ImproperlyConfigured
    from esmerald.utils.module_loading import import_string
except ImportError:
    raise ImportError(
        "Esmerald cannot be found. Please install it by running `pip install esmerald`."
    )

if TYPE_CHECKING:
    from esmerald.applications import Esmerald
    from pydantic.typing import AnyCallable


class EsmeraldScheduler:
    """
    Scheduler instance to be used by the Esmerald application instance.

    Args:
        app: Esmerald application
        scheduler_class: An instance of a SchedulerType
        tasks: A dictinary str, str mapping the tasks to be executed.
        timezone: The timezone instance.
        configurations: A dictionary with extra configurations to be passed to the scheduler.
    """

    def __init__(
        self,
        app: Optional["Esmerald"] = None,
        scheduler_class: Optional["SchedulerType"] = None,
        tasks: Optional[Dict[str, str]] = None,
        timezone: Optional[dtimezone] = None,
        configurations: Optional[Dict[str, str]] = None,
    ) -> None:
        self.app = app
        self.tasks = tasks
        self.timezone = timezone
        self.scheduler_class = scheduler_class
        self.configurations = configurations

        if not self.scheduler_class and self.app.enable_scheduler:
            raise ImproperlyConfigured(
                "It cannot start the scheduler if there is no scheduler_class declared."
            )

        for task, module in self.tasks.items():
            if not isinstance(task, str) or not isinstance(module, str):
                raise ImproperlyConfigured("The dict of tasks must be Dict[str, str].")

        if not self.tasks:
            warnings.warn(
                "Esmerald is starting the scheduler, yet there are no tasks declared.",
                UserWarning,
                stacklevel=2,
            )

        # Load the scheduler object
        self.handler = self.get_scheduler(
            scheduler=self.scheduler_class,
            timezone=self.timezone,
            configurations=self.configurations,
        )

        self.register_events(app=self.app)
        self.register_tasks(tasks=self.tasks)

    def register_tasks(self, tasks: Dict[str, str]) -> None:
        """
        Registers the tasks in the Scheduler
        """
        for task, _module in tasks.items():
            imported_task = f"{_module}.{task}"
            scheduled_task: "Task" = import_string(imported_task)

            if not scheduled_task.is_enabled:
                continue

            try:
                scheduled_task.add_task(self.handler)
            except Exception as e:
                raise ImproperlyConfigured(str(e))

    def register_events(self, app: "Esmerald") -> None:
        """
        Registers the scheduler events in the Esmerald application.
        """

        @app.on_event("startup")
        def start_scheduler() -> None:
            self.handler.start()

        @app.on_event("shutdown")
        def stop_scheduler() -> None:
            self.handler.shutdown()

    def get_scheduler(
        self,
        scheduler: "SchedulerType",
        timezone: Optional[dtimezone] = None,
        configurations: Optional[Dict[str, str]] = None,
    ) -> SchedulerType:
        """
        Initiates the scheduler from the given time.
        If no value is provided, it will default to AsyncIOScheduler.

        The value of `scheduler_class` can be overwritten by any esmerald custom settings.

        Args:
            scheduler: AsyncIOScheduler.
            timezone: The timezone instance.
            configurations: A dictionary with extra configurations to be passed to the scheduler.

        Return:
            SchedulerType: An instance of a Scheduler.
        """
        if not timezone:
            timezone = settings.timezone

        if not configurations:
            return scheduler(timezone=timezone)

        return scheduler(global_config=configurations, timezone=timezone)


class Task:
    """
    Base for the scheduler decorator that will auto discover the
    tasks in the application and add them to the internal scheduler.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        trigger: Optional[TriggerType] = None,
        id: Optional[str] = None,
        mistrigger_grace_time: Optional[int] = None,
        coalesce: Optional[bool] = None,
        max_intances: Optional[int] = None,
        next_run_time: Optional[datetime] = None,
        store: Optional[str] = "default",
        executor: Optional[str] = "default",
        replace_existing: bool = False,
        args: Optional[Any] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        is_enabled: bool = True,
    ) -> None:
        """_summary_

        Args:
            name: Textual description of the task.
            trigger: An instance of a trigger class.
            identifier: Explicit identifier for the task.
            mistrigger_grace_time: Seconds after the designated runtime that the task is still allowed to be run (or None to allow the task to run no
                matter  how late it is).
            coalesce: Run once instead of many times if the scheduler determines that the task should be run more than once in succession.
            max_intances: Maximum number of concurrently running instances allowed for this task.
            next_run_time: When to first run the task, regardless of the trigger (pass None to add the task as paused).
            store: Alias of the task store to store the task in.
            executor: Alias of the executor to run the task with.
            replace_existing: True to replace an existing task with the same id
                (but retain the number of runs from the existing one).
            args: List of positional arguments to call func with.
            kwargs: Dict of keyword arguments to call func with.
            is_enabled: True if the the task to be added to the scheduler.
        """
        self.name = name
        self.trigger = trigger
        self.id = id
        self.mistrigger_grace_time = mistrigger_grace_time or undefined
        self.coalesce = coalesce or undefined
        self.max_intances = max_intances or undefined
        self.next_run_time = next_run_time or undefined
        self.store = store
        self.executor = executor
        self.replace_existing = replace_existing
        self.args = args
        self.kwargs = kwargs
        self.is_enabled = is_enabled
        self.fn = None

    def add_task(self, scheduler: "SchedulerType"):
        try:
            scheduler.add_task(
                fn=self.fn,
                trigger=self.trigger,
                args=self.args,
                kwargs=self.kwargs,
                id=self.id,
                name=self.name,
                mistrigger_grace_time=self.mistrigger_grace_time,
                coalesce=self.coalesce,
                max_instances=self.max_intances,
                next_run_time=self.next_run_time,
                store=self.store,
                executor=self.executor,
                replace_existing=self.replace_existing,
            )
        except Exception as e:
            raise ImproperlyConfigured(str(e))

    def __call__(self, fn: "AnyCallable") -> None:
        """
        Tricking the object into think it's being instantiated by in reality
        is just returning itself.
        """
        self.fn = fn
        return self
