from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from asyncz.typing import DictStrAny

if TYPE_CHECKING:
    from asyncz.schedulers.base import BaseScheduler

ASGIApp = Callable[
    [
        DictStrAny,
        Callable[[], Awaitable[DictStrAny]],
        Callable[[DictStrAny], Awaitable[None]],
    ],
    Awaitable[None],
]


@dataclass
class ASGIHelper:
    app: ASGIApp
    scheduler: BaseScheduler
    handle_lifespan: bool = False

    async def __call__(
        self,
        scope: DictStrAny,
        receive: Callable[[], Awaitable[DictStrAny]],
        send: Callable[[DictStrAny], Awaitable[None]],
    ) -> None:
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    self.scheduler.start()
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "msg": str(exc)})
                    return
            elif message["type"] == "lifespan.shutdown":
                try:
                    self.scheduler.stop()
                except Exception as exc:
                    await send({"type": "lifespan.shutdown.failed", "msg": str(exc)})
                    return

            if self.handle_lifespan:
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                return
            else:

                async def receive() -> DictStrAny:
                    return message

        await self.app(scope, receive, send)
