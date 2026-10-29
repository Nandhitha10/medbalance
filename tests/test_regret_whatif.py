"""Integration and unit tests for Phase 14: Regret Ledger, Why-Not, What-If, and Auto Re-Plan."""

import asyncio
from datetime import date
import time
from typing import Any, Dict, List
import pytest
from httpx import ASGITransport, AsyncClient

from optimizer.app import build_app
from optimizer.auto_replan import find_affected_orders, trigger_auto_replan
from optimizer.candidates import generate_candidates
from optimizer.models import TransferOrder
from optimizer.qubo_builder import build_qubo, energy
from optimizer.regret import compute_regret_for_orders
from optimizer.snapshot import load_fixture_snapshot
from optimizer.solver import _plans_store, run_planning_pipeline
from optimizer.whatif import apply_snapshot_overrides, compute_kpi_deltas, compute_plan_diff
from optimizer.whynot import explain_whynot_shortage


@pytest.mark.asyncio
async def test_regret_delta_h_matches_energy_recomputation():
    """Verify regret ΔH strictly matches exact energy difference vs best sample."""
    snapshot = load_fixture_snapshot()
    plan = await run_planning_pipeline(mode="live", solver_choice="qubo", snapshot=snapshot)
    assert len(plan["orders"]) > 0
    assert len(plan["regret"]) > 0

    # Build QUBO on the snapshot with computed positions
    cands, infeasible = generate_candidates(plan["snapshot"])
    Q, offset, meta = build_qubo(cands, plan["snapshot"])

    var_names = meta.variable_names
    order_cand_ids = {o["candidate_id"] for o in plan["orders"] if o.get("candidate_id")}
    best_bits = [1 if name in order_cand_ids else 0 for name in var_names]
    best_energy = energy(Q, offset, best_bits)

    verified_feasible_deltas = 0
    verified_nowhere_deltas = 0

    for reg in plan["regret"]:
        delta_h = reg.get("delta_h")
        assert delta_h is not None
        assert (
            reg.get("reason_code") in {"LOWER_USABLE", "HIGHER_COST", "LOWER_VEN", "WORSE_FILL"}
            or str(reg.get("reason_code", "")).startswith("FAILED_RULE_")
        )
        assert len(reg.get("reason_text", "")) > 0

        # Check numeric reason text contains ΔH or Rule
        assert "ΔH" in reg["reason_text"] or "Rule" in reg["reason_text"] or "Infeasible" in reg["reason_text"]

        # Case 1: NOWHERE alternative (cancel transfer) from best sample
        if reg.get("alternate_destination_id") == "NOWHERE" and reg.get("sample_rank", 0) == 0:
            order_id = reg.get("order_id")
            matching_orders = [o for o in plan["orders"] if o.get("id") == order_id or o.get("order_id") == order_id]
            if matching_orders:
                c_id = matching_orders[0].get("candidate_id")
                if c_id and c_id in var_names:
                    idx = var_names.index(c_id)
                    x_nowhere = list(best_bits)
                    x_nowhere[idx] = 0
                    e_nowhere = energy(Q, offset, x_nowhere)
                    expected_delta = round(e_nowhere - best_energy, 4)
                    assert abs(delta_h - expected_delta) < 1e-3
                    verified_nowhere_deltas += 1

        # Case 2: Feasible alternative candidate from best sample
        elif reg.get("alternate_destination_id") not in ("NOWHERE", None) and reg.get("sample_rank", 0) == 0 and delta_h < 500.0:
            alt_cand_id = reg.get("candidate_id")
            if alt_cand_id and alt_cand_id in var_names:
                alt_idx = var_names.index(alt_cand_id)
                order_id = reg.get("order_id")
                matching_orders = [o for o in plan["orders"] if o.get("id") == order_id or o.get("order_id") == order_id]
                if matching_orders:
                    chosen_id = matching_orders[0].get("candidate_id")
                    if chosen_id and chosen_id in var_names:
                        chosen_idx = var_names.index(chosen_id)
                        x_alt = list(best_bits)
                        x_alt[chosen_idx] = 0
                        x_alt[alt_idx] = 1
                        e_alt = energy(Q, offset, x_alt)
                        expected_delta = round(e_alt - best_energy, 4)
                        assert abs(delta_h - expected_delta) < 1e-3
                        verified_feasible_deltas += 1

    assert verified_nowhere_deltas > 0


@pytest.mark.asyncio
async def test_whynot_lists_f3_for_h4_insulin():
    """Verify Why-Not engine identifies Rule F3 cold-chain failure for H4 insulin while ILR is down."""
    snapshot = load_fixture_snapshot()
    # Ensure H4 has cold_storage_available = False in fixture
    h4 = next((f for f in snapshot["facilities"] if f["id"] == "H4"), None)
    assert h4 is not None
    assert h4.get("cold_storage_available") is False

    # 1. Direct function call
    whynot_res = explain_whynot_shortage(
        facility_id="H4",
        drug_code="INS-REG",
        snapshot=snapshot,
    )

    assert whynot_res["facility_id"] == "H4"
    assert whynot_res["drug_code"] == "INS-REG"
    assert whynot_res["candidates_evaluated"] > 0
    assert whynot_res["residual_shortage"] >= 0

    # Verify candidate source lots for INS-REG evaluated against H4 fail Rule F3
    f3_found = False
    for lot_eval in whynot_res["candidate_source_lots"]:
        for failed_r in lot_eval.get("failed_rules", []):
            if failed_r.get("rule") == "F3":
                f3_found = True
                assert "cold storage" in failed_r.get("detail", "").lower() or "cold" in failed_r.get("detail", "").lower()

    assert f3_found, "Expected Rule F3 failure for H4 insulin candidate source lots"

    # Verify summary reasons list contains F3 explanation
    reasons_str = " ".join(whynot_res.get("reasons", []))
    assert "F3" in reasons_str or "cold" in reasons_str.lower()

    # 2. Test via FastAPI endpoint
    app = build_app(use_fixtures=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/whynot?facility=H4&drug=INS-REG")
        assert resp.status_code == 200
        data = resp.json()
        assert data["facility_id"] == "H4"
        assert data["drug_code"] == "INS-REG"
        assert any("F3" in r or "cold" in r.lower() for r in data["reasons"])


@pytest.mark.asyncio
async def test_whatif_repair_cold_storage_h4_makes_h4_destination():
    """Verify what-if repair_cold_storage(H4) enables H4 to receive cold-chain inventory."""
    snapshot = load_fixture_snapshot()
    app = build_app(use_fixtures=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Run baseline live plan
        live_resp = await client.post("/plan/run", json={"mode": "live", "solver": "qubo"})
        assert live_resp.status_code == 200
        live_plan = live_resp.json()
        live_plan_id = live_plan["id"]

        # Confirm H4 is NOT a destination for cold-chain items in baseline
        live_h4_cold_orders = [
            o for o in live_plan.get("orders", [])
            if o.get("destination_facility_id") == "H4" and o.get("drug_code") in ("INS-REG", "OXY-10")
        ]
        assert len(live_h4_cold_orders) == 0

        # Step 2: Post what-if scenario with repair_cold_storage="H4"
        whatif_resp = await client.post(
            "/whatif",
            json={"scenario_type": "cold_chain_repair", "overrides": {"repair_cold_storage": "H4"}},
        )
        assert whatif_resp.status_code == 200
        whatif_data = whatif_resp.json()

        assert whatif_data["mode"] == "whatif"
        assert whatif_data["status"] == "COMPLETED"
        diff = whatif_data["diff"]
        assert "orders_added" in diff

        # Verify H4 is now a destination in what-if orders
        whatif_h4_orders = [
            o for o in whatif_data.get("orders", [])
            if o.get("destination_facility_id") == "H4"
        ]
        assert len(whatif_h4_orders) > 0, "Repaired H4 should receive transfer orders in what-if"

        # Verify added orders list contains H4 destination
        added_to_h4 = [
            o for o in diff["orders_added"]
            if o.get("destination_facility_id") == "H4"
        ]
        assert len(added_to_h4) > 0

        # Step 3: Invariant - what-if is NEVER persisted as live plan
        latest_live = _plans_store.get("latest_live")
        assert latest_live is not None
        assert latest_live.get("id") == live_plan_id
        assert latest_live.get("mode") == "live"


@pytest.mark.asyncio
async def test_auto_replan_moves_cold_orders_off_cv02():
    """Verify coldchain excursion alert triggers auto re-plan moving orders off failing CV-02."""
    snapshot = load_fixture_snapshot()
    plans_store: Dict[str, Any] = {}

    # Seed an active live plan with a cold order on CV-02
    live_plan = await run_planning_pipeline(mode="live", snapshot=snapshot)
    assert len(live_plan["orders"]) > 0

    # Explicitly assign one cold order to CV-02 to simulate active assignment
    cold_order = None
    for o in live_plan["orders"]:
        if o.get("drug_code") in ("INS-REG", "OXY-10", "ASV-10", "TD-VAC"):
            cold_order = o
            break

    if not cold_order:
        cold_order = live_plan["orders"][0]

    cold_order["vehicle_id"] = "CV-02"
    cold_order_id = cold_order["id"]

    plans_store[live_plan["id"]] = live_plan
    plans_store["latest_live"] = live_plan

    # Trigger excursion alert for CV-02 (temp 11.4°C > 8.0°C)
    alert_payload = {
        "vehicle_id": "CV-02",
        "device_id": "DEV-CV-02",
        "temp_c": 11.4,
        "severity": "CRITICAL",
        "routes": ["R-H1-H4", "R-H2-H4"],
    }

    replan_result = await trigger_auto_replan(
        alert_data=alert_payload,
        plans_store=plans_store,
        run_planning_fn=run_planning_pipeline,
        snapshot=snapshot,
    )

    assert replan_result is not None
    assert replan_result["status"] == "revised"
    revised_plan_id = replan_result["new_plan_id"]
    assert revised_plan_id.startswith("PLAN-REV-")

    # 1. Verify original cold order on CV-02 is marked SUPERSEDED
    assert cold_order["status"] == "SUPERSEDED"
    assert cold_order["superseded_by"] == revised_plan_id

    # 2. Verify NO order in the revised plan is assigned to CV-02
    revised_orders = replan_result["plan"]["orders"]
    for ro in revised_orders:
        v_id = str(ro.get("vehicle_id", "")).upper()
        assert "CV-02" not in v_id, f"Revised order {ro.get('id')} must not be assigned to CV-02"

    # 3. Verify diff is computed
    diff = replan_result["diff"]
    assert "orders_added" in diff or "orders_removed" in diff or "orders_changed" in diff


@pytest.mark.asyncio
async def test_acceptance_fridge_failure_produces_plan_revised_within_60s():
    """Acceptance Test: Fridge failure during a live plan produces plan.revised with a diff within 60 s."""
    snapshot = load_fixture_snapshot()
    plans_store: Dict[str, Any] = {}

    # 1. Establish baseline live plan
    live_plan = await run_planning_pipeline(mode="live", snapshot=snapshot)
    # Assign CV-02 to first cold order
    for o in live_plan["orders"]:
        if o.get("drug_code") in ("INS-REG", "OXY-10", "ASV-10", "TD-VAC"):
            o["vehicle_id"] = "CV-02"
            break
    plans_store[live_plan["id"]] = live_plan
    plans_store["latest_live"] = live_plan

    # 2. Time end-to-end execution of auto re-planning on excursion alert
    start_time = time.perf_counter()

    alert_payload = {
        "device_id": "DEV-CV-02",
        "vehicle_id": "CV-02",
        "temp_c": 12.5,
        "severity": "CRITICAL",
        "routes": ["RTE-H2-H4"],
    }

    result = await trigger_auto_replan(
        alert_data=alert_payload,
        plans_store=plans_store,
        run_planning_fn=run_planning_pipeline,
        snapshot=snapshot,
    )

    elapsed_sec = time.perf_counter() - start_time

    # Assert SLA: must complete well within 60 seconds
    assert elapsed_sec < 60.0, f"Auto re-planning took {elapsed_sec:.2f}s, exceeding 60s SLA"

    # 3. Assert plan.revised event and diff structure
    assert result is not None
    assert result["status"] == "revised"
    assert result["original_plan_id"] == live_plan["id"]
    assert result["new_plan_id"].startswith("PLAN-REV-")

    event = result["event"]
    assert event["event_type"] == "plan.revised"
    event_data = event["data"]
    assert event_data["original_plan_id"] == live_plan["id"]
    assert event_data["new_plan_id"] == result["new_plan_id"]
    assert "diff" in event_data
    assert "superseded_orders" in event_data

    # 4. Assert zero violations in revised plan
    assert result["plan"]["violations_count"] == 0

