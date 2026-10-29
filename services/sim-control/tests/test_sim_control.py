"""Integration tests for sim-control: clock, scenarios, and signal broadcasts."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def sim_control_app(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("SIM_START_DATE", "2026-11-01T08:00:00+05:30")
    monkeypatch.setenv("SIM_DAY_SECONDS", "30")
    from sim_control.main import build_app
    from sim_control.clock import clock
    from sim_control.scenarios import scenario_manager

    clock.reset("2026-11-01T08:00:00+05:30")
    scenario_manager.reset(seed=42)
    return build_app()


@pytest.mark.asyncio
async def test_clock_lifecycle(sim_control_app):
    """Verify clock status, pause, start, and speed adjustments."""
    async with AsyncClient(
        transport=ASGITransport(app=sim_control_app), base_url="http://test"
    ) as client:
        # GET /clock
        r_clock = await client.get("/clock")
        assert r_clock.status_code == 200
        data = r_clock.json()
        assert data["date"] == "2026-11-01"
        assert data["today"] == "2026-11-01"
        assert data["running"] is True
        assert data["speed"] == 1.0
        assert data["day_index"] == 0

        # POST /clock/pause
        r_pause = await client.post("/clock/pause")
        assert r_pause.status_code == 200
        assert r_pause.json()["is_running"] is False

        # POST /clock/speed
        r_speed = await client.post("/clock/speed", json={"speed": 5.0})
        assert r_speed.status_code == 200
        assert r_speed.json()["speed"] == 5.0

        # POST /clock/start
        r_start = await client.post("/clock/start")
        assert r_start.status_code == 200
        assert r_start.json()["is_running"] is True


@pytest.mark.asyncio
async def test_scenarios_and_signals_feed(sim_control_app):
    """Verify scenario activation and epidemiological signal generation."""
    async with AsyncClient(
        transport=ASGITransport(app=sim_control_app), base_url="http://test"
    ) as client:
        # GET /scenarios
        r_sc = await client.get("/scenarios")
        assert r_sc.status_code == 200
        scenarios = r_sc.json()
        scenario_names = [s["name"] for s in scenarios]
        assert "baseline" in scenario_names
        assert "dengue_outbreak" in scenario_names
        assert "fridge_failure" in scenario_names
        assert "bad_data" in scenario_names
        assert "ilr_repaired" in scenario_names
        assert "road_closure" in scenario_names
        assert "td_campaign" in scenario_names

        # Initially, signals feed has no shock signals (only baseline active)
        r_sig_init = await client.get("/signals")
        assert r_sig_init.status_code == 200
        assert len(r_sig_init.json()) == 0

        # POST /scenario/dengue_outbreak
        r_act = await client.post("/scenario/dengue_outbreak")
        assert r_act.status_code == 200
        assert r_act.json()["status"] == "activated"

        # Check signals feed reflects dengue outbreak
        r_sig = await client.get("/signals")
        assert r_sig.status_code == 200
        signals = r_sig.json()
        assert len(signals) >= 1
        dengue_sig = [s for s in signals if s["type"] == "OUTBREAK"][0]
        assert dengue_sig["facility"] == "H3"
        assert "ORS-20" in dengue_sig["drugs_affected"]
        assert dengue_sig["multiplier"] == 4.0
        assert "Dengue" in dengue_sig["text"]


@pytest.mark.asyncio
async def test_reset_simulation(sim_control_app):
    """Verify reset returns clock and scenarios to initial baseline."""
    async with AsyncClient(
        transport=ASGITransport(app=sim_control_app), base_url="http://test"
    ) as client:
        # Activate scenario first
        await client.post("/scenario/fridge_failure")
        signals = (await client.get("/signals")).json()
        assert len(signals) == 1

        # Reset
        r_reset = await client.post("/reset?seed=123")
        assert r_reset.status_code == 200
        assert r_reset.json()["status"] == "reset"
        assert r_reset.json()["seed"] == 123

        # Signals feed should now be cleared
        signals_after = (await client.get("/signals")).json()
        assert len(signals_after) == 0

        # Clock should be reset
        clock_data = (await client.get("/clock")).json()
        assert clock_data["day_index"] == 0
        assert clock_data["date"] == "2026-11-01"
