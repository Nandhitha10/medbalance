"""Unit and integration tests for cold chain excursion detection and state machine."""

from datetime import datetime, timedelta
import pytest
from httpx import ASGITransport, AsyncClient

from medbal_common.clock import KOLKATA_TZ
from coldchain.state_machine import ColdChainManager, DeviceStateMachine, DeviceState, MIN_SAFE_TEMP_C, MAX_SAFE_TEMP_C
from coldchain.main import build_app


def test_state_machine_ok_to_warning_to_excursion():
    """Verify OK -> WARNING (1 bad reading) -> EXCURSION (3 consecutive bad readings)."""
    sm = DeviceStateMachine(device_id="DEV-CV-02", assigned_to="CV-02", device_type="vehicle")
    assert sm.state == DeviceState.OK

    base_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # 1. Normal reading -> stays OK, no alert
    alert1 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 4.5, "ts": base_time.isoformat()})
    assert sm.state == DeviceState.OK
    assert alert1 is None

    # 2. First reading out of range (9.0 °C) -> WARNING, no alert
    t2 = base_time + timedelta(seconds=5)
    alert2 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 9.0, "ts": t2.isoformat()})
    assert sm.state == DeviceState.WARNING
    assert alert2 is None
    assert sm.consecutive_bad_count == 1

    # 3. Second consecutive bad reading (9.4 °C) -> still WARNING, no alert
    t3 = base_time + timedelta(seconds=10)
    alert3 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 9.4, "ts": t3.isoformat()})
    assert sm.state == DeviceState.WARNING
    assert alert3 is None
    assert sm.consecutive_bad_count == 2

    # 4. Third consecutive bad reading (10.1 °C) -> EXCURSION! Alert published ONCE.
    t4 = base_time + timedelta(seconds=15)
    alert4 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 10.1, "ts": t4.isoformat()})
    assert sm.state == DeviceState.EXCURSION
    assert alert4 is not None
    assert alert4["event_type"] == "coldchain.alert"
    assert alert4["data"]["severity"] == "CRITICAL"
    assert alert4["data"]["device_id"] == "DEV-CV-02"
    assert alert4["data"]["vehicle_id"] == "CV-02"
    assert alert4["data"]["temperature_c"] == 10.1
    assert "RTE-W0-H2" in alert4["data"]["route_ids"]

    # 5. Fourth & Fifth consecutive bad readings (10.8 °C, 11.2 °C) -> Stays EXCURSION, NO duplicate alert!
    t5 = base_time + timedelta(seconds=20)
    alert5 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 10.8, "ts": t5.isoformat()})
    assert sm.state == DeviceState.EXCURSION
    assert alert5 is None  # Exactly once per transition

    t6 = base_time + timedelta(seconds=25)
    alert6 = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 11.2, "ts": t6.isoformat()})
    assert sm.state == DeviceState.EXCURSION
    assert alert6 is None


def test_state_machine_recovery_after_6_consecutive_good_readings():
    """Verify EXCURSION -> RECOVERED requires exactly 6 consecutive good readings."""
    sm = DeviceStateMachine(device_id="DEV-CV-02", assigned_to="CV-02", device_type="vehicle")
    base_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # Force device into EXCURSION
    for i in range(3):
        sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 10.0 + i, "ts": (base_time + timedelta(seconds=i*5)).isoformat()})
    assert sm.state == DeviceState.EXCURSION

    # Feed 5 good readings (within 2-8 °C): must stay in EXCURSION
    rec_start = base_time + timedelta(seconds=30)
    for i in range(5):
        t = rec_start + timedelta(seconds=i*5)
        alert = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 4.5, "ts": t.isoformat()})
        assert sm.state == DeviceState.EXCURSION
        assert alert is None

    # 6th good reading -> Transitions to RECOVERED and publishes recovery alert!
    t_6th = rec_start + timedelta(seconds=25)
    alert_rec = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 4.6, "ts": t_6th.isoformat()})
    assert sm.state == DeviceState.RECOVERED
    assert alert_rec is not None
    assert alert_rec["event_type"] == "coldchain.alert"
    assert alert_rec["data"]["severity"] == "NORMAL"
    assert alert_rec["data"]["device_id"] == "DEV-CV-02"

    # Subsequent good reading -> stays in safe condition, NO duplicate recovery alert
    t_7th = rec_start + timedelta(seconds=30)
    alert_dup = sm.process_reading({"device_id": "DEV-CV-02", "temp_c": 4.4, "ts": t_7th.isoformat()})
    assert alert_dup is None


def test_door_open_timer_triggers_excursion():
    """Verify door open > 2 min (120 s) directly triggers EXCURSION."""
    sm = DeviceStateMachine(device_id="DEV-CV-01", assigned_to="CV-01", device_type="vehicle")
    base_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # Normal reading, door closed
    sm.process_reading({"device_id": "DEV-CV-01", "temp_c": 4.5, "door_open": False, "ts": base_time.isoformat()})
    assert sm.state == DeviceState.OK

    # Door opened at t0
    sm.door_open_since = 1000.0
    # Simulate time passed: now is 1150.0 (150s later > 120s)
    # We can test by setting door_open=True with door_open_since > 120s ago
    import time
    sm.door_open_since = time.monotonic() - 125.0  # 125 seconds ago
    alert_door = sm.process_reading({"device_id": "DEV-CV-01", "temp_c": 4.8, "door_open": True, "ts": (base_time + timedelta(seconds=125)).isoformat()})
    assert sm.state == DeviceState.EXCURSION
    assert alert_door is not None
    assert alert_door["data"]["severity"] == "CRITICAL"


def test_warning_resolved_by_normal_reading():
    """Verify a single transient spike to WARNING resolves back to OK on next good reading."""
    sm = DeviceStateMachine(device_id="DEV-CV-01", assigned_to="CV-01", device_type="vehicle")
    base_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

    # 1. First bad reading -> WARNING
    sm.process_reading({"device_id": "DEV-CV-01", "temp_c": 8.5, "ts": base_time.isoformat()})
    assert sm.state == DeviceState.WARNING
    assert sm.consecutive_bad_count == 1

    # 2. Next reading is good (4.2 °C) -> returns to OK, bad count reset
    t2 = base_time + timedelta(seconds=5)
    sm.process_reading({"device_id": "DEV-CV-01", "temp_c": 4.2, "ts": t2.isoformat()})
    assert sm.state == DeviceState.OK
    assert sm.consecutive_bad_count == 0


@pytest.fixture
def coldchain_app(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("MQTT_URL", "mqtt://localhost:1883")
    monkeypatch.setenv("CORE_API_URL", "http://localhost:8001")
    return build_app()


@pytest.mark.asyncio
async def test_coldchain_api_status_and_telemetry(coldchain_app):
    """Test GET /status and GET /devices/{id}/telemetry endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=coldchain_app), base_url="http://test"
    ) as client:
        # GET /status
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        status_data = r_status.json()
        assert "monitored_vehicles_count" in status_data
        assert "monitored_facilities_count" in status_data
        assert "system_status" in status_data
        assert len(status_data["devices"]) >= 5

        # Inject telemetry
        r_inject = await client.post("/telemetry", json={
            "device_id": "DEV-CV-01",
            "assigned_to": "CV-01",
            "temp_c": 4.3,
            "door_open": False,
            "battery": 92,
            "humidity_percent": 52.0,
            "ts": "2026-11-01T08:05:00+05:30",
        })
        assert r_inject.status_code == 200
        assert r_inject.json()["status"] == "processed"

        # GET /devices/DEV-CV-01/telemetry
        r_telem = await client.get("/devices/DEV-CV-01/telemetry")
        assert r_telem.status_code == 200
        history = r_telem.json()
        assert len(history) >= 1
        assert history[-1]["device_id"] == "DEV-CV-01"
        assert history[-1]["temperature_c"] == 4.3


@pytest.mark.asyncio
async def test_end_to_end_fridge_failure_to_excursion_alert(coldchain_app):
    """Verify fridge_failure excursion sequence triggers CRITICAL system status and recovery."""
    async with AsyncClient(
        transport=ASGITransport(app=coldchain_app), base_url="http://test"
    ) as client:
        # Feed 3 excursion telemetry packets for DEV-CV-02 (drift to 11.4 C)
        for i in range(3):
            r = await client.post("/telemetry", json={
                "device_id": "DEV-CV-02",
                "assigned_to": "CV-02",
                "temp_c": 11.4,
                "door_open": False,
                "battery": 90,
                "ts": f"2026-11-01T08:1{i}:00+05:30",
            })
            assert r.status_code == 200

        # Check /status: CV-02 should be in EXCURSION and system_status CRITICAL
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        data = r_status.json()
        assert data["system_status"] == "CRITICAL"
        assert data["active_excursions_count"] >= 1
        cv02_entry = [d for d in data["devices"] if d["device_id"] == "DEV-CV-02" or d["assigned_to"] == "CV-02"][0]
        assert cv02_entry["status"] == "EXCURSION"

        # Now feed 6 good readings (4.5 C) to verify RECOVERED transition
        for j in range(6):
            r_rec = await client.post("/telemetry", json={
                "device_id": "DEV-CV-02",
                "assigned_to": "CV-02",
                "temp_c": 4.5,
                "door_open": False,
                "battery": 90,
                "ts": f"2026-11-01T08:2{j}:00+05:30",
            })
            assert r_rec.status_code == 200

        # Check /status after recovery
        r_status_after = await client.get("/status")
        data_after = r_status_after.json()
        assert data_after["active_excursions_count"] == 0
        cv02_after = [d for d in data_after["devices"] if d["device_id"] == "DEV-CV-02" or d["assigned_to"] == "CV-02"][0]
        assert cv02_after["status"] in ("RECOVERED", "OK")

