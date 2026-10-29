"""Integration tests for optimizer candidates, greedy baselines, metrics, and plan persistence."""

from datetime import date, timedelta
import pytest

from optimizer.candidates import split_lot_into_chunks, generate_candidates
from optimizer.baselines import greedy_phone_call, greedy_f4
from optimizer.metrics import calculate_plan_metrics


def test_chunk_splitting_and_pack_rounding():
    """Verify lot's transferable quantity splits into <=3 chunks (50/25/25 pack-rounded, dropping 0)."""
    # 50 units, pack size 1 -> 25, 12, 13 (sum 50)
    chunks_50 = split_lot_into_chunks(total_qty=50, pack_size=1)
    assert len(chunks_50) == 3
    assert sum(c.quantity for c in chunks_50) == 50
    assert chunks_50[0].quantity == 25
    assert sorted([c.quantity for c in chunks_50]) == [12, 13, 25]

    # 10 units, pack size 10 -> [10] (only 1 chunk since 25% < pack size)
    chunks_10 = split_lot_into_chunks(total_qty=10, pack_size=10)
    assert len(chunks_10) == 1
    assert chunks_10[0].quantity == 10

    # 12,000 tabs, pack size 100 -> [6000, 3000, 3000]
    chunks_12k = split_lot_into_chunks(total_qty=12000, pack_size=100)
    assert len(chunks_12k) == 3
    assert chunks_12k[0].quantity == 6000
    assert chunks_12k[1].quantity == 3000
    assert chunks_12k[2].quantity == 3000


def test_chunk_sequential_usable():
    """Destination has usable capacity 28 for a lot.
    
    When 3 chunks of 25, 13, 12 evaluate against this destination:
    - Chunk 1 (25): usable = min(25, 28) = 25
    - Chunk 2 (13): usable = min(13, 28 - 25) = 3
    - Chunk 3 (12): usable = min(12, 28 - 25 - 3) = 0 (infeasible)
    """
    from optimizer.candidates import calculate_sequential_chunk_usable

    capacity = 28
    q1, u1 = 25, calculate_sequential_chunk_usable(chunk_qty=25, dest_capacity=capacity, allocated_so_far=0)
    assert u1 == 25

    q2, u2 = 13, calculate_sequential_chunk_usable(chunk_qty=13, dest_capacity=capacity, allocated_so_far=u1)
    assert u2 == 3

    q3, u3 = 12, calculate_sequential_chunk_usable(chunk_qty=12, dest_capacity=capacity, allocated_so_far=u1 + u2)
    assert u3 == 0


def test_controlled_drug_never_a_candidate():
    """Verify Schedule X / controlled drugs (e.g. MOR-10) are marked infeasible under F6 and excluded from greedy solutions."""
    snapshot = {
        "today": "2026-11-01",
        "facilities": [
            {"id": "H2", "name": "SIM-TGH Anekal", "cold_storage_available": True},
            {"id": "H1", "name": "SIM-DH Jayanagar", "cold_storage_available": True},
        ],
        "drugs": [
            {"code": "MOR-10", "name": "Morphine", "category": "V", "unit": "tab", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 14, "unit_cost_inr": 25.0, "is_controlled": True},
        ],
        "routes": [
            {"id": "R-H2-H1", "source_facility_id": "H2", "destination_facility_id": "H1", "distance_km": 28.0, "transit_hours": 1.5, "cold_chain_compliant": False, "status": "active"},
        ],
        "vehicles": [
            {"id": "AV-01", "name": "Ambient Van", "cold_chain_capable": False, "is_active": True, "current_temp_c": 24.0},
        ],
        "lots": [
            {"id": 1, "facility_id": "H2", "drug_code": "MOR-10", "batch_no": "LOT-MOR-01", "expiry": "2026-12-15", "quantity": 100},
        ],
        "positions": [
            {"facility_id": "H2", "drug_code": "MOR-10", "effective_stock": 50, "at_risk_stock": 50, "reserve": 20, "shortage": 0},
            {"facility_id": "H1", "drug_code": "MOR-10", "effective_stock": 0, "at_risk_stock": 0, "reserve": 10, "shortage": 50},
        ],
        "forecasts": [
            {"facility_id": "H1", "drug_code": "MOR-10", "effective_daily_rate": 5.0},
        ],
        "policies": [],
    }

    candidates, infeasible = generate_candidates(snapshot)
    # Morphine chunks to H1 must all fail F6
    assert len(candidates) == 0
    assert len(infeasible) > 0
    assert any("F6" in str(item.failed_rules) for item in infeasible)


def test_greedy_phone_call_vs_greedy_f4_on_engineered_lot():
    """Engineered H4 Insulin Story Lot:
    
    H4 holds 50 vials of INS-REG expiring in 18 days.
    Destination H3 has rate 0.5/day, destination earlier stock = 0.
    Destination capacity = 0.5 * 14 = 7 vials.
    
    greedy_phone_call:
      Checks only F1-F3 (ignores usable capacity and shelf life).
      Allocates min(shortage=50, at_risk=50) = 50 vials to H3.
      Moves 43 units of WASTE to H3 (waste_moved = 43)!
    
    greedy_f4:
      Checks full F1-F6 and allocates only usable quantity = 7 vials.
      Moves 0 units of waste!
    """
    snapshot = {
        "today": "2026-11-01",
        "facilities": [
            {"id": "H4", "name": "SIM-PHC Hesaraghatta", "cold_storage_available": False},
            {"id": "H3", "name": "SIM-CHC Yelahanka", "cold_storage_available": True},
        ],
        "drugs": [
            {"code": "INS-REG", "name": "Insulin Regular", "category": "V", "unit": "vial", "pack_size": 1, "storage_condition": "cold_chain", "min_residual_days": 10, "unit_cost_inr": 145.50},
        ],
        "routes": [
            {"id": "R-H4-H3", "source_facility_id": "H4", "destination_facility_id": "H3", "distance_km": 15.0, "transit_hours": 1.0, "cold_chain_compliant": True, "status": "active"},
        ],
        "vehicles": [
            {"id": "CV-01", "name": "Cold Van 1", "cold_chain_capable": True, "is_active": True, "current_temp_c": 4.5},
        ],
        "lots": [
            {"id": 101, "facility_id": "H4", "drug_code": "INS-REG", "batch_no": "LOT-INS-H4-01", "expiry": "2026-11-19", "quantity": 50},
        ],
        "positions": [
            {"facility_id": "H4", "drug_code": "INS-REG", "effective_stock": 0, "at_risk_stock": 50, "reserve": 0, "shortage": 0},
            {"facility_id": "H3", "drug_code": "INS-REG", "effective_stock": 0, "at_risk_stock": 0, "reserve": 5, "shortage": 50},
        ],
        "forecasts": [
            {"facility_id": "H3", "drug_code": "INS-REG", "effective_daily_rate": 0.5},
        ],
        "policies": [],
    }

    # 1. Greedy Phone Call
    orders_phone = greedy_phone_call(snapshot)
    assert len(orders_phone) == 1
    # Transfers 50 vials without checking usable capacity
    assert orders_phone[0].quantity == 50
    metrics_phone = calculate_plan_metrics(orders_phone, snapshot)
    # Waste moved is 50 - 7 = 43 vials!
    assert metrics_phone["waste_moved_units"] == 43

    # 2. Greedy F4
    orders_f4 = greedy_f4(snapshot)
    assert len(orders_f4) == 1
    # Only allocates usable quantity = 7 vials
    assert orders_f4[0].quantity == 7
    metrics_f4 = calculate_plan_metrics(orders_f4, snapshot)
    assert metrics_f4["waste_moved_units"] == 0
    assert metrics_f4["expiry_avoided_units"] == 7
