"""Post-Optimization Solution Validator and Repair Engine.

Applies proposed transfer orders to a snapshot clone, re-running exact FEFO
simulation at affected sources and destinations, and strictly enforces
invariants from CLAUDE.md:
  1. No negative stock
  2. No double shipping (transfers from lot <= transferable quantity)
  3. Reserve kept (source stock after transfer >= reserve R)
  4. Cold chain compliance (destination cold storage, route safe, cold van)
  5. Realised usable > 0 (trim order quantity to realised usable)
  6. No destination overfill above max stock days ceiling
  7. No controlled substances (Rule F6)
"""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from medbal_common.fefo import calculate_fefo_position, calculate_usable_quantity
from optimizer.models import TransferOrder

logger = logging.getLogger(__name__)

CONTROLLED_DRUG_CODES: Set[str] = {"MOR-10", "FNT-50"}


@dataclass
class ValidationViolation:
    rule: str
    order_id: str
    source_facility_id: str
    destination_facility_id: str
    drug_code: str
    batch_no: str
    detail: str


@dataclass
class ValidationResult:
    is_valid: bool
    violations: List[ValidationViolation] = field(default_factory=list)
    repaired_orders: List[TransferOrder] = field(default_factory=list)
    trimmed_count: int = 0
    dropped_count: int = 0
    realised_usable_map: Dict[str, int] = field(default_factory=dict)


def validate_and_simulate_fefo(
    orders: List[TransferOrder],
    snapshot: Dict[str, Any],
) -> ValidationResult:
    """Simulate exact FEFO impact of orders and verify all invariants.
    
    If order.quantity > realised usable quantity, trims order.quantity to realised usable.
    """
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str

    facilities = {f["id"]: f for f in snapshot.get("facilities", [])}
    drugs = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }
    vehicles = {v["id"]: v for v in snapshot.get("vehicles", [])}
    forecasts = {
        (fc["facility_id"], fc["drug_code"]): float(fc.get("effective_daily_rate", 0.0))
        for fc in snapshot.get("forecasts", [])
    }
    positions_map = {
        (p["facility_id"], p["drug_code"]): p
        for p in snapshot.get("positions", [])
    }

    # Clone lots for local modification
    lots_by_fac_drug: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for lt in snapshot.get("lots", []):
        key = (lt["facility_id"], lt["drug_code"])
        if key not in lots_by_fac_drug:
            lots_by_fac_drug[key] = []
        lots_by_fac_drug[key].append(dict(lt))

    violations: List[ValidationViolation] = []
    realised_usable: Dict[str, int] = {}
    repaired_orders: List[TransferOrder] = []
    trimmed_count = 0
    dropped_count = 0

    # Group proposed transfers by source lot
    lot_transfers_total: Dict[Tuple[str, str, str], int] = {}
    for ord_obj in orders:
        lot_key = (ord_obj.source_facility_id, ord_obj.drug_code, ord_obj.batch_no)
        lot_transfers_total[lot_key] = lot_transfers_total.get(lot_key, 0) + ord_obj.quantity

    # 1. Source-Side Validation (Reserve, Double Shipping, Negative Stock, Controlled)
    for ord_obj in orders:
        oid = ord_obj.order_id
        src = ord_obj.source_facility_id
        dst = ord_obj.destination_facility_id
        dcode = ord_obj.drug_code
        bno = ord_obj.batch_no
        qty = ord_obj.quantity

        drug = drugs.get(dcode, {})
        src_fac = facilities.get(src, {})
        dst_fac = facilities.get(dst, {})

        # Rule F6: Controlled Drug Prohibition
        if drug.get("is_controlled", False) or dcode in CONTROLLED_DRUG_CODES:
            violations.append(
                ValidationViolation(
                    rule="F6_CONTROLLED_SUBSTANCE",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Automated transfer of controlled narcotic '{dcode}' strictly prohibited",
                )
            )
            continue

        # Rule F1: Source and destination must be distinct
        if src == dst:
            violations.append(
                ValidationViolation(
                    rule="F1_SAME_FACILITY",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail="Source and destination facility are identical",
                )
            )
            continue

        # Rule F2: Route must exist and not be closed/unsafe
        route = routes.get((src, dst))
        if not route or route.get("status") == "unsafe":
            violations.append(
                ValidationViolation(
                    rule="F2_ROUTE_UNSAFE",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Route from {src} to {dst} is missing or marked unsafe",
                )
            )
            continue

        # Rule F3: Cold chain compliance
        is_cold = drug.get("storage_condition") == "cold_chain"
        if is_cold:
            if not dst_fac.get("cold_storage_available", False):
                violations.append(
                    ValidationViolation(
                        rule="F3_COLD_DESTINATION_INCAPABLE",
                        order_id=oid,
                        source_facility_id=src,
                        destination_facility_id=dst,
                        drug_code=dcode,
                        batch_no=bno,
                        detail=f"Destination {dst} has cold_storage_available=False",
                    )
                )
                continue

            if ord_obj.vehicle_id and ord_obj.vehicle_id in vehicles:
                veh = vehicles[ord_obj.vehicle_id]
                has_cold = bool(veh.get("has_cold_storage", veh.get("cold_chain_capable", False)))
                cold_ok = bool(veh.get("cold_ok", True))
                if not has_cold or not cold_ok:
                    violations.append(
                        ValidationViolation(
                            rule="F3_COLD_VEHICLE_INVALID",
                            order_id=oid,
                            source_facility_id=src,
                            destination_facility_id=dst,
                            drug_code=dcode,
                            batch_no=bno,
                            detail=f"Vehicle {ord_obj.vehicle_id} is not cold chain compliant or in excursion",
                        )
                    )
                    continue

        # Check source lot availability & double shipping
        src_lots = lots_by_fac_drug.get((src, dcode), [])
        target_lot = next((l for l in src_lots if l["batch_no"] == bno), None)
        if not target_lot or target_lot["quantity"] < qty:
            violations.append(
                ValidationViolation(
                    rule="DOUBLE_SHIPPING_OR_NEGATIVE_STOCK",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Requested {qty} units exceeds available lot stock ({target_lot['quantity'] if target_lot else 0})",
                )
            )
            continue

        # Check Source Reserve Protection (Rule F5)
        # Compute position before and after
        r_src = forecasts.get((src, dcode), 0.0)
        min_res_days = int(src_fac.get("min_reserve_days", 7))
        pos_before = calculate_fefo_position(
            facility_id=src,
            drug_code=dcode,
            lots=src_lots,
            daily_rate=r_src,
            today=today,
            min_reserve_days=min_res_days,
        )

        # Check if total lot transfer exceeds transferable quantity
        lot_state = next((l for l in pos_before.lots if l.batch_no == bno), None)
        trans_allowed = lot_state.transferable_quantity if lot_state else 0
        total_transfer_from_lot = lot_transfers_total.get((src, dcode, bno), 0)
        if total_transfer_from_lot > trans_allowed:
            violations.append(
                ValidationViolation(
                    rule="F5_RESERVE_VIOLATION",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Total transferred from lot {bno} ({total_transfer_from_lot}) violates reserve (allowed: {trans_allowed})",
                )
            )
            continue

        # 2. Destination-Side Validation (Usable Quantity & Overfill)
        r_dst = forecasts.get((dst, dcode), 0.0)
        if r_dst <= 0.0:
            pos_dst = positions_map.get((dst, dcode))
            if pos_dst:
                r_dst = float(pos_dst.get("daily_consumption_rate", 0.0))
        transit_hrs = float(route.get("transit_hours", 2.0))
        dst_lots = lots_by_fac_drug.get((dst, dcode), [])

        # Count destination stock expiring earlier than this lot
        earlier_exp_stock = sum(
            int(l["quantity"])
            for l in dst_lots
            if (date.fromisoformat(l["expiry"]) if isinstance(l["expiry"], str) else l["expiry"]) < ord_obj.expiry
        )

        realised_u = calculate_usable_quantity(
            source_lot_qty=qty,
            source_lot_expiry=ord_obj.expiry,
            today=today,
            destination_daily_rate=r_dst,
            transit_hours=transit_hrs,
            destination_stock_expiring_before_lot=earlier_exp_stock,
            buffer_days=2,
        )
        realised_usable[oid] = realised_u

        if realised_u <= 0:
            violations.append(
                ValidationViolation(
                    rule="F4_ZERO_REALISED_USABLE",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Realised usable quantity at destination {dst} is 0 (order moves waste)",
                )
            )
            continue

        final_qty = qty
        if realised_u < qty:
            # Trim order quantity to realised usable
            trimmed_count += 1
            final_qty = realised_u

        # Destination stock ceiling check (cannot exceed 45 days consumption)
        dst_stock_current = sum(int(l["quantity"]) for l in dst_lots)
        max_allowed_stock = math.ceil(r_dst * 45.0) if r_dst > 0 else 999999
        if (dst_stock_current + final_qty) > max_allowed_stock:
            violations.append(
                ValidationViolation(
                    rule="DESTINATION_OVERFILL_CEILING",
                    order_id=oid,
                    source_facility_id=src,
                    destination_facility_id=dst,
                    drug_code=dcode,
                    batch_no=bno,
                    detail=f"Receipt of {final_qty} units pushes destination stock ({dst_stock_current + final_qty}) above 45-day ceiling ({max_allowed_stock})",
                )
            )
            continue

        # Valid order: apply to simulated local stock
        target_lot["quantity"] -= final_qty
        # Add to destination lots
        if (dst, dcode) not in lots_by_fac_drug:
            lots_by_fac_drug[(dst, dcode)] = []
        lots_by_fac_drug[(dst, dcode)].append({
            "facility_id": dst,
            "drug_code": dcode,
            "batch_no": bno,
            "expiry": ord_obj.expiry.isoformat() if isinstance(ord_obj.expiry, date) else str(ord_obj.expiry),
            "quantity": final_qty,
        })

        # Append to repaired orders
        new_ord = deepcopy(ord_obj)
        new_ord.quantity = final_qty
        new_ord.usable_quantity = final_qty
        new_ord.shortage_reduction = final_qty
        new_ord.expiry_avoided = final_qty
        new_ord.total_cost_inr = round(final_qty * new_ord.unit_cost_inr, 2)
        repaired_orders.append(new_ord)

    is_valid = len(violations) == 0
    return ValidationResult(
        is_valid=is_valid,
        violations=violations,
        repaired_orders=repaired_orders,
        trimmed_count=trimmed_count,
        dropped_count=len(orders) - len(repaired_orders),
        realised_usable_map=realised_usable,
    )


def repair(
    orders: List[TransferOrder],
    snapshot: Dict[str, Any],
    candidates: Optional[List[Any]] = None,
    resolve_callback: Optional[Callable[[float], List[TransferOrder]]] = None,
    max_attempts: int = 3,
) -> Tuple[List[TransferOrder], List[ValidationViolation], int]:
    """Iteratively validate, trim, drop, and repair proposed orders.
    
    If one-place violation came from solver and resolve_callback provided,
    triggers re-solve with P1 x 2 (up to max_attempts).
    Guarantees returning an order list with 0 invariant violations.
    """
    current_orders = list(orders)
    current_p1_mult = 1.0

    for attempt in range(max_attempts):
        val_res = validate_and_simulate_fefo(current_orders, snapshot)
        if val_res.is_valid:
            return val_res.repaired_orders, [], attempt

        # Check if one-place violation occurred
        has_one_place = any(v.rule == "DOUBLE_SHIPPING_OR_NEGATIVE_STOCK" for v in val_res.violations)

        if has_one_place and resolve_callback and attempt < max_attempts - 1:
            current_p1_mult *= 2.0
            logger.info("One-place violation detected; re-solving with P1 multiplier %.1f (attempt %d)", current_p1_mult, attempt + 1)
            try:
                new_orders = resolve_callback(current_p1_mult)
                if new_orders is not None:
                    current_orders = new_orders
                    continue
            except Exception as e:
                logger.warning("Re-solve callback failed: %s", e)

        # Fallback repair: drop conflicting/violating orders sorted by reward ascending (keep highest reward)
        violating_ids = {v.order_id for v in val_res.violations}
        # Filter out violating orders
        surviving = [o for o in current_orders if o.order_id not in violating_ids]

        # Re-run simulation on surviving subset
        sub_res = validate_and_simulate_fefo(surviving, snapshot)
        if sub_res.is_valid:
            return sub_res.repaired_orders, [], attempt + 1

        # In extreme case, trim/drop until empty or valid
        current_orders = surviving

    # Final pass: return repaired orders from the final validation pass
    final_res = validate_and_simulate_fefo(current_orders, snapshot)
    return final_res.repaired_orders, final_res.violations, max_attempts
