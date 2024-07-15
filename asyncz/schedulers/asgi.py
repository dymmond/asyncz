from __future__ import annotations

from contextlib import suppress
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


class MuteInteruptException(BaseException):
    pass


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
            if self.handle_lifespan:
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        try:
                            self.scheduler.start()
                        except Exception as exc:
                            await send({"type": "lifespan.startup.failed", "msg": str(exc)})
                            return
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        try:
                            self.scheduler.shutdown()
                        except Exception as exc:
                            await send({"type": "lifespan.shutdown.failed", "msg": str(exc)})
                            return
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            else:
                original_receive = receive

                async def receive() -> DictStrAny:
                    message = await original_receive()
                    if message["type"] == "lifespan.startup":
                        try:
                            self.scheduler.start()
                        except Exception as exc:
                            await send({"type": "lifespan.startup.failed", "msg": str(exc)})
                            raise MuteInteruptException from None
                    elif message["type"] == "lifespan.shutdown":
                        try:
                            self.scheduler.shutdown()
                        except Exception as exc:
                            await send({"type": "lifespan.shutdown.failed", "msg": str(exc)})
                            raise MuteInteruptException from None
                    return message

        with suppress(MuteInteruptException):
            await self.app(scope, receive, send)
