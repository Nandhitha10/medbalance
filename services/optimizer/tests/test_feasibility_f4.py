"""Tests for Rule F4 (Usable Quantity, Shelf Life, Destination Queue) and Feasibility Rules F1-F6.

Written FIRST according to plan mode workflow.
"""

from datetime import date, timedelta
import pytest
from medbal_common.fefo import calculate_usable_quantity


def test_f4_worked_example():
    """Worked example: 50 vials, destination rate 2/day, 14 usable days, no dst stock -> usable 28.
    
    Setup:
    - Source lot: 50 vials
    - Expiry: today + 17 days
    - Transit: 24 hours (1 day)
    - Buffer: 2 days
    - Effective days = 17 - 1 - 2 = 14 usable days
    - Destination consumption rate: 2.0 / day
    - Destination earlier-expiring stock: 0
    - Consumption capacity: floor(2.0 * 14) = 28
    - Usable quantity: min(50, 28) = 28
    """
    today = date(2026, 11, 1)
    expiry = today + timedelta(days=17)
    
    usable = calculate_usable_quantity(
        source_lot_qty=50,
        source_lot_expiry=expiry,
        today=today,
        destination_daily_rate=2.0,
        transit_hours=24.0,  # 1 transit day
        destination_stock_expiring_before_lot=0,
        buffer_days=2,
    )
    assert usable == 28


def test_f4_destination_queue_case():
    """Destination holds 10 earlier-expiring units -> usable drops from 28 to 18.
    
    Net usable capacity = max(0, 28 - 10) = 18.
    Usable quantity = min(50, 18) = 18.
    """
    today = date(2026, 11, 1)
    expiry = today + timedelta(days=17)
    
    usable = calculate_usable_quantity(
        source_lot_qty=50,
        source_lot_expiry=expiry,
        today=today,
        destination_daily_rate=2.0,
        transit_hours=24.0,
        destination_stock_expiring_before_lot=10,
        buffer_days=2,
    )
    assert usable == 18


def test_f4_destination_queue_blocks_all():
    """Destination holds earlier-expiring units exceeding the consumption capacity -> usable is 0."""
    today = date(2026, 11, 1)
    expiry = today + timedelta(days=17)
    
    usable = calculate_usable_quantity(
        source_lot_qty=50,
        source_lot_expiry=expiry,
        today=today,
        destination_daily_rate=2.0,
        transit_hours=24.0,
        destination_stock_expiring_before_lot=35,  # > 28
        buffer_days=2,
    )
    assert usable == 0


def test_f4_residual_shelf_life_rule():
    """F4 must enforce that residual shelf life at arrival >= drug.min_residual_days."""
    from optimizer.feasibility import check_f4_rule
    
    today = date(2026, 11, 1)
    # Transit: 1 day -> arrives on 2026-11-02
    transit_hours = 24.0
    
    # Case A: Lot expires on 2026-11-25 -> residual at arrival = 23 days.
    # Drug requires min_residual_days = 30 -> FAILS!
    passed_a, reason_a, usable_a = check_f4_rule(
        lot_qty=50,
        lot_expiry=date(2026, 11, 25),
        today=today,
        destination_daily_rate=5.0,
        transit_hours=transit_hours,
        min_residual_days=30,
        destination_stock_expiring_before=0,
    )
    assert passed_a is False
    assert "residual shelf life" in reason_a.lower()
    
    # Case B: Lot expires on 2026-12-15 -> residual at arrival = 43 days.
    # Drug requires min_residual_days = 30 -> PASSES!
    passed_b, reason_b, usable_b = check_f4_rule(
        lot_qty=50,
        lot_expiry=date(2026, 12, 15),
        today=today,
        destination_daily_rate=2.0,
        transit_hours=transit_hours,
        min_residual_days=30,
        destination_stock_expiring_before=0,
    )
    assert passed_b is True
    assert usable_b > 0


def test_f1_identity_rule():
    """F1: Source and destination facility must be distinct."""
    from optimizer.feasibility import check_f1_rule
    
    assert check_f1_rule(source_id="H1", dest_id="H2")[0] is True
    passed, reason = check_f1_rule(source_id="H1", dest_id="H1")
    assert passed is False
    assert "same facility" in reason.lower()


def test_f2_route_rule():
    """F2: A safe route must exist between source and destination."""
    from optimizer.feasibility import check_f2_rule
    
    # Active route
    assert check_f2_rule(route={"status": "active", "transit_hours": 1.5})[0] is True
    
    # Unsafe route
    passed_unsafe, reason_unsafe = check_f2_rule(route={"status": "unsafe", "status_reason": "Landslide"})
    assert passed_unsafe is False
    assert "unsafe" in reason_unsafe.lower()
    
    # Missing route
    passed_missing, reason_missing = check_f2_rule(route=None)
    assert passed_missing is False
    assert "no route" in reason_missing.lower()


def test_f3_cold_chain_rule():
    """F3: If drug requires cold chain, destination must have cold storage, route must be compliant, and active cold vehicle available without excursion."""
    from optimizer.feasibility import check_f3_rule
    
    # Ambient drug always passes F3
    assert check_f3_rule(is_cold_drug=False, dest_has_cold_storage=False, route_is_cold=False, vehicles=[])[0] is True
    
    # Cold drug with all conditions met
    valid_vehicles = [{"is_active": True, "cold_chain_capable": True, "current_temp_c": 4.5}]
    passed, _ = check_f3_rule(
        is_cold_drug=True,
        dest_has_cold_storage=True,
        route_is_cold=True,
        vehicles=valid_vehicles,
    )
    assert passed is True
    
    # Negative Case 1: Destination lacks cold storage (e.g. H4 ILR under repair)
    passed_no_dest, reason_no_dest = check_f3_rule(
        is_cold_drug=True,
        dest_has_cold_storage=False,
        route_is_cold=True,
        vehicles=valid_vehicles,
    )
    assert passed_no_dest is False
    assert "destination cold storage" in reason_no_dest.lower()
    
    # Negative Case 2: Vehicle temperature excursion (e.g. CV-02 at 11.2 °C)
    excursion_vehicles = [{"is_active": True, "cold_chain_capable": True, "current_temp_c": 11.2}]
    passed_excursion, reason_excursion = check_f3_rule(
        is_cold_drug=True,
        dest_has_cold_storage=True,
        route_is_cold=True,
        vehicles=excursion_vehicles,
    )
    assert passed_excursion is False
    assert "temperature" in reason_excursion.lower()


def test_f5_reserve_rule():
    """F5: Quantity transferred must not exceed transferable quantity (must not violate reserve)."""
    from optimizer.feasibility import check_f5_rule
    
    # Transferable 30, chunk qty 20 -> ok
    assert check_f5_rule(chunk_qty=20, transferable_qty=30)[0] is True
    
    # Chunk qty 35 > transferable 30 -> violates reserve
    passed, reason = check_f5_rule(chunk_qty=35, transferable_qty=30)
    assert passed is False
    assert "reserve" in reason.lower()


def test_f6_controlled_substance_rule():
    """F6: Controlled drugs (e.g. MOR-10 Morphine) cannot be automatically transferred."""
    from optimizer.feasibility import check_f6_rule
    
    # Normal drug
    assert check_f6_rule(drug_code="INS-REG", is_controlled=False)[0] is True
    
    # Morphine / Controlled narcotic
    passed, reason = check_f6_rule(drug_code="MOR-10", is_controlled=True)
    assert passed is False
    assert "controlled" in reason.lower()
