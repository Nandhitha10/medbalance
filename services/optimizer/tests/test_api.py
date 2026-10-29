"""API endpoint tests for MedBalance Optimizer Service."""

import pytest
from fastapi.testclient import TestClient
from optimizer.app import build_app


@pytest.fixture
def client():
    app = build_app(use_fixtures=False)
    return TestClient(app)


def test_plan_run_and_retrieve_endpoints(client):
    """Test POST /plan/run and GET /plan/{id}."""
    resp = client.post("/plan/run", json={"mode": "live"})
    assert resp.status_code == 200
    plan = resp.json()
    assert "id" in plan or "plan_id" in plan
    plan_id = plan.get("id") or plan.get("plan_id")
    assert plan["status"] == "COMPLETED"
    assert "orders" in plan
    assert "metrics" in plan

    # Verify no infeasible order exists in the output
    for order in plan["orders"]:
        assert order["quantity"] > 0
        assert order["source_facility_id"] != order["destination_facility_id"]

    # Test GET /plan/{id}
    resp_get = client.get(f"/plan/{plan_id}")
    assert resp_get.status_code == 200
    plan_retrieved = resp_get.json()
    assert plan_retrieved["status"] == "COMPLETED"


def test_benchmark_and_regret_endpoints(client):
    """Test GET /plan/{id}/benchmark and GET /plan/{id}/regret."""
    # First create a plan
    resp = client.post("/plan/run", json={"mode": "live"})
    plan = resp.json()
    plan_id = plan.get("id") or plan.get("plan_id")

    # Benchmark
    resp_bm = client.get(f"/plan/{plan_id}/benchmark")
    assert resp_bm.status_code == 200
    bm_data = resp_bm.json()
    assert bm_data["plan_id"] == plan_id
    assert "optimality_gap_percent" in bm_data
    assert "solver_energy" in bm_data

    # Regret
    resp_reg = client.get(f"/plan/{plan_id}/regret")
    assert resp_reg.status_code == 200
    assert isinstance(resp_reg.json(), list)


def test_whynot_and_whatif_endpoints(client):
    """Test GET /whynot and POST /whatif."""
    resp_why = client.get("/whynot?facility=H1&drug=INS-REG")
    assert resp_why.status_code == 200
    why_data = resp_why.json()
    assert why_data["facility_id"] == "H1"
    assert why_data["drug_code"] == "INS-REG"
    assert "reasons" in why_data
    assert len(why_data["reasons"]) > 0

    resp_whatif = client.post("/whatif", json={"scenario_type": "surge", "overrides": {}})
    assert resp_whatif.status_code == 200
    whatif_plan = resp_whatif.json()
    assert whatif_plan["mode"] == "whatif"


def test_scale_mode_and_benchmark_report(client):
    """Test scale mode execution (40 facilities) and comprehensive benchmark report."""
    resp = client.post("/plan/run", json={"mode": "eval", "scale": 40})
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["scale"] == 40
    assert plan["status"] == "COMPLETED"
    plan_id = plan["id"]
    assert "decomposition_meta" in plan or "solver_meta" in plan

    # Verify GET /plan/{id}/benchmark returns full comparison report
    resp_bm = client.get(f"/plan/{plan_id}/benchmark")
    assert resp_bm.status_code == 200
    bm = resp_bm.json()
    assert bm["plan_id"] == plan_id
    assert "milp_optimal_energy" in bm
    assert "solver_energy" in bm
    assert "optimality_gap_percent" in bm
    assert "solver_time_sec" in bm
    assert "milp_time_sec" in bm

    # Table contains all 5 required policies
    table = bm.get("comparison_table") or bm.get("table", [])
    assert len(table) == 5
    policies = [r["policy"] for r in table]
    assert "no-transfer" in policies
    assert "greedy" in policies
    assert "greedy_f4" in policies
    assert "qubo" in policies
    assert "milp" in policies

    # Check zoning report
    assert "zoning_comparison" in bm
    z_comp = bm["zoning_comparison"]
    assert "qaoa" in z_comp
    assert "kmeans" in z_comp
    assert "comparison" in z_comp
    assert "qaoa_cut_advantage" in z_comp["comparison"]


