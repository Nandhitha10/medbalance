"""FastAPI application for MedBalance Ingest-AI."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict
from fastapi import FastAPI

from medbal_common import fixtures
from medbal_common.bus import start_stream_consumer_task, stop_stream_consumer_task
from medbal_common.db import session_scope
from medbal_common.fastapi_base import create_app
from ingest_ai.routers import ingest, pull, reports, reviews
from ingest_ai.service import IngestService

logger = logging.getLogger("ingest-ai")


async def handle_clock_tick(msg_id: str, data: Dict[str, Any]) -> None:
    """Handle clock.tick event by triggering active polling of H1 and H2."""
    try:
        with session_scope() as session:
            service = IngestService(session)
            await service.poll_hospitals()
    except Exception as e:
        logger.debug("Error during clock.tick poll: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start clock.tick stream listener
    consumer_task = None
    stop_event = None
    try:
        consumer_task, stop_event = start_stream_consumer_task(
            stream="clock.tick",
            group="ingest-ai-group",
            consumer="ingest-ai-1",
            handler=handle_clock_tick,
            block_ms=500,
        )
    except Exception as e:
        logger.debug("Could not start clock.tick consumer: %s", e)

    yield

    if consumer_task and stop_event:
        try:
            await stop_stream_consumer_task(consumer_task, stop_event, timeout=1.0)
        except Exception:
            pass


def build_app() -> FastAPI:
    app = create_app(
        name="ingest-ai",
        title="MedBalance Ingest AI",
        lifespan=lifespan,
    )

    app.include_router(ingest.router)
    app.include_router(pull.router)
    app.include_router(reports.router)
    app.include_router(reviews.router)

    fixtures.serve(app, "ingest-ai")
    return app


app = build_app()
