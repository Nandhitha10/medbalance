"""API endpoint integration tests for Forecast Service."""

import pytest
from fastapi.testclient import TestClient

from forecast.app import build_app


@pytest.fixture
def client():
    app = build_app(use_fixtures=False)
    return TestClient(app)


def test_forecast_run_endpoint(client):
    """Test POST /forecast/run generates forecasts."""
    resp = client.post("/forecast/run", json={"target_days": 14})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["forecasts_generated"] > 0
    assert len(data["forecasts"]) > 0

    first = data["forecasts"][0]
    assert "facility_id" in first
    assert "drug_code" in first
    assert "effective_daily_rate" in first
    assert "projected_consumption" in first
    assert first["effective_daily_rate"] > 0
    assert first["projected_consumption"] > 0


def test_get_forecast_endpoint(client):
    """Test GET /forecast retrieves stored forecasts with optional query filters."""
    # Ensure forecasts exist
    client.post("/forecast/run", json={"target_days": 14})

    resp = client.get("/forecast?facility=H3&drug=ORS-20")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    fc = items[0]
    assert fc["facility_id"] == "H3"
    assert fc["drug_code"] == "ORS-20"
    assert fc["effective_daily_rate"] > 0
    assert fc["target_days"] == 14


def test_backtest_endpoint(client):
    """Test GET /forecast/backtest returns MAPE and RMSE metrics."""
    resp = client.get("/forecast/backtest?facility=H3&drug=ORS-20&window_days=14")
    assert resp.status_code == 200
    report = resp.json()
    assert report["facility_id"] == "H3"
    assert report["drug_code"] == "ORS-20"
    assert report["evaluation_window_days"] == 14
    assert "mape_percent" in report
    assert "baseline_mape_percent" in report
    assert "rmse" in report
    assert "model_used" in report
