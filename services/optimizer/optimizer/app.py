"""FastAPI application factory for optimizer service with reactive cold-chain auto re-planning."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, Optional
from uuid import uuid4
from fastapi import FastAPI

from medbal_common.bus import start_stream_consumer_task, stop_stream_consumer_task
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures
from optimizer.auto_replan import trigger_auto_replan
from optimizer.routers.plan import router as plan_router
from optimizer.solver import _plans_store, run_planning_pipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for optimizer: starts background Redis consumer for coldchain.alert."""
    consumer_task = None
    stop_event = None
    settings = get_settings()

    if settings.REDIS_URL:
        try:
            async def handle_alert(msg_id: str, data: Dict[str, Any]):
                logger.info(f"Optimizer received coldchain.alert: {data}")
                alert_payload = data.get("data") if "data" in data else data
                await trigger_auto_replan(
                    alert_data=alert_payload,
                    plans_store=_plans_store,
                    run_planning_fn=run_planning_pipeline,
                )

            consumer_task, stop_event = start_stream_consumer_task(
                stream="coldchain.alert",
                group="optimizer-auto-replan",
                consumer=f"optimizer-{uuid4().hex[:4]}",
                handler=handle_alert,
            )
            logger.info("Optimizer: Coldchain excursion alert listener started")
        except Exception as e:
            logger.debug(f"Redis stream consumer could not be started: {e}")

    yield

    if consumer_task and stop_event:
        await stop_stream_consumer_task(consumer_task, stop_event)


def build_app(use_fixtures: Optional[bool] = None) -> FastAPI:
    """Build and configure optimizer FastAPI application."""
    settings = get_settings()
    should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures

    if should_use_fixtures:
        app = create_app(name="optimizer", title="MedBalance Optimizer Service")
        fixtures.serve(app, "optimizer")
    else:
        app = create_app(name="optimizer", title="MedBalance Optimizer Service", lifespan=lifespan)
        app.include_router(plan_router)
        app.include_router(plan_router, prefix="/api/optimizer")

    return app


app = build_app()

