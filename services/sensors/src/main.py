"""Sensors simulation service entrypoint."""

from medbal_common.fastapi_base import create_app

app = create_app(name="sensors", title="MedBalance Simulated Sensors")


@app.get("/telemetry")
async def telemetry():
    return {
        "status": "streaming",
        "active_sensors": 4,
        "protocol": "mqtt",
    }

