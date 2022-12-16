from typing import Union

from .base import BaseStore
from .memory import MemoryStore

StoreType = Union[BaseStore, MemoryStore]
