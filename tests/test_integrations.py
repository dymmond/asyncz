import contextlib
import time

import pytest
from esmerald import Gateway, Request
from esmerald import JSONResponse as EsmeraldJSONResponse
from esmerald import route as esmerald_route
from esmerald.applications import Esmerald
from esmerald.contrib.schedulers.asyncz.config import AsynczConfig
from lilya.apps import Lilya
from lilya.responses import JSONResponse as LilyaJSONResponse
from lilya.routing import Path
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.schedulers.base import ClassicLogging, LoguruLogging


def get_starlette_app():
    scheduler = AsyncIOScheduler()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with scheduler:
            yield {"scheduler": scheduler}

    async def list_notes(request: StarletteRequest):
        assert request.state.scheduler is scheduler
        return StarletteJSONResponse([])

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/notes", endpoint=list_notes, methods=["GET"]),
        ],
    )

    return app, scheduler


def get_asgi_app():
    scheduler = AsyncIOScheduler()

    async def list_notes(request: StarletteRequest):
        return StarletteJSONResponse([])

    app = scheduler.asgi(
        Starlette(
            routes=[
                Route("/notes", endpoint=list_notes, methods=["GET"]),
            ],
        )
    )

    return app, scheduler


def get_asgi_app2():
    scheduler = AsyncIOScheduler()

    async def list_notes(request: StarletteRequest):
        return StarletteJSONResponse([])

    app = scheduler.asgi(
        Starlette(
            routes=[
                Route("/notes", endpoint=list_notes, methods=["GET"]),
            ],
        ),
        handle_lifespan=True,
    )

    return app, scheduler


def get_lilya_app():
    scheduler = AsyncIOScheduler()

    async def list_notes(request: Request) -> LilyaJSONResponse:
        return LilyaJSONResponse([])

    app = Lilya(routes=[Path("/notes", methods=["GET"], handler=list_notes)])

    @app.on_event("startup")
    async def startup():
        scheduler.start()

    @app.on_event("shutdown")
    async def shutdown():
        scheduler.shutdown()

    return app, scheduler


def get_lilya_start_shutdown_app():
    scheduler = AsyncIOScheduler()

    async def list_notes(request: Request) -> LilyaJSONResponse:
        return LilyaJSONResponse([])

    app = Lilya(
        routes=[
            Path(
                "/notes",
                methods=["GET"],
                handler=list_notes,
            )
        ],
        on_startup=[
            scheduler.start,
        ],
        on_shutdown=[
            scheduler.shutdown,
        ],
    )

    return app, scheduler


def get_esmerald_app():
    scheduler = AsyncIOScheduler()

    @esmerald_route("/notes", methods=["GET"])
    async def list_notes(request: Request) -> EsmeraldJSONResponse:
        return EsmeraldJSONResponse([])

    app = Esmerald(routes=[Gateway(handler=list_notes)], enable_scheduler=False)

    @app.on_event("startup")
    async def startup():
        scheduler.start()

    @app.on_event("shutdown")
    async def shutdown():
        scheduler.shutdown()

    return app, scheduler


def get_esmerald_app2():
    @esmerald_route("/notes", methods=["GET"])
    async def list_notes(request: Request) -> EsmeraldJSONResponse:
        return EsmeraldJSONResponse([])

    app = Esmerald(
        routes=[Gateway(handler=list_notes)],
        enable_scheduler=True,
        scheduler_config=AsynczConfig(tasks={}, scheduler_class=AsyncIOScheduler),
    )
    scheduler = app.scheduler_config.handler

    return app, scheduler


@pytest.mark.parametrize(
    "loggers_class_string,loggers_class",
    [
        ["asyncz.schedulers.base:ClassicLogging", ClassicLogging],
        ["asyncz.schedulers.base:LoguruLogging", LoguruLogging],
    ],
    ids=["ClassicLogging", "LoguruLogging"],
)
@pytest.mark.parametrize(
    "get_app",
    [
        get_starlette_app,
        get_asgi_app,
        get_asgi_app2,
        get_lilya_app,
        get_lilya_start_shutdown_app,
        get_esmerald_app,
        get_esmerald_app2,
    ],
)
def test_integrations(get_app, loggers_class_string, loggers_class):
    app, scheduler = get_app()
    scheduler.setup(loggers_class=loggers_class_string)
    assert isinstance(scheduler.loggers, loggers_class)
    dummy_job_called = 0
    async_dummy_job_called = 0

    # better use real fns here for checking all behavior, like retrieving name
    def dummy_job():
        nonlocal dummy_job_called
        dummy_job_called += 1

    scheduler.add_task(dummy_job)
    with pytest.warns(DeprecationWarning):
        scheduler.add_task(fn=dummy_job)

    assert dummy_job_called == 0

    async def async_dummy_job():
        nonlocal async_dummy_job_called
        async_dummy_job_called += 1

    assert async_dummy_job_called == 0

    scheduler.add_task(async_dummy_job)
    with pytest.warns(DeprecationWarning):
        scheduler.add_task(fn=async_dummy_job)

    with TestClient(app) as client:
        assert scheduler.running
        # Ensure sessions are isolated
        response = client.get("/notes")
        assert response.status_code == 200
        assert response.json() == []
        # fix CancelledError, by giving scheduler more time to send the tasks to the  pool
        # if the pool is closed, newly submitted tasks are cancelled
        time.sleep(0.01)

    assert not scheduler.running
    assert dummy_job_called == 2
    assert async_dummy_job_called == 2
