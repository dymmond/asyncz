"""
This file is only used for development purposes.
Please do not use this anywhere in your code base
"""

from lilya.apps import Lilya
from lilya.routing import Include

from asyncz.contrib.dashboard.admin import (
    AsynczAdmin,
    SimpleUsernamePasswordBackend,
    User,
)
from asyncz.schedulers.asyncio import AsyncIOScheduler

sched = AsyncIOScheduler(stores={"default": {"type": "memory"}})


def verify(u: str, p: str) -> User | None:
    if u == "admin" and p == "secret":
        return User(id="admin", name="Admin")
    return None


asyncz_admin = AsynczAdmin(enable_login=True, backend=SimpleUsernamePasswordBackend(verify))  # type: ignore
app = Lilya(routes=[Include("/", app=asyncz_admin.get_asgi_app(with_url_prefix=True))])
# app = Lilya()
# asyncz_admin.include_in(app)


@app.on_event("startup")
async def _start() -> None:
    sched.start()


@app.on_event("shutdown")
async def _stop() -> None:
    """
    Best-effort shutdown for the dashboard-owned scheduler.
    Avoids 'RuntimeError: Event loop is closed' when the test client
    or app lifecycle already shut down the loop.
    """
    try:
        loop = getattr(sched, "event_loop", None)
        if loop is None or getattr(loop, "is_closed", lambda: False)():
            return
        sched.shutdown()
    except RuntimeError:
        # Loop may close between check and call
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True)
