import pickle
from datetime import datetime
from typing import Any, List, Optional, Union

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType
from asyncz.stores.base import BaseStore
from asyncz.typing import DictAny
from asyncz.utils import datetime_to_utc_timestamp, maybe_ref, utc_timestamp_to_datetime

try:
    from bson.binary import Binary
    from pymongo import ASCENDING, MongoClient
    from pymongo.errors import DuplicateKeyError
except ImportError:
    raise ImportError("MongoDBStore requires pymongo to be installed")


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
        collection: Optional[str] = "tasks",
        client: Optional[MongoClient] = None,
        pickle_protocol: Optional[int] = pickle.HIGHEST_PROTOCOL,
        **kwargs: DictAny,
    ):
        super().__init__(**kwargs)
        self.pickle_protocol = pickle_protocol

        if not database:
            raise ValueError("database must not be empty or None")

        if not client:
            kwargs.setdefault("w", 1)
            self.client = MongoClient(**kwargs)
        else:
            self.client = maybe_ref(client)

        self.collection = self.client[database][collection]

    def start(self, scheduler: Any, alias: str):
        """
        When starting omits from the index any documents that lack next_run_time field.
        """
        super().start(scheduler, alias)
        self.collection.create_index("next_run_time", sparse=True)

    def lookup_task(self, task_id: Union[str, int]) -> "TaskType":
        document = self.collection.find_one(task_id, ["state"])
        return self.rebuild_task(document["state"]) if document else None

    def rebuild_task(self, state: Any) -> "TaskType":
        state = pickle.loads(state)
        task = Task.__new__(TaskType)
        task.__setstate__(state)
        task.scheduler = self.scheduler
        task.store_alias = self.alias
        return task

    def get_due_tasks(self, now: datetime) -> List["Task"]:
        timestamp = datetime_to_utc_timestamp(now)
        return self.get_tasks({"next_run_time": {"$lte": timestamp}})

    def get_tasks(self, conditions: DictAny) -> List["Task"]:
        tasks: List["Taskkk"] = []
        failed_task_ids = []

        for document in self.collection.find(
            conditions, ["_id", "state"], sort=[("next_run_time", ASCENDING)]
        ):
            try:
                tasks.append(self.rebuild_task(document["state"]))
            except BaseException:
                doc_id = document["_id"]
                self.logger.exception(f"Unable to restore task '{doc_id}'. Removing it...")
                failed_task_ids.append(doc_id)

        if failed_task_ids:
            self.collection.delete_many({"_id": {"$in": failed_task_ids}})

        return tasks

    def get_next_run_time(self) -> datetime:
        document = self.collection.find_one(
            {"next_run_time": {"$ne": None}},
            projection=["next_run_time"],
            sort=[("next_run_time", ASCENDING)],
        )
        return utc_timestamp_to_datetime(document["next_run_time"]) if document else None

    def get_all_tasks(self) -> List["Task"]:
        tasks = self.get_tasks({})
        self.fix_paused_tasks(tasks)
        return tasks

    def add_task(self, task: "TaskType"):
        try:
            self.collection.insert_one(
                {
                    "_id": task.id,
                    "next_run_time": datetime_to_utc_timestamp(task.next_run_time),
                    "state": Binary(pickle.dumps(task.__getstate__(), self.pickle_protocol)),
                }
            )
        except DuplicateKeyError:
            raise ConflictIdError(task.id)

    def update_task(self, task: "TaskType"):
        updates = {
            "next_run_time": datetime_to_utc_timestamp(task.next_run_time),
            "state": Binary(pickle.dumps(task.__getstate__(), self.pickle_protocol)),
        }
        result = self.collection.update_one({"_id": task.id}, {"$set": updates})
        if result and result.matched_count == 0:
            raise TaskLookupError(task.id)

    def delete_task(self, task_id: Union[str, int]):
        result = self.collection.delete_one({"_id": task_id})
        if result and result.deleted_count == 0:
            raise TaskLookupError(task_id)

    def remove_all_tasks(self):
        self.collection.delete_many({})

    def shutdown(self):
        self.client.close()

    def __repr__(self):
        return "<%s (client=%s)>" % (self.__class__.__name__, self.client)
