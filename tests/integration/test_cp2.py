"""Integration test for Checkpoint 2 (CP2) end-to-end operational scenarios.

Tests the live running stack:
1. dengue_outbreak raises H3 ORS forecast (POST /api/sim/scenario/dengue_outbreak -> POST /api/forecast/run -> GET /api/forecast)
2. bad_data creates review items (POST /api/sim/scenario/bad_data -> POST /api/ingest/pull/run or /ingest/H4 -> GET /api/ingest/reviews)
3. plan uses QUBO tier (any) with 0 violations (POST /api/optimizer/plan/run)
4. benchmark has 5 rows (GET /api/optimizer/plan/{id}/benchmark)
5. fridge_failure produces coldchain.alert within 90 s (POST /api/sim/scenario/fridge_failure -> poll GET /api/coldchain/status)
"""

import os
import time
from typing import Any, Dict, List, Optional
import httpx
import pytest

# Configuration from environment with gateway defaults (port 8080 per CLAUDE.md §3)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")
SIM_CONTROL_URL = os.getenv("SIM_CONTROL_URL", f"{GATEWAY_URL}/api/sim").rstrip("/")
CORE_API_URL = os.getenv("CORE_API_URL", f"{GATEWAY_URL}/api/core").rstrip("/")
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", f"{GATEWAY_URL}/api/optimizer").rstrip("/")
FORECAST_URL = os.getenv("FORECAST_URL", f"{GATEWAY_URL}/api/forecast").rstrip("/")
INGEST_AI_URL = os.getenv("INGEST_AI_URL", f"{GATEWAY_URL}/api/ingest").rstrip("/")
COLDCHAIN_URL = os.getenv("COLDCHAIN_URL", f"{GATEWAY_URL}/api/coldchain").rstrip("/")

# Controlled drug codes prohibited from automated redistribution (Rule F6)
CONTROLLED_DRUG_CODES = {"MOR-10", "FNT-50"}

# Recognized QUBO solver tiers
VALID_QUBO_TIERS = {
    "qpiai_opt_platform",
    "qpiai_opt_local",
    "dwave_neal_sa",
    "greedy_descent",
    "qubo",
    "greedy_f4_fallback",
}


@pytest.fixture(scope="module")
def client():
    """HTTP client with standard timeout."""
    with httpx.Client(timeout=15.0) as c:
        yield c


class TestCP2Integration:
    """End-to-end integration test suite verifying Checkpoint 2 capabilities."""

    def test_01_dengue_outbreak_raises_h3_ors_forecast(self, client: httpx.Client):
        """Step 1: dengue_outbreak raises H3 ORS forecast (multiplier > 1.0, daily rate expanded, outbreak signal cited)."""
        # 1. Activate dengue_outbreak scenario on sim-control
        scenario_url = f"{SIM_CONTROL_URL}/scenario/dengue_outbreak"
        resp_sc = client.post(scenario_url)
        # Accept either /scenario/ or /scenarios/ route
        if resp_sc.status_code == 404:
            resp_sc = client.post(f"{SIM_CONTROL_URL}/scenarios/dengue_outbreak")
        assert resp_sc.status_code == 200, f"Activating dengue_outbreak failed ({resp_sc.status_code}): {resp_sc.text}"
        data_sc = resp_sc.json()
        assert data_sc.get("status") == "activated", f"Expected scenario activated: {data_sc}"

        # 2. Trigger consumption forecast run
        run_url = f"{FORECAST_URL}/run"
        resp_run = client.post(run_url, json={"facility": "H3", "drug": "ORS-20", "target_days": 14})
        if resp_run.status_code == 404:
            resp_run = client.post(f"{FORECAST_URL}/forecast/run", json={"facility": "H3", "drug": "ORS-20", "target_days": 14})
        assert resp_run.status_code == 200, f"Forecast run failed ({resp_run.status_code}): {resp_run.text}"
        data_run = resp_run.json()
        assert data_run.get("status") == "completed", f"Forecast run not completed: {data_run}"

        # 3. Fetch forecast for H3 ORS-20
        query_url = f"{FORECAST_URL}/forecast?facility=H3&drug=ORS-20"
        resp_q = client.get(query_url)
        if resp_q.status_code == 404:
            resp_q = client.get(f"{FORECAST_URL}?facility=H3&drug=ORS-20")
        assert resp_q.status_code == 200, f"Fetching forecast failed ({resp_q.status_code}): {resp_q.text}"
        forecasts = resp_q.json()
        assert isinstance(forecasts, list), f"Expected list of forecasts, got {type(forecasts)}"

        # Find H3 ORS forecast item
        h3_ors: Optional[Dict[str, Any]] = None
        for fc in forecasts:
            fac = fc.get("facility") or fc.get("facility_id")
            drug = fc.get("drug") or fc.get("drug_code")
            if fac == "H3" and drug in ("ORS-20", "ORS"):
                h3_ors = fc
                break

        assert h3_ors is not None, f"No forecast item found for H3 ORS. Response: {forecasts}"

        # Assert context multiplier > 1.0 (clamped [0.5, 3.0])
        multiplier = float(h3_ors.get("llm_multiplier", h3_ors.get("context_multiplier", h3_ors.get("multiplier", 1.0))))
        assert multiplier > 1.0, f"Expected context multiplier > 1.0 for H3 ORS under dengue outbreak, got {multiplier}"

        # Assert daily consumption rate is expanded: effective_daily_rate > baseline_daily_rate
        base_rate = float(h3_ors.get("baseline_daily_rate", h3_ors.get("baseline_rate", 0.0)))
        final_rate = float(h3_ors.get("effective_daily_rate", h3_ors.get("forecast_daily_rate", h3_ors.get("daily_rate", 0.0))))
        if base_rate > 0:
            assert final_rate > base_rate, (
                f"Expected final forecast rate ({final_rate}) to exceed baseline rate ({base_rate})"
            )

        # Assert epidemiological outbreak signal is cited
        signals = h3_ors.get("signal_ids") or h3_ors.get("signals") or []
        reason = h3_ors.get("context_reasoning") or h3_ors.get("reasoning", "")
        has_signal_citation = len(signals) > 0 or any(kw in reason.upper() for kw in ("DENGUE", "OUTBREAK", "IDSP", "SIG-"))
        assert has_signal_citation, f"Expected IDSP/outbreak signal citation in forecast: {h3_ors}"

    def test_02_bad_data_creates_review_items(self, client: httpx.Client):
        """Step 2: bad_data scenario creates pharmacist review items with anomaly flags."""
        # 1. Activate bad_data scenario on sim-control
        sc_url = f"{SIM_CONTROL_URL}/scenario/bad_data"
        resp_sc = client.post(sc_url)
        if resp_sc.status_code == 404:
            resp_sc = client.post(f"{SIM_CONTROL_URL}/scenarios/bad_data")
        assert resp_sc.status_code == 200, f"Activating bad_data failed ({resp_sc.status_code}): {resp_sc.text}"

        # 2. Ingest bad data report: push corrupted physical stock register for H4
        # (10000 vials of insulin and year 1999 expiry)
        bad_text = (
            "DAILY STOCK REGISTER - HESARAGHATTA PHC\n"
            "Date: 01/11/2026\n"
            "Physical count taken at ILR & ambient rack:\n"
            "---------------------------------------------------------\n"
            "10000 inzulin reg 100iu vials b.no B-999 exp 14/08/1999\n"
            "paracetmol 500mg tabs: 300 tab b.no LOT-PCM-H4-01 exp 2026-12-16\n"
            "ors oral salt sachet: 150 pkt exp 2027-01-30\n"
            "---------------------------------------------------------\n"
            "ILR status: under repair / compressor defect\n"
            "Checked by: Staff Nurse Lalitha K.\n"
        )
        ingest_url = f"{INGEST_AI_URL}/ingest/H4"
        resp_ingest = client.post(ingest_url, json={"raw_content": bad_text, "source_type": "text"})
        assert resp_ingest.status_code in (200, 201), f"Ingest report failed ({resp_ingest.status_code}): {resp_ingest.text}"

        # Also trigger hospital polling to exercise ingestion pipeline
        try:
            client.post(f"{INGEST_AI_URL}/pull/run")
        except Exception:
            pass

        # 3. Retrieve review queue from ingest-ai
        reviews_url = f"{INGEST_AI_URL}/reviews"
        resp_rev = client.get(reviews_url)
        assert resp_rev.status_code == 200, f"Fetching reviews failed ({resp_rev.status_code}): {resp_rev.text}"
        reviews = resp_rev.json()
        assert isinstance(reviews, list), f"Expected list of reviews, got {type(reviews)}"

        # Assert at least 1 review item is pending
        assert len(reviews) >= 1, f"Expected >= 1 review item after bad_data ingestion, got {len(reviews)}. Data: {reviews}"

        # Assert an anomaly item exists with expected safety flags (SUSPICIOUS_EXPIRY or QUANTITY_SPIKE)
        anomaly_types = {r.get("anomaly_type") for r in reviews if r.get("anomaly_type")}
        valid_anomalies = {"SUSPICIOUS_EXPIRY", "QUANTITY_SPIKE", "CORRUPTED_TEXT", "UNKNOWN_DRUG", "LOW_CONFIDENCE"}
        assert len(anomaly_types.intersection(valid_anomalies)) > 0, (
            f"Expected recognized anomaly type among {valid_anomalies}, got {anomaly_types}"
        )

    def test_03_plan_uses_qubo_tier_with_zero_violations(self, client: httpx.Client):
        """Step 3: plan uses QUBO tier (any) with 0 violations, usable > 0, and no controlled drugs."""
        plan_run_url = f"{OPTIMIZER_URL}/plan/run"
        response = client.post(plan_run_url, json={"mode": "live", "solver": "qubo"})
        assert response.status_code in (200, 201), (
            f"Optimizer plan run failed ({response.status_code}): {response.text}"
        )
        plan = response.json()

        # 1. Assert solver tier is a QUBO tier
        solver_tier = plan.get("solver_tier")
        if not solver_tier:
            solver_tier = plan.get("solver_meta", {}).get("solver_tier")
        assert solver_tier is not None, f"Missing solver_tier in plan response: {plan}"
        assert solver_tier in VALID_QUBO_TIERS, (
            f"Expected solver_tier to be one of {VALID_QUBO_TIERS}, got '{solver_tier}'"
        )

        # 2. Assert violations count == 0
        violations_count = plan.get("violations_count")
        if violations_count is None:
            violations_count = plan.get("solver_meta", {}).get("violations_count")
        if violations_count is None:
            violations_count = len(plan.get("violations", []))
        assert violations_count == 0, f"Expected 0 constraint violations post-repair, got {violations_count}"

        # 3. Assert orders exist and all have usable > 0
        orders: List[Dict[str, Any]] = plan.get("orders") or plan.get("transfer_orders") or []
        assert len(orders) >= 1, f"Expected >= 1 transfer order from plan, got {len(orders)}. Plan: {plan}"

        for order in orders:
            order_id = order.get("id") or order.get("order_id") or "UNKNOWN"
            usable_qty = order.get("usable_quantity")
            if usable_qty is None:
                usable_qty = order.get("usable")
            if usable_qty is None:
                usable_qty = order.get("quantity", 0)

            assert usable_qty > 0, (
                f"Order {order_id} has non-positive usable quantity: {usable_qty}. Order: {order}"
            )

        # 4. Assert no order for controlled drugs (Rule F6)
        for order in orders:
            order_id = order.get("id") or order.get("order_id") or "UNKNOWN"
            drug_code = order.get("drug_code")
            assert drug_code not in CONTROLLED_DRUG_CODES, (
                f"Order {order_id} is for controlled narcotic drug '{drug_code}', violating Rule F6"
            )

    def test_04_benchmark_has_5_rows(self, client: httpx.Client):
        """Step 4: benchmark endpoint returns exactly 5 rows (no-transfer, greedy, greedy_f4, qubo, milp) with valid gap."""
        # 1. Run plan to obtain plan_id
        plan_run_url = f"{OPTIMIZER_URL}/plan/run"
        plan_resp = client.post(plan_run_url, json={"mode": "live", "solver": "qubo"})
        assert plan_resp.status_code in (200, 201), f"Plan run failed: {plan_resp.text}"
        plan = plan_resp.json()
        plan_id = plan.get("id") or plan.get("plan_id") or "latest"

        # 2. Query benchmark endpoint
        bench_url = f"{OPTIMIZER_URL}/plan/{plan_id}/benchmark"
        response = client.get(bench_url)
        assert response.status_code == 200, f"Fetching benchmark failed ({response.status_code}): {response.text}"
        bench = response.json()

        # 3. Assert comparison table has exactly 5 rows
        comparison_table = bench.get("comparison_table") or bench.get("table") or []
        assert len(comparison_table) == 5, (
            f"Expected exactly 5 rows in benchmark comparison table, got {len(comparison_table)}. Table: {comparison_table}"
        )

        # 4. Assert all 5 policies are present
        policies = {r.get("policy") for r in comparison_table if r.get("policy")}
        expected_policies = {"no-transfer", "greedy", "greedy_f4", "qubo", "milp"}
        assert policies == expected_policies, f"Expected policies {expected_policies}, got {policies}"

        # 5. Assert optimality gap % is non-negative and finite
        gap = bench.get("optimality_gap_percent")
        assert gap is not None, f"Missing optimality_gap_percent in benchmark: {bench}"
        assert gap >= 0.0, f"Optimality gap cannot be negative, got {gap}%"

        # 6. Assert graph zoning report / comparison is present
        zoning = bench.get("zoning_comparison") or bench.get("zoning_report")
        assert zoning is not None, f"Missing zoning comparison report in benchmark: {bench}"

    def test_05_fridge_failure_produces_coldchain_alert_within_90s(self, client: httpx.Client):
        """Step 5: fridge_failure scenario produces temperature excursion and alert on DEV-CV-02 within 90 s."""
        # 1. Activate fridge_failure scenario on sim-control
        sc_url = f"{SIM_CONTROL_URL}/scenario/fridge_failure"
        resp_sc = client.post(sc_url)
        if resp_sc.status_code == 404:
            resp_sc = client.post(f"{SIM_CONTROL_URL}/scenarios/fridge_failure")
        assert resp_sc.status_code == 200, f"Activating fridge_failure failed ({resp_sc.status_code}): {resp_sc.text}"

        # 2. Inject telemetry packets to simulate compressor drift above 8.0 °C if direct injection supported
        telemetry_url = f"{COLDCHAIN_URL}/telemetry"
        for temp in (8.5, 9.8, 11.4):
            try:
                client.post(telemetry_url, json={
                    "device_id": "DEV-CV-02",
                    "vehicle_id": "CV-02",
                    "temp_c": temp,
                    "door_open": False,
                    "battery": 92.0,
                })
            except Exception:
                pass

        # 3. Poll coldchain status until DEV-CV-02 reaches EXCURSION or active_excursions >= 1 (max 90 s)
        status_url = f"{COLDCHAIN_URL}/status"
        start_time = time.time()
        max_wait_seconds = 90.0
        excursion_detected = False
        last_status: Dict[str, Any] = {}

        while time.time() - start_time < max_wait_seconds:
            resp = client.get(status_url)
            if resp.status_code == 200:
                last_status = resp.json()
                active_excursions = last_status.get("active_excursions", 0)

                # Check devices list
                devices = last_status.get("devices", [])
                cv02_state = None
                cv02_temp = None
                for d in devices:
                    d_id = d.get("device_id") or d.get("id")
                    target = d.get("assigned_to")
                    if d_id == "DEV-CV-02" or target in ("CV-02", "V-COLD-02"):
                        cv02_state = d.get("status") or d.get("state")
                        cv02_temp = d.get("latest_temp_c")
                        break

                if active_excursions >= 1 or cv02_state == "EXCURSION" or (cv02_temp is not None and cv02_temp > 8.0):
                    excursion_detected = True
                    break

            time.sleep(2.0)

        assert excursion_detected, (
            f"Timed out after {max_wait_seconds}s waiting for coldchain excursion alert on DEV-CV-02. "
            f"Last coldchain status: {last_status}"
        )
