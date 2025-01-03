from __future__ import annotations

import pickle
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType
from asyncz.utils import datetime_to_utc_timestamp, utc_timestamp_to_datetime

try:
    import sqlalchemy
    from sqlalchemy.exc import IntegrityError
except ImportError:
    raise ImportError("SQLALchemyStore requires SQLALchemy to be installed") from None

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType


class SQLAlchemyStore(BaseStore):
    """
    Stores tasks via sqlalchemy in a database.

    Args:
        database - The database to store the tasks. String or Engine possible.
        tablename - The tablename to store the tasks.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available.
    """

    def __init__(
        self,
        database: Union[str, sqlalchemy.Engine],
        tablename: str = "asyncz_store",
        pickle_protocol: Optional[int] = pickle.HIGHEST_PROTOCOL,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.pickle_protocol = pickle_protocol
        if isinstance(database, str):
            database = sqlalchemy.create_engine(database, **kwargs)
        if not database:
            raise ValueError("database must not be empty or None")
        self.engine: sqlalchemy.Engine = database
        self.metadata: sqlalchemy.MetaData = sqlalchemy.MetaData()
        self.table: sqlalchemy.Table = sqlalchemy.Table(
            tablename,
            self.metadata,
            sqlalchemy.Column(
                "id", sqlalchemy.String(length=255), primary_key=True, nullable=False
            ),
            sqlalchemy.Column("next_run_time", sqlalchemy.BigInteger(), nullable=True),
            sqlalchemy.Column("state", sqlalchemy.LargeBinary(), nullable=False),
        )

    def start(self, scheduler: Any, alias: str) -> None:
        """
        When starting omits from the index any documents that lack next_run_time field.
        """
        super().start(scheduler, alias)
        self.metadata.create_all(self.engine)

    def shutdown(self) -> None:
        self.engine.dispose()
        super().shutdown()

    def lookup_task(self, task_id: str) -> Optional[TaskType]:
        tasks = self.get_tasks(self.table.c.id == task_id, limit=1)
        return tasks[0] if tasks else None

    def rebuild_task(self, state: Any) -> TaskType:
        state = pickle.loads(self.conditional_decrypt(state))
        task = Task.__new__(Task)
        task.__setstate__(state)
        task.scheduler = cast("SchedulerType", self.scheduler)
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> list[TaskType]:
        timestamp = datetime_to_utc_timestamp(now)
        return self.get_tasks(self.table.c.next_run_time <= timestamp)

    def get_tasks(self, conditions: Any = None, limit: int = 0) -> list[TaskType]:
        tasks: list[TaskType] = []
        failed_task_ids = []
        stmt = self.table.select().order_by(self.table.c.next_run_time.asc().nullslast())
        if conditions is not None:
            stmt = stmt.where(conditions)

        if limit > 0:
            stmt = stmt.limit(limit)

        with self.engine.connect() as conn:
            for row in conn.execute(stmt):
                try:
                    tasks.append(self.rebuild_task(row.state))
                except Exception:
                    task_id = row.id
                    cast("SchedulerType", self.scheduler).loggers[self.logger_name].exception(
                        f"Unable to restore task '{task_id}'. Removing it..."
                    )
                    failed_task_ids.append(task_id)

            if failed_task_ids:
                stmt2 = self.table.delete().where(self.table.c.id.in_(failed_task_ids))
                conn.execute(stmt2)
                conn.commit()
        return tasks

    def get_next_run_time(self) -> Optional[datetime]:
        stmt = (
            sqlalchemy.select(self.table.c["next_run_time"])
            .where(self.table.c.next_run_time != None)  #  noqa: E711  other meaning than is not None
            .order_by(self.table.c.next_run_time.asc())
        )

        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()

            return utc_timestamp_to_datetime(row.next_run_time) if row else None

    def get_all_tasks(self) -> list[TaskType]:
        return self.get_tasks()

    def add_task(self, task: TaskType) -> None:
        data = {
            "id": task.id,
            "next_run_time": datetime_to_utc_timestamp(task.next_run_time or None),
            "state": self.conditional_encrypt(
                pickle.dumps(task.__getstate__(), self.pickle_protocol)
            ),
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(self.table.insert().values(**data))
        except IntegrityError:
            raise ConflictIdError(task.id) from None

    def update_task(self, task: TaskType) -> None:
        updates = {
            "next_run_time": datetime_to_utc_timestamp(task.next_run_time or None),
            "state": self.conditional_encrypt(
                pickle.dumps(task.__getstate__(), self.pickle_protocol)
            ),
        }
        success = True

        with self.engine.begin() as conn:
            result = conn.execute(
                self.table.update().values(**updates).where(self.table.c.id == task.id)
            )
            if result and result.rowcount == 0:
                success = False
        if not success:
            raise TaskLookupError(task.id)

    def delete_task(self, task_id: str) -> None:
        success = True
        with self.engine.begin() as conn:
            result = conn.execute(self.table.delete().where(self.table.c.id == task_id))
            if result and result.rowcount == 0:
                success = False
        if not success:
            raise TaskLookupError(task_id)

    def remove_all_tasks(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(self.table.delete())

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (database={self.engine.url})>"
