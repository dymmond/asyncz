import contextlib
from unittest.mock import MagicMock

import pytest
from esmerald import Gateway, Request
from esmerald import JSONResponse as EsmeraldJSONResponse
from esmerald import route as esmerald_route
from esmerald.applications import Esmerald
from esmerald.contrib.schedulers.asyncz.config import AsynczConfig
from lilya.apps import Lilya
from lilya.middleware import DefineMiddleware
from lilya.responses import JSONResponse as LilyaJSONResponse
from lilya.routing import Path
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from asyncz.schedulers.base import BaseScheduler


class DummyScheduler(BaseScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "wakeup", MagicMock())

    def shutdown(self, wait=True):
        super().shutdown(wait)

    def wakeup(self): ...


def get_starlette_app():
    scheduler = DummyScheduler()

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
    scheduler = DummyScheduler()

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
    scheduler = DummyScheduler()

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
    scheduler = DummyScheduler()

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


def get_lilya_middleware_app():
    scheduler = DummyScheduler()

    async def list_notes(request: Request) -> LilyaJSONResponse:
        return LilyaJSONResponse([])

    app = Lilya(
        routes=[
            Path(
                "/notes",
                methods=["GET"],
                handler=list_notes,
                middleware=[
                    DefineMiddleware(scheduler.asgi()),
                ],
            )
        ]
    )

    return app, scheduler


def get_esmerald_app():
    scheduler = DummyScheduler()

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
        scheduler_config=AsynczConfig(tasks={}, scheduler_class=DummyScheduler),
    )
    scheduler = app.scheduler_config.handler

    return app, scheduler


@pytest.mark.parametrize(
    "get_app",
    [
        get_starlette_app,
        get_asgi_app,
        get_asgi_app2,
        get_lilya_app,
        get_lilya_middleware_app,
        get_esmerald_app,
        get_esmerald_app2,
    ],
)
def test_integrations(get_app):
    app, scheduler = get_app()

    with TestClient(app) as client:
        assert scheduler.running
        # Ensure sessions are isolated
        response = client.get("/notes")
        assert response.status_code == 200
        assert response.json() == []

    assert not scheduler.running
