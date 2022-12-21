from datetime import datetime
from typing import List, Union

from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks.types import TaskType
from asyncz.typing import DictAny


class CustomStore(BaseStore):
    """
    A new custom store.
    """

    def get_due_tasks(self, now: datetime) -> List["TaskType"]:
        ...

    def lookup_task(self, task_id: Union[str, int]) -> "TaskType":
        ...

    def delete_task(self, task_id: Union[str, int]):
        ...

    def remove_all_tasks(self):
        ...

    def get_next_run_time(self) -> datetime:
        ...

    def get_all_tasks(self) -> List["TaskType"]:
        ...

    def add_task(self, task: "TaskType"):
        ...

    def update_task(self, task: "TaskType"):
        ...


scheduler = AsyncIOScheduler()

# Add custom store
scheduler.add_store(CustomStore, "custom")
