from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Optional, Protocol


class LockProtectedProtocol(Protocol):
    """Non-blocking locks"""

    def protected(
        self, blocking: bool = False, timeout: Optional[int] = None
    ) -> AbstractContextManager[bool]: ...

    def shutdown(self) -> None: ...
