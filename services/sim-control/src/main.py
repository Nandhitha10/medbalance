"""Sim-Control Service entrypoint: clock, scenarios, signals, and cluster reset."""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from medbal_common.fastapi_base import create_app
from medbal_common.http import create_client
from medbal_common.settings import get_settings
from medbal_common import fixtures

try:
    from sim_control.clock import clock
    from sim_control.scenarios import scenario_manager
except ImportError:
    from src.clock import clock
    from src.scenarios import scenario_manager

logger = logging.getLogger(__name__)


class ClockSpeedPayload(BaseModel):
    speed: float = Field(ge=0.1, le=100.0, description="Clock speed multiplier")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background clock advancement loop on app launch."""
    task = asyncio.create_task(clock.run_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def build_app() -> FastAPI:
    settings = get_settings()
    app = create_app(
        name="sim-control",
        title="MedBalance Simulation Control",
        lifespan=lifespan,
    )

    if settings.USE_FIXTURES:
        fixtures.serve(app, "sim-control")
        return app

    @app.get("/clock", response_model=Dict[str, Any])
    def get_clock() -> Dict[str, Any]:
        """Get current simulation clock state."""
        return clock.get_state()

    @app.post("/clock/start", response_model=Dict[str, Any])
    def start_clock() -> Dict[str, Any]:
        """Start or resume simulation clock."""
        clock.start()
        return {"status": "started", "is_running": True}

    @app.post("/clock/pause", response_model=Dict[str, Any])
    def pause_clock() -> Dict[str, Any]:
        """Pause simulation clock."""
        clock.pause()
        return {"status": "paused", "is_running": False}

    @app.post("/clock/speed", response_model=Dict[str, Any])
    def set_clock_speed(payload: ClockSpeedPayload) -> Dict[str, Any]:
        """Set simulation clock speed multiplier."""
        clock.set_speed(payload.speed)
        return {"status": "updated", "speed": payload.speed}

    @app.get("/scenarios", response_model=List[Dict[str, Any]])
    def get_scenarios() -> List[Dict[str, Any]]:
        """List available simulation scenarios and active status."""
        return scenario_manager.get_scenarios_list()

    @app.post("/scenario/{name}", response_model=Dict[str, Any])
    @app.post("/scenarios/{name}", response_model=Dict[str, Any])
    async def apply_scenario(name: str) -> Dict[str, Any]:
        """Apply and activate a simulation scenario shock."""
        try:
            sc = await scenario_manager.activate_scenario(name)
            return {"status": "activated", "scenario": sc.name}
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

    @app.get("/signals", response_model=List[Dict[str, Any]])
    def get_signals() -> List[Dict[str, Any]]:
        """List active IDSP-style epidemiological and infrastructure signals."""
        return scenario_manager.get_signals_feed()

    @app.post("/reset", response_model=Dict[str, Any])
    async def reset_simulation(seed: int = Query(42, description="Simulation seed")) -> Dict[str, Any]:
        """Reset simulation clock, scenarios, and instruct hospital nodes to reload ground truth."""
        clock.reset()
        scenario_manager.reset(seed=seed)

        # Broadcast reset to hospital instances (H1..H4) concurrently
        hospital_urls = [
            os.getenv("SIM_HOSPITAL_H1_URL", "http://sim-hospital-h1:8101"),
            os.getenv("SIM_HOSPITAL_H2_URL", "http://sim-hospital-h2:8102"),
            os.getenv("SIM_HOSPITAL_H3_URL", "http://sim-hospital-h3:8103"),
            os.getenv("SIM_HOSPITAL_H4_URL", "http://sim-hospital-h4:8104"),
        ]

        async def _notify(url: str):
            try:
                async with create_client(timeout=0.3) as client:
                    await client.post(f"{url}/reset?seed={seed}")
            except Exception as exc:
                logger.debug(f"Hospital reset notice for {url}: {exc}")

        await asyncio.gather(*[_notify(u) for u in hospital_urls], return_exceptions=True)

        return {
            "status": "reset",
            "seed": seed,
            "reset_time": clock.current_sim_time.isoformat(),
        }

    return app


app = build_app()
