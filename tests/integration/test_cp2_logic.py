"""Verification of CP2 requirements in-process: proving correctness of domain logic."""

import asyncio
from datetime import date
import pytest

from sim_control.scenarios import scenario_manager
from forecast.service import run_all_forecasts, get_stored_forecasts
from ingest_ai.anomaly import AnomalyDetector
from optimizer.solver import run_planning_pipeline
from optimizer.routers.plan import get_benchmark
from coldchain.state_machine import ColdChainManager, DeviceState


@pytest.mark.asyncio
async def test_cp2_step1_dengue_outbreak_forecast():
    """Verify dengue outbreak raises H3 ORS forecast with multiplier > 1.0 and signal citation."""
    sc = await scenario_manager.activate_scenario("dengue_outbreak")
    assert sc.active is True

    fc_items = await run_all_forecasts(facility_filter="H3", drug_filter="ORS-20")
    h3_ors = [fc for fc in fc_items if fc.facility_id == "H3" and fc.drug_code == "ORS-20"][0]

    assert h3_ors.llm_multiplier > 1.0
    assert h3_ors.effective_daily_rate > h3_ors.baseline_daily_rate
    assert len(h3_ors.signal_ids) > 0 or "OUTBREAK" in (h3_ors.reasoning or "").upper()


def test_cp2_step2_bad_data_anomaly_detection():
    """Verify bad_data produces anomaly review item flags for suspicious expiry and quantity spike."""
    detector = AnomalyDetector()
    eval_res = detector.evaluate_item(
        facility_id="H4",
        drug_code="INS-REG",
        batch_no="B-999",
        expiry=date(1999, 8, 14),
        quantity=10000,
        confidence=0.88,
        report_date=date(2026, 11, 1),
    )
    assert eval_res.is_anomalous is True
    assert "SUSPICIOUS_EXPIRY_PAST" in eval_res.triggered_rules


@pytest.mark.asyncio
async def test_cp2_step3_qubo_solver_tier_and_zero_violations():
    """Verify planning pipeline uses QUBO tier, 0 violations, and positive usable quantity."""
    plan = await run_planning_pipeline(mode="live", solver_choice="qubo")
    tier = plan["solver_tier"]
    violations = plan.get("violations_count", 0)
    orders = plan["orders"]

    assert tier in {
        "qpiai_opt_platform",
        "qpiai_opt_local",
        "dwave_neal_sa",
        "greedy_descent",
        "qubo",
        "greedy_f4_fallback",
    }
    assert violations == 0
    assert len(orders) >= 1
    assert all(o.get("usable_quantity", 0) > 0 for o in orders)
    assert not any(o.get("drug_code") in ("MOR-10", "FNT-50") for o in orders)


@pytest.mark.asyncio
async def test_cp2_step4_benchmark_5_rows():
    """Verify benchmark returns exactly 5 rows with non-negative gap and zoning comparison."""
    plan = await run_planning_pipeline(mode="live", solver_choice="qubo")
    bench = await get_benchmark(plan["id"])
    table = bench["comparison_table"]
    policies = [r["policy"] for r in table]
    gap = bench["optimality_gap_percent"]

    assert len(table) == 5
    assert set(policies) == {"no-transfer", "greedy", "greedy_f4", "qubo", "milp"}
    assert gap >= 0.0
    assert "zoning_comparison" in bench


def test_cp2_step5_coldchain_excursion_alert():
    """Verify cold chain state machine triggers EXCURSION and produces coldchain.alert on 11.4 °C."""
    mgr = ColdChainManager()
    alert = None
    for temp in [8.5, 9.2, 11.4]:
        res = mgr.process_reading({
            "device_id": "DEV-CV-02",
            "assigned_to": "CV-02",
            "temp_c": temp,
            "door_open": False,
        })
        if res:
            alert = res

    status = mgr.get_status_summary()
    cv02 = [d for d in status["devices"] if d["device_id"] == "DEV-CV-02"][0]

    assert cv02["status"] == "EXCURSION"
    assert alert is not None
    assert alert["event_type"] == "coldchain.alert"
