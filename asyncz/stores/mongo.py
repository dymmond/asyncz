import pickle
from datetime import datetime
from typing import Any, List, Optional, Union

from asyncz.exceptions import ConflictIdError, JobLookupError
from asyncz.jobs import Job
from asyncz.jobs.types import JobType
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
    Stores jobs in a Mongo database instance. Any remaining kwargs are passing directly to the mongo client.

    Args:
        database - The database to store the jobs.
        collection - The collection to store the jobs.
        client - A pymongo.mongo_client.MongoClient instance.
        pickle_protocol - Pickle protocol level to use (for serialization), defaults to the
            highest available.
    """

    def __init__(
        self,
        database: str = "asyncz",
        collection: Optional[str] = "jobs",
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

    def lookup_job(self, job_id: Union[str, int]) -> "JobType":
        document = self.collection.find_one(job_id, ["state"])
        return self.rebuild_job(document["state"]) if document else None

    def rebuild_job(self, state: Any) -> "JobType":
        state = pickle.loads(state)
        job = Job.__new__(JobType)
        job.__setstate__(state)
        job.scheduler = self.scheduler
        job.store_alias = self.alias
        return job

    def get_due_jobs(self, now: datetime) -> List["Job"]:
        timestamp = datetime_to_utc_timestamp(now)
        return self.get_jobs({"next_run_time": {"$lte": timestamp}})

    def get_jobs(self, conditions: DictAny) -> List["Job"]:
        jobs: List["Job"] = []
        failed_job_ids = []

        for document in self.collection.find(
            conditions, ["_id", "state"], sort=[("next_run_time", ASCENDING)]
        ):
            try:
                jobs.append(self.rebuild_job(document["state"]))
            except BaseException:
                doc_id = document["_id"]
                self.logger.exception(f"Unable to restore job '{doc_id}'. Removing it...")
                failed_job_ids.append(doc_id)

        if failed_job_ids:
            self.collection.delete_many({"_id": {"$in": failed_job_ids}})

        return jobs

    def get_next_run_time(self) -> datetime:
        document = self.collection.find_one(
            {"next_run_time": {"$ne": None}},
            projection=["next_run_time"],
            sort=[("next_run_time", ASCENDING)],
        )
        return utc_timestamp_to_datetime(document["next_run_time"]) if document else None

    def get_all_jobs(self) -> List["Job"]:
        jobs = self.get_jobs({})
        self.fix_paused_jobs(jobs)
        return jobs

    def add_job(self, job: "JobType"):
        try:
            self.collection.insert_one(
                {
                    "_id": job.id,
                    "next_run_time": datetime_to_utc_timestamp(job.next_run_time),
                    "state": Binary(pickle.dumps(job.__getstate__(), self.pickle_protocol)),
                }
            )
        except DuplicateKeyError:
            raise ConflictIdError(job.id)

    def update_job(self, job: "JobType"):
        updates = {
            "next_run_time": datetime_to_utc_timestamp(job.next_run_time),
            "state": Binary(pickle.dumps(job.__getstate__(), self.pickle_protocol)),
        }
        result = self.collection.update_one({"_id": job.id}, {"$set": updates})
        if result and result.matched_count == 0:
            raise JobLookupError(job.id)

    def remove_job(self, job_id: Union[str, int]):
        result = self.collection.delete_one({"_id": job_id})
        if result and result.deleted_count == 0:
            raise JobLookupError(job_id)

    def remove_all_jobs(self):
        self.collection.delete_many({})

    def shutdown(self):
        self.client.close()

    def __repr__(self):
        return "<%s (client=%s)>" % (self.__class__.__name__, self.client)
