"""Application factory for GenAI service."""

from contextlib import asynccontextmanager
import logging
from typing import Optional
from uuid import uuid4
from fastapi import FastAPI
from medbal_common.bus import start_stream_consumer_task, stop_stream_consumer_task
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures
from genai_service.events import handle_plan_event
from genai_service.routers.llm import router as llm_router
from genai_service.routers.narrate import router as narrate_router
from genai_service.routers.documents import router as documents_router
from genai_service.routers.copilot import router as copilot_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for GenAI: starts batch narration listener on plan events."""
    consumer_tasks = []
    stop_events = []
    settings = get_settings()

    if settings.REDIS_URL:
        try:
            for stream_name in ("plan.completed", "plan.revised"):
                task, stop_event = start_stream_consumer_task(
                    stream=stream_name,
                    group="genai-batch-narration",
                    consumer=f"genai-{uuid4().hex[:4]}",
                    handler=handle_plan_event,
                )
                consumer_tasks.append(task)
                stop_events.append(stop_event)
            logger.info("GenAI batch narration stream listeners started")
        except Exception as exc:
            logger.debug(f"GenAI Redis stream consumer could not be started: {exc}")

    yield

    for task, stop_event in zip(consumer_tasks, stop_events):
        try:
            await stop_stream_consumer_task(task, stop_event)
        except Exception:
            pass


def build_app(use_fixtures: Optional[bool] = None) -> FastAPI:
    """Build and configure GenAI FastAPI application."""
    app = create_app(name="genai", title="MedBalance GenAI Gateway", lifespan=lifespan)
    settings = get_settings()

    should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures

    if should_use_fixtures:
        fixtures.serve(app, "genai")
    else:
        for r in (llm_router, narrate_router, documents_router, copilot_router):
            app.include_router(r)
            app.include_router(r, prefix="/api/genai")

    return app


app = build_app()

