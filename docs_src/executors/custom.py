from datetime import datetime
from typing import Any, List

from asyncz.executors.base import BaseExecutor
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.types import TaskType


class CustomExecutor(BaseExecutor):
    """
    A new custom executor.
    """

    def start(self, scheduler: Any, alias: str): ...

    def shutdown(self, wait: bool = True): ...

    def send_task(self, task: "TaskType", run_times: List[datetime]): ...

    def do_send_task(self, task: "TaskType", run_times: List[datetime]) -> Any: ...


# Create executor
executor = CustomExecutor()

scheduler = AsyncIOScheduler()

# Add custom executor
scheduler.add_executor(executor, "cutom")
