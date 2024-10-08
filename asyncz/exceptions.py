from typing import Any, Optional


class AsynczException(Exception):
    """
    Base exception for all Asyncz thrown error exceptions.
    """

    detail = None

    def __init__(self, *args: Any, detail: str = "") -> None:
        if detail:
            self.detail = detail
        super().__init__(*(str(arg) for arg in args if arg), detail)

    def __repr__(self) -> str:
        if self.detail:
            return f"{self.__class__.__name__} - {self.detail}"
        return self.__class__.__name__

    def __str__(self) -> str:
        return "".join(self.args).strip()


class BaseLookupError(LookupError):
    """
    Base lookup error for all the Asyncz lookup errors.
    """

    detail = "Not found."

    def __init__(self, detail: Optional[str] = None) -> None:
        if not detail:
            detail = self.detail
        super().__init__(detail)


class AsynczLookupError(BaseLookupError):
    """
    general LookupError for Asyncz.
    """

    ...


class SchedulerLookupError(BaseLookupError):
    detail = "No schedule with the id {schedule_id} has been found."

    def __init__(self, schedule_id: str) -> None:
        detail = self.detail.format(schedule_id=schedule_id)
        super().__init__(detail=detail)


class TaskLookupError(BaseLookupError):
    detail = "No task with the id {task_id} has been found."

    def __init__(self, task_id: Optional[str]) -> None:
        detail = self.detail.format(task_id=task_id)
        super().__init__(detail=detail)


class ConflictError(KeyError):
    detail = "This data store already contains a schedule with the identifier {schedule_id}."

    def __init__(self, schedule_id: str) -> None:
        detail = self.detail.format(schedule_id=schedule_id)
        super().__init__(detail)


class ConflictIdError(KeyError):
    detail = "Task identifier ({task_id}) conflicts with an existing task."

    def __init__(self, task_id: Optional[str]) -> None:
        detail = self.detail.format(task_id=task_id)
        super().__init__(detail)


class MaximumInstancesError(AsynczException):
    detail = "The task by the id of {id} reached its maximum number of instances {total}."

    def __init__(self, _id: str, total: int) -> None:
        detail = self.detail.format(id=_id, total=total)
        super().__init__(detail=detail)


class SchedulerAlreadyRunningError(AsynczException):
    detail = "Scheduler is already running"

    def __str__(self) -> str:
        return self.detail


class SchedulerNotRunningError(AsynczException):
    detail = "Scheduler is not running"

    def __str__(self) -> str:
        return self.detail
