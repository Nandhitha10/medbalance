"""Pure deterministic feasibility rules F1-F6 per CLAUDE.md §5."""

from datetime import date, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple


VEN_WEIGHTS: Dict[str, float] = {
    "V": 3.0,
    "E": 2.0,
    "N": 1.0,
}


def get_ven_weight(category: Optional[str]) -> float:
    """Resolve VEN priority multiplier pi_g."""
    if not category:
        return 1.0
    return VEN_WEIGHTS.get(str(category).upper(), 1.0)


def check_f1_rule(source_id: str, dest_id: str) -> Tuple[bool, Optional[str]]:
    """F1 (Identity): Source and destination must be distinct facilities."""
    if source_id == dest_id:
        return False, "F1 identity: Cannot transfer lot to the same facility"
    return True, None


def check_f2_rule(route: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """F2 (Route OK): A safe, active route must exist between facilities."""
    if not route:
        return False, "F2 route: No route exists between source and destination"
    status = route.get("status", "active")
    if status == "unsafe" or status == "closed":
        reason = route.get("status_reason", "Route is unsafe or closed")
        return False, f"F2 route: Transit route is unsafe ({reason})"
    return True, None


def check_f3_rule(
    is_cold_drug: bool,
    dest_has_cold_storage: bool,
    route_is_cold: bool,
    vehicles: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """F3 (Cold Chain): Cold drug requires destination cold storage, cold route, and active cold vehicle in 2-8°C."""
    if not is_cold_drug:
        return True, None

    if not dest_has_cold_storage:
        return False, "F3 cold chain: Destination cold storage is unavailable or under repair"

    if not route_is_cold:
        return False, "F3 cold chain: Transit route lacks cold chain compliance"

    # Check for active cold-chain vehicle without excursion (2°C - 8°C)
    active_cold_vehicles = [
        v for v in vehicles
        if v.get("is_active", True)
        and v.get("cold_chain_capable", False)
        and (2.0 <= float(v.get("current_temp_c", 4.0)) <= 8.0)
    ]
    if not active_cold_vehicles:
        return False, "F3 cold chain: No active cold transport vehicle available within 2-8°C (temperature excursion)"

    return True, None


def check_f4_rule(
    lot_qty: int,
    lot_expiry: date,
    today: date,
    destination_daily_rate: float,
    transit_hours: float,
    min_residual_days: int = 14,
    destination_stock_expiring_before: int = 0,
    buffer_days: int = 2,
) -> Tuple[bool, Optional[str], int]:
    """F4 (Usable & Shelf Life): Usable > 0 and residual shelf life >= drug.min_residual_days.
    
    Returns (passed, failure_reason, usable_quantity).
    """
    transit_days = math.ceil(transit_hours / 24.0)
    arrival_date = today + timedelta(days=transit_days)
    residual_days_at_arrival = (lot_expiry - arrival_date).days

    # Enforce minimum residual shelf life at arrival
    if residual_days_at_arrival < min_residual_days:
        return (
            False,
            f"F4 shelf life: Residual shelf life at arrival ({residual_days_at_arrival} days) is less than required minimum ({min_residual_days} days)",
            0,
        )

    # Calculate usable consumption window
    effective_days = (lot_expiry - today).days - transit_days - buffer_days
    if effective_days <= 0:
        return False, f"F4 usable: Non-positive consumption window ({effective_days} days) before expiry", 0

    if destination_daily_rate <= 0.0:
        return False, "F4 usable: Destination has zero projected consumption rate for this drug", 0

    consumption_capacity = math.floor(destination_daily_rate * effective_days)
    net_capacity = max(0, consumption_capacity - destination_stock_expiring_before)
    usable_qty = min(lot_qty, net_capacity)

    if usable_qty <= 0:
        return (
            False,
            f"F4 usable: Usable quantity is 0 (capacity {consumption_capacity} units fully absorbed by earlier-expiring stock {destination_stock_expiring_before})",
            0,
        )

    return True, None, usable_qty


def check_f5_rule(chunk_qty: int, transferable_qty: int) -> Tuple[bool, Optional[str]]:
    """F5 (Reserve Protection): Transferred quantity must not exceed transferable quantity."""
    if transferable_qty <= 0:
        return False, "F5 reserve: Lot has zero transferable quantity (fully reserved)"
    if chunk_qty > transferable_qty:
        return False, f"F5 reserve: Quantity {chunk_qty} violates protected reserve (transferable: {transferable_qty})"
    return True, None


def check_f6_rule(drug_code: str, is_controlled: bool = False) -> Tuple[bool, Optional[str]]:
    """F6 (Controlled Substances): Schedule X narcotics cannot be redistributed automatically."""
    if is_controlled or drug_code in ("MOR-10", "FNT-50"):
        return False, f"F6 controlled substance: Drug {drug_code} is a Schedule X narcotic and cannot be redistributed automatically"
    return True, None


def evaluate_feasibility(
    source_id: str,
    dest_id: str,
    lot_qty: int,
    transferable_qty: int,
    lot_expiry: date,
    today: date,
    drug: Dict[str, Any],
    route: Optional[Dict[str, Any]],
    dest_facility: Dict[str, Any],
    vehicles: List[Dict[str, Any]],
    destination_daily_rate: float,
    destination_stock_expiring_before: int = 0,
) -> Tuple[bool, List[Dict[str, str]], int]:
    """Evaluate all rules F1-F6, collecting ALL failure reasons for regret and copilot analysis."""
    failed_rules: List[Dict[str, str]] = []

    # F1
    ok_f1, reason_f1 = check_f1_rule(source_id, dest_id)
    if not ok_f1:
        failed_rules.append({"rule": "F1", "detail": reason_f1 or ""})

    # F2
    ok_f2, reason_f2 = check_f2_rule(route)
    if not ok_f2:
        failed_rules.append({"rule": "F2", "detail": reason_f2 or ""})

    # F3
    is_cold = drug.get("storage_condition") == "cold_chain" or drug.get("cold_chain", False)
    has_cold_storage = bool(dest_facility.get("cold_storage_available", False) or dest_facility.get("has_cold_storage", False))
    if dest_facility.get("cold_storage_status") == "FAIL" or dest_facility.get("ilr_status") in ("offline", "under_repair"):
        has_cold_storage = False
    route_cold = bool(route.get("cold_chain_compliant", False) or route.get("cold_chain_capable", False)) if route else False
    ok_f3, reason_f3 = check_f3_rule(is_cold, has_cold_storage, route_cold, vehicles)
    if not ok_f3:
        failed_rules.append({"rule": "F3", "detail": reason_f3 or ""})

    # F5
    ok_f5, reason_f5 = check_f5_rule(lot_qty, transferable_qty)
    if not ok_f5:
        failed_rules.append({"rule": "F5", "detail": reason_f5 or ""})

    # F6
    is_controlled = bool(drug.get("is_controlled", False))
    ok_f6, reason_f6 = check_f6_rule(drug.get("code", ""), is_controlled)
    if not ok_f6:
        failed_rules.append({"rule": "F6", "detail": reason_f6 or ""})

    # F4
    transit_hours = float(route.get("transit_hours", 2.0)) if route else 2.0
    min_res_days = int(drug.get("min_residual_days", 14))
    ok_f4, reason_f4, usable_qty = check_f4_rule(
        lot_qty=lot_qty,
        lot_expiry=lot_expiry,
        today=today,
        destination_daily_rate=destination_daily_rate,
        transit_hours=transit_hours,
        min_residual_days=min_res_days,
        destination_stock_expiring_before=destination_stock_expiring_before,
    )
    if not ok_f4:
        failed_rules.append({"rule": "F4", "detail": reason_f4 or ""})

    is_feasible = (len(failed_rules) == 0)
    return is_feasible, failed_rules, usable_qty

