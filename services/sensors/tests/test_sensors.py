"""Unit and integration tests for simulated temperature sensor network."""

from datetime import datetime
import pytest
from httpx import ASGITransport, AsyncClient

from medbal_common.clock import KOLKATA_TZ
from sensors.simulator import SensorSimulator, SensorDevice
from sensors.main import build_app


def test_sensors_telemetry_normal_and_offline():
    """Verify normal sensors generate 4.5 +/- 1 C and H4 begins offline."""
    sim = SensorSimulator()
    dt = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # 1. Normal vehicle sensor (CV-01)
    cv01 = sim.devices["DEV-CV-01"]
    reading = cv01.read_telemetry(dt)
    assert reading["device_id"] == "DEV-CV-01"
    assert reading["assigned_to"] == "CV-01"
    assert reading["status"] == "OK"
    assert 2.0 <= reading["temp_c"] <= 8.0

    # 2. Facility sensor H4: starts offline per CLAUDE.md ("ILR under repair")
    h4 = sim.devices["DEV-ILR-H4"]
    h4_reading = h4.read_telemetry(dt)
    assert h4_reading["device_id"] == "DEV-ILR-H4"
    assert h4_reading["status"] == "offline"
    assert h4_reading["temp_c"] is None


def test_sensors_fault_mode_drifts_to_11c():
    """Verify fault mode drifts temperature up towards ~11.4 C over 60s."""
    cv02 = SensorDevice("DEV-CV-02", assigned_to="CV-02", base_temp_c=4.5)
    dt = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # Normal before fault
    init_reading = cv02.read_telemetry(dt)
    assert init_reading["status"] == "OK"
    assert init_reading["temp_c"] < 7.0

    # Trigger fault with short drift duration for testing (0.1s)
    cv02.trigger_fault(target_temp=11.4, drift_seconds=0.05)
    import time
    time.sleep(0.06)

    # Reading after drift
    fault_reading = cv02.read_telemetry(dt)
    assert fault_reading["status"] in ("WARNING", "EXCURSION")
    assert fault_reading["temp_c"] >= 10.0


def test_sensors_h4_repair():
    """Verify repairing H4 ILR puts it online in normal operating range."""
    h4 = SensorDevice("DEV-ILR-H4", assigned_to="H4", is_offline=True)
    dt = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    assert h4.read_telemetry(dt)["status"] == "offline"

    # Repair
    h4.set_offline(False)
    reading = h4.read_telemetry(dt)
    assert reading["status"] == "OK"
    assert 2.0 <= reading["temp_c"] <= 8.0


@pytest.fixture
def sensors_app():
    return build_app()


@pytest.mark.asyncio
async def test_sensors_api_endpoints(sensors_app):
    """Test /status, /devices, /simulate/fault, and /simulate/repair endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=sensors_app), base_url="http://test"
    ) as client:
        # GET /status
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        assert r_status.json()["monitored_devices_count"] >= 5

        # GET /devices
        r_devs = await client.get("/devices")
        assert r_devs.status_code == 200
        assert len(r_devs.json()) >= 5

        # POST /simulate/fault
        r_fault = await client.post("/simulate/fault", json={
            "target": "CV-02",
            "temperature_c": 11.2,
            "drift_seconds": 1.0,
        })
        assert r_fault.status_code == 200
        assert r_fault.json()["status"] == "fault_triggered"

        # POST /simulate/repair
        r_repair = await client.post("/simulate/repair?target=H4")
        assert r_repair.status_code == 200
        assert r_repair.json()["status"] == "repaired"
