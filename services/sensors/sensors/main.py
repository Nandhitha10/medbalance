"""Sensors Service entrypoint: simulated MQTT temperature telemetry stream."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from medbal_common.fastapi_base import create_app

try:
    from sensors.simulator import sensor_simulator, SensorSimulator
except ImportError:
    from src.simulator import sensor_simulator, SensorSimulator

logger = logging.getLogger(__name__)


class FaultPayload(BaseModel):
    target: str = Field(description="Vehicle or device ID, e.g. CV-02 or DEV-CV-02")
    temperature_c: float = Field(default=11.4, description="Target excursion temperature")
    drift_seconds: float = Field(default=60.0, description="Drift duration in seconds")


class DoorPayload(BaseModel):
    target: str = Field(description="Vehicle or device ID, e.g. CV-01 or DEV-CV-01")
    door_open: bool = Field(description="True to open door, False to close")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background MQTT sensor publication loop."""
    task = asyncio.create_task(sensor_simulator.run_loop(interval_seconds=5.0))
    yield
    sensor_simulator.is_running = False
    sensor_simulator.stop_mqtt()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def build_app() -> FastAPI:
    """Build and configure the sensors simulation application."""
    app = create_app(name="sensors", lifespan=lifespan)

    @app.get("/status", response_model=Dict[str, Any])
    def get_status() -> Dict[str, Any]:
        """Get simulation status and list of monitored sensors."""
        devices_status = []
        for dev in sensor_simulator.devices.values():
            reading = dev.read_telemetry()
            devices_status.append(reading)

        return {
            "status": "running" if sensor_simulator.is_running else "ready",
            "monitored_devices_count": len(sensor_simulator.devices),
            "devices": devices_status,
        }

    @app.get("/devices", response_model=List[Dict[str, Any]])
    def get_devices() -> List[Dict[str, Any]]:
        """List all simulated devices and current telemetry values."""
        return [dev.read_telemetry() for dev in sensor_simulator.devices.values()]

    @app.post("/simulate/fault", response_model=Dict[str, Any])
    def trigger_simulated_fault(payload: FaultPayload) -> Dict[str, Any]:
        """Manually trigger a heating fault drift on a vehicle or device."""
        dev = sensor_simulator.get_device_by_target(payload.target)
        if dev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device or target '{payload.target}' not found",
            )
        dev.trigger_fault(target_temp=payload.temperature_c, drift_seconds=payload.drift_seconds)
        return {
            "status": "fault_triggered",
            "device_id": dev.device_id,
            "assigned_to": dev.assigned_to,
            "target_temperature_c": payload.temperature_c,
            "drift_seconds": payload.drift_seconds,
        }

    @app.post("/simulate/repair", response_model=Dict[str, Any])
    def trigger_simulated_repair(target: str = "H4") -> Dict[str, Any]:
        """Clear faults or mark offline equipment repaired."""
        dev = sensor_simulator.get_device_by_target(target)
        if dev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device or target '{target}' not found",
            )
        dev.clear_fault()
        if dev.is_offline:
            dev.set_offline(False)
        return {
            "status": "repaired",
            "device_id": dev.device_id,
            "assigned_to": dev.assigned_to,
        }

    @app.post("/simulate/door", response_model=Dict[str, Any])
    def toggle_door(payload: DoorPayload) -> Dict[str, Any]:
        """Toggle sensor container door open state."""
        dev = sensor_simulator.get_device_by_target(payload.target)
        if dev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device or target '{payload.target}' not found",
            )
        dev.set_door_open(payload.door_open)
        return {
            "status": "door_updated",
            "device_id": dev.device_id,
            "door_open": dev.door_open,
        }

    return app


app = build_app()
