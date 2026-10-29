"""Unit tests for FEFO mathematics and inventory position modeling."""

from datetime import date, timedelta
import pytest
from medbal_common.fefo import calculate_fefo_position, calculate_usable_quantity


def test_fefo_worked_example():
    """Worked example per CLAUDE.md: 50 vials, rate 2/day, 14 usable days -> 28 effective stock, 22 at risk."""
    today = date(2026, 11, 1)
    expiry = today + timedelta(days=14)

    lots = [
        {
            "batch_no": "LOT-INS-01",
            "expiry": expiry,
            "quantity": 50,
        }
    ]

    result = calculate_fefo_position(
        facility_id="H1",
        drug_code="INS-REG",
        lots=lots,
        daily_rate=2.0,
        today=today,
        min_reserve_days=7,
        target_days=21,
    )

    # 14 days * 2 vials/day = 28 effective vials
    assert result.stock_on_hand == 50
    assert result.effective_stock == 28
    # 50 - 28 = 22 at risk vials
    assert result.at_risk_stock == 22
    assert len(result.lots) == 1
    assert result.lots[0].effective_quantity == 28
    assert result.lots[0].at_risk_quantity == 22


def test_fefo_reserve_protection_from_longest_dated_lots():
    """Reserve R is protected from the longest-dated (latest expiring) lots."""
    today = date(2026, 11, 1)

    # Three lots with different expiries
    lots = [
        {"batch_no": "LOT-NEAR", "expiry": today + timedelta(days=10), "quantity": 30},
        {"batch_no": "LOT-MID", "expiry": today + timedelta(days=20), "quantity": 40},
        {"batch_no": "LOT-FAR", "expiry": today + timedelta(days=40), "quantity": 50},
    ]

    # rate = 2.0/day. min_reserve_days = 10 -> Reserve R = ceil(2.0 * 10) = 20
    # Reserve of 20 should be taken exclusively from LOT-FAR (the longest dated lot)
    result = calculate_fefo_position(
        facility_id="H1",
        drug_code="AMOX-500",
        lots=lots,
        daily_rate=2.0,
        today=today,
        min_reserve_days=10,
        target_days=30,
        lead_time_days=3,
    )

    assert result.reserve == 20

    lot_map = {lt.batch_no: lt for lt in result.lots}

    # LOT-FAR: 50 total, 20 reserved, 30 transferable
    assert lot_map["LOT-FAR"].reserved_quantity == 20
    assert lot_map["LOT-FAR"].transferable_quantity == 30

    # LOT-NEAR and LOT-MID should have 0 reserved, all transferable
    assert lot_map["LOT-NEAR"].reserved_quantity == 0
    assert lot_map["LOT-NEAR"].transferable_quantity == 30
    assert lot_map["LOT-MID"].reserved_quantity == 0
    assert lot_map["LOT-MID"].transferable_quantity == 40


def test_fefo_shortage_calculation():
    """Shortage n = max(0, ceil(r * target_days) - effective_stock)."""
    today = date(2026, 11, 1)

    lots = [
        {"batch_no": "LOT-01", "expiry": today + timedelta(days=5), "quantity": 10},
    ]

    # rate = 4/day, target_days = 14 -> target demand = 56
    # 5 days * 4 = 20 max possible consumption, but only 10 vials available -> effective_stock = 10
    # Shortage = 56 - 10 = 46
    result = calculate_fefo_position(
        facility_id="H2",
        drug_code="INS-REG",
        lots=lots,
        daily_rate=4.0,
        today=today,
        target_days=14,
    )

    assert result.stock_on_hand == 10
    assert result.effective_stock == 10
    assert result.at_risk_stock == 0
    assert result.shortage == 46


def test_calculate_usable_quantity_rule_f4():
    """Usable(k,d) = min(q_k, max(0, r_d * (expiry - today - transit - buffer) - S_d(<expiry)))."""
    today = date(2026, 11, 1)
    expiry = today + timedelta(days=20)

    # Destination rate: 2/day, transit_hours: 24 (1 day), buffer_days: 2
    # Effective days = 20 - 1 - 2 = 17 days
    # Destination capacity = 17 * 2 = 34
    # Destination stock expiring before lot = 10
    # Net usable = 34 - 10 = 24
    usable = calculate_usable_quantity(
        source_lot_qty=30,
        source_lot_expiry=expiry,
        today=today,
        destination_daily_rate=2.0,
        transit_hours=24.0,
        destination_stock_expiring_before_lot=10,
        buffer_days=2,
    )

    assert usable == 24
