from typing import Union

from .asyncio import AsyncIOExecutor
from .base import BaseExecutor
from .debug import DebugExecutor

ExecutorType = Union[BaseExecutor, AsyncIOExecutor, DebugExecutor]
