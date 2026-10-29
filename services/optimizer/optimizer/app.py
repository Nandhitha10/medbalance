"""FastAPI application factory for optimizer service."""

from typing import Optional
from fastapi import FastAPI
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures
from optimizer.routers.plan import router as plan_router


def build_app(use_fixtures: Optional[bool] = None) -> FastAPI:
    """Build and configure optimizer FastAPI application."""
    app = create_app(name="optimizer", title="MedBalance Optimizer Service")
    settings = get_settings()

    should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures

    if should_use_fixtures:
        fixtures.serve(app, "optimizer")
    else:
        app.include_router(plan_router)
        app.include_router(plan_router, prefix="/api/optimizer")

    return app


app = build_app()
