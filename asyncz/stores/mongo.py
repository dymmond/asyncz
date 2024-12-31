import pickle
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, cast

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task
from asyncz.typing import DictAny
from asyncz.utils import datetime_to_utc_timestamp, maybe_ref, utc_timestamp_to_datetime

try:
    from bson.binary import Binary
    from pymongo import ASCENDING, MongoClient
    from pymongo.errors import DuplicateKeyError
except ImportError:
    raise ImportError("MongoDBStore requires pymongo to be installed") from None

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class MongoDBStore(BaseStore):
    """
    Stores tasks in a Mongo database instance. Any remaining kwargs are passing directly to the mongo client.

    Args:
        database - The database to store the tasks.
        collection - The collection to store the tasks.
        client - A pymongo.mongo_client.MongoClient instance.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available.
    """

    def __init__(
        self,
        database: str = "asyncz",
        collection: str = "tasks",
        client: Optional[MongoClient] = None,
        pickle_protocol: Optional[int] = pickle.HIGHEST_PROTOCOL,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.pickle_protocol = pickle_protocol

        if not database:
            raise ValueError("database must not be empty or None")

        if not client:
            kwargs.setdefault("w", 1)
            self.client: MongoClient = MongoClient(**kwargs)
        else:
            self.client = maybe_ref(client)

        self.collection = self.client[database][collection]

    def start(self, scheduler: Any, alias: str) -> None:
        """
        When starting omits from the index any documents that lack next_run_time field.
        """
        super().start(scheduler, alias)
        self.collection.create_index("next_run_time", sparse=True)

    def lookup_task(self, task_id: str) -> Optional["TaskType"]:
        document = self.collection.find_one(task_id, ["state"])
        return self.rebuild_task(document["state"]) if document else None

    def rebuild_task(self, state: Any) -> "TaskType":
        state = pickle.loads(self.conditional_decrypt(state))
        task = Task.__new__(Task)
        task.__setstate__(state)
        task.scheduler = cast("SchedulerType", self.scheduler)
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> list["TaskType"]:
        timestamp = datetime_to_utc_timestamp(now)
        return self.get_tasks({"next_run_time": {"$lte": timestamp}})

    def get_tasks(self, conditions: DictAny) -> list["TaskType"]:
        tasks: list[TaskType] = []
        failed_task_ids = []

        for document in self.collection.find(
            conditions, ["_id", "state"], sort=[("next_run_time", ASCENDING)]
        ):
            try:
                tasks.append(self.rebuild_task(document["state"]))
            except BaseException:
                doc_id = document["_id"]
                cast("SchedulerType", self.scheduler).loggers[self.logger_name].exception(
                    f"Unable to restore task '{doc_id}'. Removing it..."
                )
                failed_task_ids.append(doc_id)

        if failed_task_ids:
            self.collection.delete_many({"_id": {"$in": failed_task_ids}})

        return tasks

    def get_next_run_time(self) -> Optional[datetime]:
        document = self.collection.find_one(
            {"next_run_time": {"$ne": None}},
            projection=["next_run_time"],
            sort=[("next_run_time", ASCENDING)],
        )
        return utc_timestamp_to_datetime(document["next_run_time"]) if document else None

    def get_all_tasks(self) -> list["TaskType"]:
        tasks = self.get_tasks({})
        self.fix_paused_tasks(tasks)
        return tasks

    def add_task(self, task: "TaskType") -> None:
        try:
            self.collection.insert_one(
                {
                    "_id": task.id,
                    "next_run_time": datetime_to_utc_timestamp(task.next_run_time or None),
                    "state": Binary(
                        self.conditional_encrypt(
                            pickle.dumps(task.__getstate__(), self.pickle_protocol)
                        )
                    ),
                }
            )
        except DuplicateKeyError:
            raise ConflictIdError(task.id) from None

    def update_task(self, task: "TaskType") -> None:
        updates = {
            "next_run_time": datetime_to_utc_timestamp(task.next_run_time or None),
            "state": Binary(
                self.conditional_encrypt(pickle.dumps(task.__getstate__(), self.pickle_protocol))
            ),
        }
        result = self.collection.update_one({"_id": task.id}, {"$set": updates})
        if result and result.matched_count == 0:
            raise TaskLookupError(task.id)

    def delete_task(self, task_id: str) -> None:
        result = self.collection.delete_one({"_id": task_id})
        if result and result.deleted_count == 0:
            raise TaskLookupError(task_id)

    def remove_all_tasks(self) -> None:
        self.collection.delete_many({})

    def shutdown(self) -> None:
        self.client.close()
        super().shutdown()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (client={self.client})>"
