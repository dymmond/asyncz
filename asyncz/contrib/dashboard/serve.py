from lilya.apps import Lilya
from lilya.middleware.base import DefineMiddleware
from lilya.middleware.cors import CORSMiddleware
from lilya.middleware.sessions import SessionMiddleware
from lilya.routing import Include

from asyncz import monkay
from asyncz.contrib.dashboard import create_dashboard_app
from asyncz.schedulers.asyncio import AsyncIOScheduler

sched = AsyncIOScheduler(stores={"default": {"type": "memory"}})


app = Lilya(
    routes=[
        Include(
            path=monkay.settings.dashboard_config.dashboard_url_prefix,
            app=create_dashboard_app(scheduler=sched),
        )
    ],
    middleware=[
        DefineMiddleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        ),
        DefineMiddleware(SessionMiddleware, secret_key="secret"),
        monkay.settings.dashboard_config.session_middleware,
    ],
)


# @app.on_event("startup")
# async def _start() -> None:
#     sched.start()
#
#
# @app.on_event("shutdown")
# async def _stop() -> None:
#     """
#     Best-effort shutdown for the dashboard-owned scheduler.
#     Avoids 'RuntimeError: Event loop is closed' when the test client
#     or app lifecycle already shut down the loop.
#     """
#     try:
#         loop = getattr(sched, "event_loop", None)
#         if loop is None or getattr(loop, "is_closed", lambda: False)():
#             return
#         sched.shutdown()
#     except RuntimeError:
#         # Loop may close between check and call
#         pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("serve:app", host="0.0.0.0", port=8000, reload=True)
