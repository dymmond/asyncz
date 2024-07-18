from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.stores.base import BaseStore
from asyncz.utils import datetime_to_utc_timestamp

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class MemoryStore(BaseStore):
    """
    Stores tasks in an array in RAM. Provides no persistance support.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tasks: List[Tuple[TaskType, Optional[float]]] = []
        self.tasks_index: Dict[str, Tuple[TaskType, Optional[float]]] = {}

    def lookup_task(self, task_id: str) -> Optional["TaskType"]:
        return self.tasks_index.get(task_id, (None, None))[0]

    def get_due_tasks(self, now: datetime) -> List["TaskType"]:
        now_timestamp = datetime_to_utc_timestamp(now)
        pending = []

        for task, timestamp in self.tasks:
            if timestamp is None or timestamp > now_timestamp:
                break
            pending.append(task)

        return pending

    def get_next_run_time(self) -> Optional[datetime]:
        return (self.tasks[0][0].next_run_time or None) if self.tasks else None

    def get_all_tasks(self) -> List["TaskType"]:
        return [task[0] for task in self.tasks]

    def add_task(self, task: "TaskType") -> None:
        assert task.id is not None, "The task is in decorator mode."
        if task.id in self.tasks_index:
            raise ConflictIdError(task.id)

        timestamp = datetime_to_utc_timestamp(task.next_run_time or None)
        index = self.get_task_index(timestamp, task.id)

        self.tasks.insert(index, (task, timestamp))
        self.tasks_index[task.id] = (task, timestamp)

    def update_task(self, task: "TaskType") -> None:
        assert task.id is not None, "The task is in decorator mode."
        old_task, old_timestamp = self.tasks_index.get(task.id, (None, None))
        if old_task is None:
            raise TaskLookupError(task.id)

        old_index = self.get_task_index(old_timestamp, old_task.id)  # type: ignore
        new_timestamp = datetime_to_utc_timestamp(task.next_run_time or None)
        if old_timestamp == new_timestamp:
            self.tasks[old_index] = (task, new_timestamp)
        else:
            del self.tasks[old_index]
            new_index = self.get_task_index(new_timestamp, task.id)
            self.tasks.insert(new_index, (task, new_timestamp))

    def delete_task(self, task_id: str) -> None:
        task, timestamp = self.tasks_index.get(task_id, (None, None))
        if task is None:
            raise TaskLookupError(task_id)

        index = self.get_task_index(timestamp, task_id)
        del self.tasks[index]
        del self.tasks_index[task_id]

    def remove_all_tasks(self) -> None:
        self.tasks = []
        self.tasks_index = {}

    def shutdown(self) -> None:
        self.remove_all_tasks()

    def get_task_index(self, timestamp: Union[int, float, None], task_id: str) -> int:
        """
        Returns the index of the given task, or if it's not found, the index where the task should be
        inserted based on the given timestamp.
        """
        low, high = 0, len(self.tasks)
        timestamp = float("inf") if timestamp is None else timestamp
        while low < high:
            mid = (low + high) // 2
            mid_task, mid_timestamp = self.tasks[mid]
            mid_timestamp = float("inf") if mid_timestamp is None else mid_timestamp
            if mid_timestamp > timestamp:
                high = mid
            elif mid_timestamp < timestamp:
                low = mid + 1
            elif mid_task.id > task_id:  # type: ignore
                high = mid
            elif mid_task.id < task_id:  # type: ignore
                low = mid + 1
            else:
                return mid

        return low
