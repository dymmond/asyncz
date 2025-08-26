import logging
import sys
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta
from datetime import timezone as tz
from threading import RLock
from traceback import format_tb
from typing import TYPE_CHECKING, Any, cast

from asyncz.events import TaskExecutionEvent
from asyncz.events.constants import TASK_ERROR, TASK_EXECUTED, TASK_MISSED
from asyncz.exceptions import MaximumInstancesError
from asyncz.executors.types import ExecutorType

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class BaseExecutor(ExecutorType):
    """
    Base model for the executors. It defines the interface for all the executors used by the Asyncz.

    Asyncz uses loguru for its logging as it is more descriptive and intuitive.
    """

    @property
    def instances(self) -> dict[str, int]:
        assert self.scheduler is not None
        return cast("SchedulerType", self.scheduler).instances

    def start(self, scheduler: Any, alias: str) -> None:
        """
        Called by the scheduler when the scheduler is being started or when the executor is being
        added to an already running scheduler.

        Args:
            scheduler - The scheduler that is starting this executor.
            alias - The alias of this executor as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.lock: RLock = scheduler.create_lock()
        self.logger_name = f"asyncz.executors.{alias}"
        # send to tasks
        self.logger = self.scheduler.loggers[self.logger_name]

    def shutdown(self, wait: bool = True) -> None:
        """
        Shuts down the executor.

        Args:
            wait - Boolean indicating to wait until all submitted tasks have been executed.
        """

    def send_task(self, task: "TaskType", run_times: list[datetime]) -> None:
        """
        Sends the task for execution.

        Args:
            task: A Task instance to execute.
            run_times: A list of datetimes specifying when the task should have been run.
        """
        assert self.lock is not None, "This executor has not been started yet."
        assert task.id is not None, "The task is in decorator mode."
        with self.lock:
            if self.instances[task.id] >= task.max_instances:
                raise MaximumInstancesError(task.id, task.max_instances)

            self.do_send_task(task, run_times)
            self.instances[task.id] += 1

    def run_task_success(self, task_id: str, events: list[TaskExecutionEvent]) -> None:
        """
        Called by the executor with the list of generated events when the function run_task has
        been successfully executed.
        """
        with self.lock:
            self.instances[task_id] -= 1
            if self.instances[task_id] == 0:
                del self.instances[task_id]

        for event in events or []:
            self.scheduler.dispatch_event(event)

    def run_task_error(self, task_id: str) -> None:
        """
        Called by the executor with the exception if there is an error calling the run_task.
        """
        with self.lock:
            self.instances[task_id] -= 1
            if self.instances[task_id] == 0:
                del self.instances[task_id]

        self.scheduler.loggers[self.logger_name].error(
            f"Error running task {task_id}", exc_info=True
        )


def run_task(
    task: "TaskType",
    store_alias: str,
    run_times: list[datetime],
    logger: logging.Logger,
) -> list[TaskExecutionEvent]:
    """
    Called by executors to run the task. Returns a list of scheduler events to be dispatched by the
    scheduler.

    The run task is made to run in async mode.
    """

    events = []
    for run_time in run_times:
        mistrigger_grace_time = task.mistrigger_grace_time
        if mistrigger_grace_time is not None:
            difference = datetime.now(tz.utc) - run_time
            grace_time = timedelta(seconds=mistrigger_grace_time)
            if difference > grace_time:
                events.append(
                    TaskExecutionEvent(
                        code=TASK_MISSED,
                        task_id=task.id,
                        store=store_alias,
                        scheduled_run_time=run_time,
                    )
                )
                logger.warning(f"Run time of task '{task}' was missed by {difference}")
                continue

        logger.info(f'Running task "{task}" (scheduled at {run_time})')
        try:
            return_value = cast(Callable[..., Any], task.fn)(*task.args, **task.kwargs)
        except Exception as exc:
            trace_back = sys.exc_info()[2]
            formatted_trace_back = "".join(format_tb(trace_back))
            events.append(
                TaskExecutionEvent(
                    code=TASK_ERROR,
                    task_id=task.id,
                    store=store_alias,
                    scheduled_run_time=run_time,
                    exception=exc,
                    traceback=formatted_trace_back,
                )
            )
            traceback.clear_frames(trace_back)
            del trace_back
        else:
            events.append(
                TaskExecutionEvent(
                    code=TASK_EXECUTED,
                    task_id=task.id,
                    store=store_alias,
                    scheduled_run_time=run_time,
                    return_value=return_value,
                )
            )
            logger.info(f"Task '{task}' executed successfully.")
    return events


async def run_coroutine_task(
    task: "TaskType",
    store_alias: str,
    run_times: list[datetime],
    logger: logging.Logger,
) -> list[TaskExecutionEvent]:
    """
    Called by executors to run the task. Returns a list of scheduler events to be dispatched by the
    scheduler.

    The run task is made to run in async mode.
    """
    events = []
    for run_time in run_times:
        mistrigger_grace_time = task.mistrigger_grace_time
        if mistrigger_grace_time is not None:
            difference = datetime.now(tz.utc) - run_time
            grace_time = timedelta(seconds=mistrigger_grace_time)
            if difference > grace_time:
                events.append(
                    TaskExecutionEvent(
                        code=TASK_MISSED,
                        task_id=task.id,
                        alias=store_alias,
                        scheduled_run_time=run_time,
                    )
                )
                logger.warning(f"Run time of task '{task}' was missed by {difference}")
                continue

        logger.info(f'Running task "{task}" (scheduled at {run_time})')
        try:
            return_value = await cast(Callable[..., Any], task.fn)(*task.args, **task.kwargs)
        except Exception as exc:
            trace_back = sys.exc_info()[2]
            formatted_trace_back = "".join(format_tb(trace_back))
            events.append(
                TaskExecutionEvent(
                    code=TASK_ERROR,
                    task_id=task.id,
                    alias=store_alias,
                    scheduled_run_time=run_time,
                    exception=exc,
                    traceback=formatted_trace_back,
                )
            )
            traceback.clear_frames(trace_back)
            del trace_back
        else:
            events.append(
                TaskExecutionEvent(
                    code=TASK_EXECUTED,
                    task_id=task.id,
                    alias=store_alias,
                    scheduled_run_time=run_time,
                    return_value=return_value,
                )
            )
            logger.info(f"Task '{task}' executed successfully")

    return events
