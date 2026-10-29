"""Tests for FastAPI base application factory."""

import pytest
from httpx import ASGITransport, AsyncClient

from medbal_common.fastapi_base import create_app


@pytest.mark.asyncio
async def test_base_app_health():
    app = create_app(name="test-service")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "test-service"
        assert "timestamp" in data
