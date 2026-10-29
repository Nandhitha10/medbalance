"""ColdChain Service entrypoint: temperature excursion detection, vehicle status, and sparklines."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status

from medbal_common.clock import KOLKATA_TZ, now as sim_now
from medbal_common.fastapi_base import create_app
from medbal_common import fixtures

try:
    from coldchain.mqtt_subscriber import coldchain_manager, coldchain_subscriber, ColdChainManager
except ImportError:
    from src.mqtt_subscriber import coldchain_manager, coldchain_subscriber, ColdChainManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start MQTT subscriber on app launch."""
    loop = asyncio.get_running_loop()
    coldchain_subscriber.start(loop=loop)
    yield
    coldchain_subscriber.stop()


def build_app() -> FastAPI:
    """Build and configure the coldchain service FastAPI application."""
    use_fixtures = os.getenv("USE_FIXTURES", "0").lower() in ("1", "true")

    if use_fixtures:
        app = create_app(name="coldchain")
        fixtures.serve(app, "coldchain")
        return app

    app = create_app(name="coldchain", lifespan=lifespan)

    @app.get("/status", response_model=Dict[str, Any])
    @app.get("/api/coldchain/status", response_model=Dict[str, Any])
    def get_status() -> Dict[str, Any]:
        """Get overall cold chain network health, monitored devices, and active excursions."""
        return coldchain_manager.get_status_summary()

    @app.get("/devices/{id}/telemetry", response_model=List[Dict[str, Any]])
    @app.get("/api/coldchain/devices/{id}/telemetry", response_model=List[Dict[str, Any]])
    def get_device_telemetry(
        id: str,
        since: Optional[str] = Query(None, description="ISO timestamp to filter telemetry history"),
    ) -> List[Dict[str, Any]]:
        """Retrieve recent telemetry history and sparklines for a specific sensor device or target."""
        dev = None
        if id in coldchain_manager.devices:
            dev = coldchain_manager.devices[id]
        else:
            for d in coldchain_manager.devices.values():
                if d.assigned_to == id:
                    dev = d
                    break

        if dev is None:
            # If not yet registered, return empty sparkline series
            return []

        history = list(dev.telemetry_history)
        if not history:
            # Seed at least 1 recent point if available
            if dev.latest_temp_c is not None:
                history = [{
                    "device_id": dev.device_id,
                    "timestamp": (dev.last_ping or sim_now()).isoformat(),
                    "temperature_c": dev.latest_temp_c,
                    "humidity_percent": dev.latest_humidity,
                    "battery_percent": dev.latest_battery,
                }]

        if since:
            try:
                dt_since = datetime.fromisoformat(since)
                if dt_since.tzinfo is None:
                    dt_since = dt_since.replace(tzinfo=KOLKATA_TZ)
                history = [
                    item for item in history
                    if datetime.fromisoformat(item["timestamp"]) >= dt_since
                ]
            except Exception:
                pass

        return history

    @app.post("/telemetry", response_model=Dict[str, Any])
    @app.post("/api/coldchain/telemetry", response_model=Dict[str, Any])
    async def inject_telemetry(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Directly inject a telemetry packet into the state machine (useful for tests and manual dispatch)."""
        await coldchain_subscriber.handle_telemetry(payload)
        device_id = payload.get("device_id", "UNKNOWN")
        dev = coldchain_manager.devices.get(device_id)
        current_state = dev.state.value if dev else "UNKNOWN"
        return {
            "status": "processed",
            "device_id": device_id,
            "current_state": current_state,
        }

    return app


app = build_app()
