from __future__ import annotations

from typing import Any, Protocol

from lilya.requests import Request
from lilya.responses import Response


class User:
    def __init__(self, id: str, name: str, is_admin: bool = True, **extra: Any):
        self.id = id
        self.name = name
        self.is_admin = is_admin
        self.extra = extra


class AuthBackend(Protocol):
    async def authenticate(self, request: Request) -> User | None:
        """Return a User if the session/token is valid, else None."""

    async def login(self, request: Request) -> Response:
        """Handle POST /login (validate credentials, set session/cookie)."""

    async def logout(self, request: Request) -> Response:
        """Handle POST/GET /logout (clear session/cookie)."""

    def routes(self) -> list[Any]:
        """Optional: return extra routes (e.g., GET /login page)."""
