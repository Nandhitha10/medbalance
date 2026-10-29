"""Test that services serve contracts/fixtures when USE_FIXTURES=1."""

import os
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def enable_fixtures_env(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "1")


@pytest.mark.asyncio
async def test_optimizer_serves_plan_demo(monkeypatch):
    """Verify that optimizer app serves the fixture plan at /plan/demo when USE_FIXTURES=1."""
    monkeypatch.setenv("USE_FIXTURES", "1")
    # Re-import or create app with fixtures
    from medbal_common.fastapi_base import create_app
    from medbal_common import fixtures

    app = create_app(name="optimizer")
    fixtures.serve(app, "optimizer")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Check /health
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["service"] == "optimizer"

        # Check /plan/demo
        plan_resp = await client.get("/plan/demo")
        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert plan["id"] == "PLAN-20261101-01"
        assert len(plan["orders"]) == 6
        insulin = [o for o in plan["orders"] if o["drug_code"] == "INS-REG"][0]
        assert insulin["lot_quantity"] == 50
        assert insulin["usable_quantity"] == 28


@pytest.mark.asyncio
async def test_core_api_serves_fixtures(monkeypatch):
    """Verify core-api serves facilities, snapshot, and health."""
    monkeypatch.setenv("USE_FIXTURES", "1")
    from medbal_common.fastapi_base import create_app
    from medbal_common import fixtures

    app = create_app(name="core-api")
    fixtures.serve(app, "core-api")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Check health
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "core-api"

        # Check facilities
        facs = await client.get("/facilities")
        assert facs.status_code == 200
        assert len(facs.json()) >= 4

        # Check snapshot
        snap = await client.get("/snapshot")
        assert snap.status_code == 200
        data = snap.json()
        assert "facilities" in data
        assert "drugs" in data
        assert "lots" in data
