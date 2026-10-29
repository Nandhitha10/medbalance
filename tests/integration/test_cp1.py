"""Integration test for Checkpoint 1 (CP1) walking skeleton end-to-end.

Tests the live running stack:
1. Reset sim with seed 42 (POST /api/sim/reset?seed=42)
2. Start clock (POST /api/sim/clock/start)
3. Wait for 2 sim days (poll GET /api/sim/clock until day_index >= 2 or date advances 2 days)
4. Assert lots exist for H1..H4 via core-api (GET /api/core/lots)
5. Run a plan (POST /api/optimizer/plan/run)
6. Assert >= 1 order
7. Assert all orders have usable > 0
8. Assert no order for a controlled drug (e.g. MOR-10)
9. Assert audit verify ok (GET /api/core/audit/verify)
"""

import os
import time
from typing import Any, Dict, List
import httpx
import pytest

# Configuration from environment with gateway defaults (port 8080 per CLAUDE.md §3)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")
SIM_CONTROL_URL = os.getenv("SIM_CONTROL_URL", f"{GATEWAY_URL}/api/sim").rstrip("/")
CORE_API_URL = os.getenv("CORE_API_URL", f"{GATEWAY_URL}/api/core").rstrip("/")
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", f"{GATEWAY_URL}/api/optimizer").rstrip("/")

# Controlled drug codes prohibited from automated redistribution (Rule F6)
CONTROLLED_DRUG_CODES = {"MOR-10", "FNT-50"}


@pytest.fixture(scope="module")
def client():
    """HTTP client with standard timeout."""
    with httpx.Client(timeout=15.0) as client:
        yield client


class TestCP1WalkingSkeleton:
    """End-to-end integration test suite verifying the walking skeleton."""

    def test_01_reset_sim_seed_42(self, client: httpx.Client):
        """Step 1: Reset simulation clock and ground truth with seed 42."""
        url = f"{SIM_CONTROL_URL}/reset?seed=42"
        response = client.post(url)
        assert response.status_code == 200, f"Reset failed ({response.status_code}): {response.text}"
        data = response.json()
        assert data.get("status") == "reset", f"Unexpected reset response status: {data}"
        assert data.get("seed") == 42, f"Expected seed 42, got: {data.get('seed')}"

    def test_02_start_clock_and_wait_2_sim_days(self, client: httpx.Client):
        """Step 2 & 3: Start simulation clock and wait until 2 sim days have rolled over."""
        # Speed up clock to accelerate 2-day progression if supported
        speed_url = f"{SIM_CONTROL_URL}/clock/speed"
        try:
            client.post(speed_url, json={"speed": 10.0})
        except Exception:
            pass

        # Start clock
        start_url = f"{SIM_CONTROL_URL}/clock/start"
        start_resp = client.post(start_url)
        assert start_resp.status_code == 200, f"Clock start failed ({start_resp.status_code}): {start_resp.text}"

        # Poll clock until at least 2 sim days elapse (day_index >= 2 or date advanced >= 2 days)
        clock_url = f"{SIM_CONTROL_URL}/clock"
        max_wait_seconds = 45.0
        start_time = time.time()
        target_reached = False
        last_state: Dict[str, Any] = {}

        while time.time() - start_time < max_wait_seconds:
            resp = client.get(clock_url)
            if resp.status_code == 200:
                last_state = resp.json()
                day_index = last_state.get("day_index", 0)
                sim_date = last_state.get("date") or last_state.get("today", "")
                # Consider day 2 reached if day_index >= 2 or date is on/after 2026-11-03
                if day_index >= 2 or sim_date >= "2026-11-03":
                    target_reached = True
                    break
            time.sleep(1.0)

        assert target_reached, (
            f"Timed out after {max_wait_seconds}s waiting for 2 sim days. "
            f"Last clock state: {last_state}"
        )

    def test_03_assert_lots_exist_for_h1_to_h4(self, client: httpx.Client):
        """Step 4: Assert lots exist for H1..H4 via core-api."""
        lots_url = f"{CORE_API_URL}/lots"
        response = client.get(lots_url)
        assert response.status_code == 200, f"Fetching lots failed ({response.status_code}): {response.text}"
        lots = response.json()
        assert isinstance(lots, list), f"Expected lots list, got: {type(lots)}"

        facilities_present = {lt.get("facility_id") for lt in lots if lt.get("facility_id")}
        for fac_id in ("H1", "H2", "H3", "H4"):
            assert fac_id in facilities_present, (
                f"Facility '{fac_id}' has no inventory lots reported in core-api. "
                f"Present facilities: {facilities_present}"
            )

    def test_04_run_plan_and_assert_orders(self, client: httpx.Client):
        """Step 5..8: Run optimization plan, assert >=1 order, usable>0, and no controlled drug."""
        plan_run_url = f"{OPTIMIZER_URL}/plan/run"
        response = client.post(plan_run_url, json={"mode": "live"})
        assert response.status_code in (200, 201), (
            f"Optimizer plan run failed ({response.status_code}): {response.text}"
        )
        plan = response.json()
        orders: List[Dict[str, Any]] = plan.get("orders") or plan.get("transfer_orders") or []

        # Assert >= 1 order produced
        assert len(orders) >= 1, f"Expected >= 1 transfer order from plan, got {len(orders)}. Plan: {plan}"

        # Assert all orders have usable > 0
        for order in orders:
            order_id = order.get("id") or order.get("order_id") or "UNKNOWN"
            usable_qty = order.get("usable_quantity")
            if usable_qty is None:
                usable_qty = order.get("usable")
            if usable_qty is None:
                usable_qty = order.get("quantity", 0)

            assert usable_qty > 0, (
                f"Order {order_id} has invalid non-positive usable quantity: {usable_qty}. "
                f"Order details: {order}"
            )

        # Assert no order for a controlled drug (Schedule X / F6 violation)
        for order in orders:
            order_id = order.get("id") or order.get("order_id") or "UNKNOWN"
            drug_code = order.get("drug_code")
            assert drug_code not in CONTROLLED_DRUG_CODES, (
                f"Order {order_id} is for controlled narcotic drug '{drug_code}', "
                f"violating feasibility rule F6. Order: {order}"
            )

    def test_05_audit_verify(self, client: httpx.Client):
        """Step 9: Assert audit chain verification is ok (tamper-evident integrity)."""
        audit_url = f"{CORE_API_URL}/audit/verify"
        response = client.get(audit_url)
        assert response.status_code == 200, f"Audit verify request failed ({response.status_code}): {response.text}"
        result = response.json()
        assert result.get("ok") is True or result.get("verified") is True, (
            f"Audit chain verification failed: {result}"
        )
