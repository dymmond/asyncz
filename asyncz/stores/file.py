from __future__ import annotations

import glob
import os
import pickle
import shutil
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.file_locking import LOCK_EX, LOCK_SH, with_lock
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType


class FileStore(BaseStore):
    """
    Stores tasks via sqlalchemy in a database.

    Args:
        directory - The directory to store the tasks. String or Path.
        suffix - The task suffix.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available.
    """

    forbidden_characters: set[str] = {"/", "\\", "\0", ":"}

    def __init__(
        self,
        directory: Union[str, os.PathLike],
        suffix: str = ".task",
        mode: int = 0o700,
        cleanup_directory: bool = False,
        pickle_protocol: Optional[int] = pickle.HIGHEST_PROTOCOL,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.pickle_protocol = pickle_protocol
        self.directory = Path(directory)
        self.mode = mode
        self.cleanup_directory = cleanup_directory
        self.suffix = suffix

    def check_task_id(self, task_id: str | None) -> None:
        if task_id is None:
            raise RuntimeError("Task id is None")
        if task_id.startswith("."):
            raise RuntimeError(f'Invalid character in task id: "{task_id}".')
        for char in task_id:
            if char in self.forbidden_characters:
                raise RuntimeError(f'Invalid character in task id: "{task_id}".')

    def start(self, scheduler: Any, alias: str) -> None:
        """
        When starting omits from the index any documents that lack next_run_time field.
        """
        super().start(scheduler, alias)
        self.directory.mkdir(self.mode, parents=True, exist_ok=True)
        if not self.directory.is_dir():
            raise RuntimeError("Not a directory.")

    def shutdown(self) -> None:
        if self.cleanup_directory:
            shutil.rmtree(self.directory, ignore_errors=True)
        super().shutdown()

    def lookup_task(self, task_id: str) -> Optional[TaskType]:
        self.check_task_id(task_id)
        task_path = self.directory / f"{task_id}{self.suffix}"
        try:
            with open(task_path, "rb") as read_ob, with_lock(read_ob, LOCK_SH):
                task = self.rebuild_task(read_ob.read())
        except Exception:
            task_path.unlink(missing_ok=True)
            task = None
        return task

    def rebuild_task(self, state: Any) -> TaskType:
        state = pickle.loads(self.conditional_decrypt(state))
        task = Task.__new__(Task)
        task.__setstate__(state)
        task.scheduler = cast("SchedulerType", self.scheduler)
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> list[TaskType]:
        return [
            task
            for task in self.get_all_tasks()
            if task.next_run_time is not None and task.next_run_time <= now
        ]

    def get_tasks(self) -> list[TaskType]:
        tasks: list[tuple[TaskType, os.stat_result]] = []
        with os.scandir(self.directory) as scanner:
            for entry in scanner:
                if not entry.name.endswith(self.suffix) or not entry.is_file():
                    continue
                try:
                    with open(entry.path, "rb") as read_ob, with_lock(read_ob, LOCK_SH):
                        task = self.rebuild_task(read_ob.read())
                    tasks.append((task, entry.stat()))
                except Exception:
                    with suppress(FileNotFoundError):
                        os.unlink(entry.path)
            return [
                task
                for task, _ in sorted(
                    tasks,
                    key=lambda task_stat: (
                        int(task_stat[0].next_run_time is None),
                        task_stat[0].next_run_time,
                        # sort for task creation not update
                        task_stat[1].st_ctime,
                    ),
                )
            ]

    def get_next_run_time(self) -> Optional[datetime]:
        next_run_time: datetime | None = None
        for task in self.get_all_tasks():
            if task.next_run_time is None:
                break
            if next_run_time is None or next_run_time >= task.next_run_time:
                next_run_time = task.next_run_time
        return next_run_time

    def get_all_tasks(self) -> list[TaskType]:
        return self.get_tasks()

    def add_task(self, task: TaskType) -> None:
        self.check_task_id(task.id)
        task_path = self.directory / f"{task.id}{self.suffix}"
        try:
            with task_path.open("xb") as write_ob, with_lock(write_ob, LOCK_EX):
                write_ob.write(
                    self.conditional_encrypt(
                        pickle.dumps(task.__getstate__(), self.pickle_protocol)
                    )
                )
        except FileExistsError:
            raise ConflictIdError(task.id) from None

    def update_task(self, task: TaskType) -> None:
        self.check_task_id(task.id)
        task_path = self.directory / f"{task.id}{self.suffix}"
        try:
            with task_path.open("r+b") as write_ob, with_lock(write_ob, LOCK_EX):
                write_ob.truncate()
                write_ob.write(
                    self.conditional_encrypt(
                        pickle.dumps(task.__getstate__(), self.pickle_protocol)
                    )
                )
        except FileNotFoundError:
            raise TaskLookupError(task.id) from None

    def delete_task(self, task_id: str) -> None:
        self.check_task_id(task_id)
        task_path = self.directory / f"{task_id}{self.suffix}"
        try:
            task_path.unlink(missing_ok=False)
        except FileNotFoundError:
            raise TaskLookupError(task_id) from None

    def remove_all_tasks(self) -> None:
        for task_path in self.directory.glob(f"*{glob.escape(self.suffix)}"):
            task_path.unlink(missing_ok=True)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (directory={self.directory})>"
