"""FastAPI application factory for forecast service."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Optional
from fastapi import FastAPI

from medbal_common.bus import get_redis_client
from medbal_common.fastapi_base import create_app
from medbal_common.settings import get_settings
from medbal_common import fixtures
from forecast.routers.forecast import router as forecast_router
from forecast.service import run_all_forecasts

logger = logging.getLogger(__name__)


async def _clock_tick_consumer():
    """Background listener for clock.tick and signal events to refresh forecasts."""
    try:
        redis = get_redis_client()
        await asyncio.wait_for(redis.ping(), timeout=0.1)
    except Exception:
        logger.debug("Redis unavailable; clock tick consumer inactive")
        return

    last_id = "$"
    while True:
        try:
            streams = await asyncio.wait_for(
                redis.xread({"clock.tick": last_id}, count=1, block=2000),
                timeout=3.0,
            )
            if streams:
                for stream_name, messages in streams:
                    for msg_id, data in messages:
                        last_id = msg_id
                        logger.info("Received clock.tick; re-evaluating consumption forecasts")
                        await run_all_forecasts()
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            await asyncio.sleep(2.0)


def build_app(use_fixtures: Optional[bool] = None) -> FastAPI:
    """Build and configure forecast FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        consumer_task = None
        settings = get_settings()
        should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures
        if not should_use_fixtures:
            consumer_task = asyncio.create_task(_clock_tick_consumer())
        yield
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

    app = create_app(name="forecast", title="MedBalance Forecast Service", lifespan=lifespan)
    settings = get_settings()
    should_use_fixtures = settings.USE_FIXTURES if use_fixtures is None else use_fixtures

    if should_use_fixtures:
        fixtures.serve(app, "forecast")
    else:
        app.include_router(forecast_router)
        app.include_router(forecast_router, prefix="/api/forecast")

    return app


app = build_app()
