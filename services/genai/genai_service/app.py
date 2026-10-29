"""Application factory for GenAI service."""

from typing import Optional
from fastapi import FastAPI
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures
from genai_service.routers.llm import router as llm_router


def build_app(use_fixtures: Optional[bool] = None) -> FastAPI:
    """Build and configure GenAI FastAPI application."""
    app = create_app(name="genai", title="MedBalance GenAI Gateway")
    settings = get_settings()

    should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures

    if should_use_fixtures:
        fixtures.serve(app, "genai")
    else:
        app.include_router(llm_router)
        app.include_router(llm_router, prefix="/api/genai")

    return app


app = build_app()
