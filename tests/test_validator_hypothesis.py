"""Hypothesis Property Tests for Optimizer Solution Validator and Repair Engine.

Generates random small snapshots and random sets of proposed transfer orders
(including deliberate duplicates, cold-chain violations, overfill, and controlled drugs),
and proves that validator repair() output GUARANTEES that 100% of invariants hold.
"""

from datetime import date, timedelta
from typing import List
import hypothesis.strategies as st
from hypothesis import given, settings, HealthCheck

from optimizer.models import TransferOrder
from optimizer.validator import (
    CONTROLLED_DRUG_CODES,
    repair,
    validate_and_simulate_fefo,
)

BASE_DATE = date(2026, 11, 1)


@st.composite
def snapshot_strategy(draw):
    """Generate valid minimal district snapshot with randomized inventory and policies."""
    fac_ids = ["H1", "H2", "H3"]
    cold_capable = draw(st.booleans())
    facilities = [
        {"id": "H1", "name": "Facility 1", "facility_type": "DH", "cold_storage_available": True, "min_reserve_days": 7},
        {"id": "H2", "name": "Facility 2", "facility_type": "TH", "cold_storage_available": cold_capable, "min_reserve_days": 5},
        {"id": "H3", "name": "Facility 3", "facility_type": "CHC", "cold_storage_available": True, "min_reserve_days": 3},
    ]

    drugs = [
        {"code": "INS-REG", "name": "Insulin", "category": "V", "storage_condition": "cold_chain", "unit_cost_inr": 145.5, "is_controlled": False},
        {"code": "PCM-500", "name": "Paracetamol", "category": "E", "storage_condition": "ambient", "unit_cost_inr": 1.2, "is_controlled": False},
        {"code": "MOR-10", "name": "Morphine", "category": "V", "storage_condition": "ambient", "unit_cost_inr": 25.0, "is_controlled": True},
    ]

    routes = [
        {"source_facility_id": "H1", "destination_facility_id": "H2", "distance_km": 25.0, "transit_hours": 1.5, "status": draw(st.sampled_from(["safe", "unsafe"])), "cold_chain_compliant": True},
        {"source_facility_id": "H1", "destination_facility_id": "H3", "distance_km": 30.0, "transit_hours": 2.0, "status": "safe", "cold_chain_compliant": True},
        {"source_facility_id": "H2", "destination_facility_id": "H3", "distance_km": 40.0, "transit_hours": 2.5, "status": "safe", "cold_chain_compliant": True},
    ]

    vehicles = [
        {"id": "CV-01", "name": "Cold Van 1", "has_cold_storage": True, "cold_ok": True},
        {"id": "AV-01", "name": "Ambient Van", "has_cold_storage": False, "cold_ok": False},
    ]

    # Generate random lots
    lots = []
    lot_id_seq = 1
    for f in ["H1", "H2"]:
        for d in ["INS-REG", "PCM-500"]:
            qty = draw(st.integers(min_value=10, max_value=200))
            exp_days = draw(st.integers(min_value=5, max_value=60))
            lots.append({
                "id": lot_id_seq,
                "facility_id": f,
                "drug_code": d,
                "batch_no": f"BATCH-{f}-{d}-{lot_id_seq}",
                "quantity": qty,
                "expiry": (BASE_DATE + timedelta(days=exp_days)).isoformat(),
            })
            lot_id_seq += 1

    forecasts = [
        {"facility_id": "H1", "drug_code": "INS-REG", "effective_daily_rate": draw(st.floats(min_value=1.0, max_value=15.0))},
        {"facility_id": "H2", "drug_code": "INS-REG", "effective_daily_rate": draw(st.floats(min_value=0.5, max_value=10.0))},
        {"facility_id": "H3", "drug_code": "INS-REG", "effective_daily_rate": draw(st.floats(min_value=0.5, max_value=8.0))},
        {"facility_id": "H1", "drug_code": "PCM-500", "effective_daily_rate": draw(st.floats(min_value=5.0, max_value=50.0))},
        {"facility_id": "H2", "drug_code": "PCM-500", "effective_daily_rate": draw(st.floats(min_value=5.0, max_value=30.0))},
        {"facility_id": "H3", "drug_code": "PCM-500", "effective_daily_rate": draw(st.floats(min_value=5.0, max_value=20.0))},
    ]

    return {
        "today": BASE_DATE.isoformat(),
        "facilities": facilities,
        "drugs": drugs,
        "routes": routes,
        "vehicles": vehicles,
        "lots": lots,
        "forecasts": forecasts,
    }


@st.composite
def random_orders_strategy(draw, snapshot):
    """Generate arbitrary candidate transfer orders, possibly invalid or conflicting."""
    lots = snapshot["lots"]
    if not lots:
        return []

    num_orders = draw(st.integers(min_value=0, max_value=6))
    orders: List[TransferOrder] = []

    for i in range(num_orders):
        lt = draw(st.sampled_from(lots))
        dst = draw(st.sampled_from(["H1", "H2", "H3"]))
        # Random quantity, could exceed lot stock to test double-shipping detection
        qty = draw(st.integers(min_value=1, max_value=300))
        # Sometimes test controlled drug injection
        dcode = draw(st.sampled_from([lt["drug_code"], "MOR-10"]))

        exp_d = date.fromisoformat(lt["expiry"])
        orders.append(
            TransferOrder(
                order_id=f"DTA/BLR-U/2026/{1000 + i:06d}",
                plan_id="plan-hypo",
                source_facility_id=lt["facility_id"],
                destination_facility_id=dst,
                drug_code=dcode,
                batch_no=lt["batch_no"],
                expiry=exp_d,
                quantity=qty,
                unit_cost_inr=10.0,
                total_cost_inr=float(qty * 10.0),
                shortage_reduction=qty,
                expiry_avoided=qty,
                vehicle_id=draw(st.sampled_from(["CV-01", "AV-01"])),
                status="PROPOSED",
            )
        )

    return orders


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.data())
def test_hypothesis_validator_invariants(data):
    """Property test: For any random snapshot and arbitrary orders, repair() output guarantees 0 violations."""
    snap = data.draw(snapshot_strategy())
    orders = data.draw(random_orders_strategy(snap))

    repaired, violations, attempts = repair(orders, snap)

    # 1. Post-repair violations must be zero
    assert len(violations) == 0, f"Repair failed to eliminate violations: {violations}"

    # 2. Strict re-simulation of repaired orders must pass 100%
    val_res = validate_and_simulate_fefo(repaired, snap)
    assert val_res.is_valid is True
    assert len(val_res.violations) == 0

    # 3. Structural invariant assertions on every output order
    for ord_obj in repaired:
        assert ord_obj.quantity > 0, "Repaired order cannot have non-positive quantity"
        assert ord_obj.usable_quantity > 0, "Repaired order must have positive usable quantity"
        assert ord_obj.drug_code not in CONTROLLED_DRUG_CODES, "Controlled drug must never survive repair"
        assert ord_obj.source_facility_id != ord_obj.destination_facility_id, "Source and destination must differ"
