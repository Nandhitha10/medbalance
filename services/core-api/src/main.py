"""Core API Service entrypoint."""

from fastapi import FastAPI
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures

from src.routers import (
    audit,
    custody,
    events,
    lots,
    master,
    orders,
    plans,
    positions,
    provenance,
)


def build_app() -> FastAPI:
    app = create_app(name="core-api", title="MedBalance Core API")
    settings = get_settings()

    if settings.USE_FIXTURES:
        fixtures.serve(app, "core-api")
    else:
        all_routers = [
            master.router,
            lots.router,
            positions.router,
            plans.router,
            orders.router,
            custody.router,
            audit.router,
            provenance.router,
            events.router,
        ]
        for r in all_routers:
            app.include_router(r)
            app.include_router(r, prefix="/api/core")

    return app


app = build_app()
