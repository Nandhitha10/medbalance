"""First-Expiry-First-Out (FEFO) and inventory position mathematics.

Shared between core-api and optimizer per CLAUDE.md §5.
"""

from dataclasses import dataclass, field
from datetime import date
import math
from typing import Any, Dict, List, Optional


@dataclass
class LotState:
    batch_no: str
    expiry: date
    quantity: int
    days_to_expiry: int
    effective_quantity: int = 0
    at_risk_quantity: int = 0
    reserved_quantity: int = 0
    transferable_quantity: int = 0


@dataclass
class PositionResult:
    facility_id: str
    drug_code: str
    daily_consumption_rate: float
    stock_on_hand: int
    effective_stock: int
    at_risk_stock: int
    reserve: int
    shortage: int
    lots: List[LotState] = field(default_factory=list)


def calculate_fefo_position(
    facility_id: str,
    drug_code: str,
    lots: List[Dict[str, Any]],
    daily_rate: float,
    today: date,
    min_reserve_days: int = 7,
    target_days: int = 21,
    lead_time_days: int = 3,
) -> PositionResult:
    """Calculate FEFO stock position, effective stock, at-risk units, and reserve protection.

    Rules from CLAUDE.md §5:
    - FEFO: Consumption always uses the earliest-expiring lot first.
    - Effective stock: Units that will be consumed before their expiry under FEFO at the forecast rate.
    - At-risk: Units that will expire unconsumed under FEFO.
    - Reserve R = max(ceil(r * min_reserve_days), ceil(r * lead_time * 1.2)), protected from longest-dated lots.
    - Shortage n = max(0, ceil(r * target_days) - effective_stock).
    """
    total_stock_on_hand = sum(int(lt["quantity"]) for lt in lots)

    # 1. Parse and sort lots ascending by expiry (earliest expiring first)
    parsed_lots: List[LotState] = []
    for lt in lots:
        exp = lt["expiry"]
        if isinstance(exp, str):
            exp = date.fromisoformat(exp)
        days = (exp - today).days
        parsed_lots.append(
            LotState(
                batch_no=str(lt["batch_no"]),
                expiry=exp,
                quantity=int(lt["quantity"]),
                days_to_expiry=max(0, days),
            )
        )
    parsed_lots.sort(key=lambda l: (l.expiry, l.batch_no))

    # 2. FEFO Consumption calculation
    # Simulate consumption timeline: units consumed before expiry
    # Total cumulative demand consumed up to each lot's expiry
    r = max(0.0, float(daily_rate))
    cumulative_consumed = 0

    for lot in parsed_lots:
        if r <= 0.0 or lot.days_to_expiry <= 0:
            lot.effective_quantity = 0
            lot.at_risk_quantity = lot.quantity
            continue

        # Total units that could possibly be consumed from day 0 to lot.expiry
        max_possible_consumed_by_expiry = math.floor(r * lot.days_to_expiry)
        # Remaining consumption capacity available for this lot
        capacity_for_lot = max(0, max_possible_consumed_by_expiry - cumulative_consumed)

        effective_from_lot = min(lot.quantity, capacity_for_lot)
        lot.effective_quantity = effective_from_lot
        lot.at_risk_quantity = lot.quantity - effective_from_lot
        cumulative_consumed += effective_from_lot

    total_effective_stock = sum(l.effective_quantity for l in parsed_lots)
    total_at_risk_stock = sum(l.at_risk_quantity for l in parsed_lots)

    # 3. Reserve Protection:
    # R = max(ceil(r * min_reserve_days), ceil(r * lead_time * 1.2))
    # Protected from the LONGEST-DATED lots (latest expiring first)
    reserve_r = max(
        math.ceil(r * min_reserve_days),
        math.ceil(r * lead_time_days * 1.2),
    )

    remaining_reserve_to_protect = reserve_r
    # Iterate in reverse (longest-dated lots first)
    for lot in reversed(parsed_lots):
        if remaining_reserve_to_protect <= 0:
            lot.reserved_quantity = 0
        else:
            protect_amount = min(lot.quantity, remaining_reserve_to_protect)
            lot.reserved_quantity = protect_amount
            remaining_reserve_to_protect -= protect_amount

        # Transferable per lot: quantity not protected by reserve
        lot.transferable_quantity = max(0, lot.quantity - lot.reserved_quantity)

    # 4. Shortage calculation:
    # Shortage n = max(0, ceil(r * target_days) - effective_stock)
    target_demand = math.ceil(r * target_days)
    shortage_n = max(0, target_demand - total_effective_stock)

    return PositionResult(
        facility_id=facility_id,
        drug_code=drug_code,
        daily_consumption_rate=r,
        stock_on_hand=total_stock_on_hand,
        effective_stock=total_effective_stock,
        at_risk_stock=total_at_risk_stock,
        reserve=reserve_r,
        shortage=shortage_n,
        lots=parsed_lots,
    )


def calculate_usable_quantity(
    source_lot_qty: int,
    source_lot_expiry: date,
    today: date,
    destination_daily_rate: float,
    transit_hours: float,
    destination_stock_expiring_before_lot: int = 0,
    buffer_days: int = 2,
) -> int:
    """Calculate usable units at destination under Rule F4.

    Usable(k,d) = min(q_k, max(0, r_d * (expiry - today - transit - buffer) - S_d(<expiry)))
    """
    days_to_expiry = (source_lot_expiry - today).days
    transit_days = math.ceil(transit_hours / 24.0)
    effective_days = days_to_expiry - transit_days - buffer_days

    if effective_days <= 0 or destination_daily_rate <= 0.0:
        return 0

    dest_consumption_capacity = math.floor(destination_daily_rate * effective_days)
    net_usable = max(0, dest_consumption_capacity - destination_stock_expiring_before_lot)
    return min(source_lot_qty, net_usable)
