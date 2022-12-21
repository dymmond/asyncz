from typing import Union

from .base import BaseStore
from .memory import MemoryStore
from .mongo import MongoDBStore
from .redis import RedisStore

StoreType = Union[BaseStore, MemoryStore, MongoDBStore, RedisStore]
