"""Greedy baseline solvers: phone-call heuristic and F4-constrained greedy allocator."""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from optimizer.feasibility import check_f1_rule, check_f2_rule, check_f3_rule, evaluate_feasibility
from optimizer.models import TransferOrder


VEN_WEIGHTS = {"V": 3, "E": 2, "N": 1}


def _get_ven_weight(category: str) -> int:
    return VEN_WEIGHTS.get(str(category).upper(), 1)


def greedy_phone_call(snapshot: Dict[str, Any]) -> List[TransferOrder]:
    """Baseline 1: Models current manual district practice.
    
    1. Shortages sorted by VEN then size descending.
    2. Nearest source with at-risk stock.
    3. Checks F1–F3 only (ignores usable quantity & shelf life).
    4. May move waste (transfers stock that will still expire at destination).
    """
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str

    facilities = {f["id"]: f for f in snapshot.get("facilities", [])}
    drugs = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }
    vehicles = snapshot.get("vehicles", [])

    # Find shortages
    shortage_items: List[Dict[str, Any]] = []
    for pos in snapshot.get("positions", []):
        shortage = int(pos.get("shortage", 0))
        if shortage > 0:
            dcode = pos["drug_code"]
            drug = drugs.get(dcode, {})
            shortage_items.append({
                "facility_id": pos["facility_id"],
                "drug_code": dcode,
                "shortage": shortage,
                "ven_weight": _get_ven_weight(drug.get("category", "N")),
            })

    # Sort by VEN descending, then shortage size descending
    shortage_items.sort(key=lambda s: (s["ven_weight"], s["shortage"]), reverse=True)

    # Track available at-risk stock per lot
    lot_availability: Dict[str, int] = {}
    lots_by_drug: Dict[str, List[Dict[str, Any]]] = {}
    for lt in snapshot.get("lots", []):
        dcode = lt["drug_code"]
        bno = lt["batch_no"]
        qty = int(lt.get("quantity", 0))
        lot_availability[bno] = qty
        if dcode not in lots_by_drug:
            lots_by_drug[dcode] = []
        lots_by_drug[dcode].append(lt)

    orders: List[TransferOrder] = []
    order_seq = 1

    for item in shortage_items:
        dst_id = item["facility_id"]
        dcode = item["drug_code"]
        needed = item["shortage"]
        drug = drugs.get(dcode, {})
        dst_fac = facilities.get(dst_id, {})

        # Find potential source lots holding stock
        candidate_sources: List[Tuple[float, Dict[str, Any]]] = []
        for lt in lots_by_drug.get(dcode, []):
            src_id = lt["facility_id"]
            bno = lt["batch_no"]
            avail = lot_availability.get(bno, 0)
            if src_id == dst_id or avail <= 0:
                continue

            # F1 Check
            ok_f1, _ = check_f1_rule(src_id, dst_id)
            if not ok_f1:
                continue

            # F2 Check
            route = routes.get((src_id, dst_id))
            ok_f2, _ = check_f2_rule(route)
            if not ok_f2:
                continue

            # F3 Check
            is_cold = drug.get("storage_condition") == "cold_chain"
            has_cold = bool(dst_fac.get("cold_storage_available", False))
            route_cold = bool(route.get("cold_chain_compliant", False)) if route else False
            ok_f3, _ = check_f3_rule(is_cold, has_cold, route_cold, vehicles)
            if not ok_f3:
                continue

            dist = float(route.get("distance_km", 999.0)) if route else 999.0
            candidate_sources.append((dist, lt))

        # Sort candidate sources by distance ascending (nearest first)
        candidate_sources.sort(key=lambda x: x[0])

        for dist, lt in candidate_sources:
            if needed <= 0:
                break
            bno = lt["batch_no"]
            avail = lot_availability.get(bno, 0)
            if avail <= 0:
                continue

            # In greedy_phone_call, full at-risk/transferable quantity is moved up to shortage
            transfer_qty = min(needed, avail)
            lot_availability[bno] -= transfer_qty
            needed -= transfer_qty

            exp_val = lt.get("expiry")
            exp_date = date.fromisoformat(exp_val) if isinstance(exp_val, str) else exp_val
            unit_cost = float(drug.get("unit_cost_inr", 10.0))

            orders.append(
                TransferOrder(
                    order_id=f"DTA/BLR-U/2026/{order_seq:06d}",
                    plan_id="plan-phone-call",
                    source_facility_id=lt["facility_id"],
                    destination_facility_id=dst_id,
                    drug_code=dcode,
                    batch_no=bno,
                    expiry=exp_date,
                    quantity=transfer_qty,
                    unit_cost_inr=unit_cost,
                    total_cost_inr=round(transfer_qty * unit_cost, 2),
                    shortage_reduction=transfer_qty,
                    expiry_avoided=transfer_qty,
                    vehicle_id="CV-01" if drug.get("storage_condition") == "cold_chain" else "AV-01",
                    route_id=routes.get((lt["facility_id"], dst_id), {}).get("id"),
                    status="PROPOSED",
                )
            )
            order_seq += 1

    return orders


def greedy_f4(snapshot: Dict[str, Any]) -> List[TransferOrder]:
    """Baseline 2: Safe greedy allocator with full F1–F6 validation and usable quantities.
    
    1. Shortages sorted by VEN then size descending.
    2. Nearest feasible source.
    3. Evaluates full F1–F6:
       - strictly enforces residual shelf life (F4)
       - strictly enforces reserve protection (F5)
       - strictly enforces controlled substance prohibition (F6)
       - subtracts earlier expiring destination stock (F4)
    4. Allocates only the usable quantity (never moves waste).
    """
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str

    facilities = {f["id"]: f for f in snapshot.get("facilities", [])}
    drugs = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }
    vehicles = snapshot.get("vehicles", [])
    forecasts = {
        (fc["facility_id"], fc["drug_code"]): float(fc.get("effective_daily_rate", 0.0))
        for fc in snapshot.get("forecasts", [])
    }
    positions = {
        (p["facility_id"], p["drug_code"]): p
        for p in snapshot.get("positions", [])
    }

    # Destination lots map (for checking earlier-expiring stock)
    dest_lots_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for lt in snapshot.get("lots", []):
        key = (lt["facility_id"], lt["drug_code"])
        if key not in dest_lots_map:
            dest_lots_map[key] = []
        dest_lots_map[key].append(lt)

    for k in dest_lots_map:
        dest_lots_map[k].sort(
            key=lambda x: date.fromisoformat(x["expiry"]) if isinstance(x["expiry"], str) else x["expiry"]
        )

    # Find shortages
    shortage_items: List[Dict[str, Any]] = []
    for pos in snapshot.get("positions", []):
        shortage = int(pos.get("shortage", 0))
        if shortage > 0:
            dcode = pos["drug_code"]
            drug = drugs.get(dcode, {})
            # Exclude controlled substances from automated allocation
            if drug.get("is_controlled", False) or dcode in ("MOR-10", "FNT-50"):
                continue
            shortage_items.append({
                "facility_id": pos["facility_id"],
                "drug_code": dcode,
                "shortage": shortage,
                "ven_weight": _get_ven_weight(drug.get("category", "N")),
            })

    # Sort shortages: VEN descending, then shortage quantity descending
    shortage_items.sort(key=lambda s: (s["ven_weight"], s["shortage"]), reverse=True)

    # Track transferable quantity remaining per lot (respecting reserve F5)
    lot_transferable_map: Dict[str, int] = {}
    lots_by_drug: Dict[str, List[Dict[str, Any]]] = {}
    for lt in snapshot.get("lots", []):
        dcode = lt["drug_code"]
        fac_id = lt["facility_id"]
        bno = lt["batch_no"]
        qty = int(lt.get("quantity", 0))

        # Check position lot transferable qty if defined
        trans_qty = qty
        pos = positions.get((fac_id, dcode))
        if pos and "lots" in pos:
            for plt in pos["lots"]:
                if plt.get("batch_no") == bno:
                    trans_qty = int(plt.get("transferable_quantity", qty))
                    break

        lot_transferable_map[bno] = trans_qty
        if dcode not in lots_by_drug:
            lots_by_drug[dcode] = []
        lots_by_drug[dcode].append(lt)

    orders: List[TransferOrder] = []
    order_seq = 1

    # Track allocated units received at destination to maintain sequential usable capacity
    dest_allocated_units: Dict[Tuple[str, str], int] = {}

    for item in shortage_items:
        dst_id = item["facility_id"]
        dcode = item["drug_code"]
        needed = item["shortage"]
        drug = drugs.get(dcode, {})
        dst_fac = facilities.get(dst_id, {})
        pack_size = int(drug.get("pack_size", 1))

        # Destination consumption rate
        dst_rate = forecasts.get((dst_id, dcode), 0.0)
        if dst_rate <= 0.0:
            pos = positions.get((dst_id, dcode))
            if pos:
                dst_rate = float(pos.get("daily_consumption_rate", 0.0))

        candidate_sources: List[Tuple[float, Dict[str, Any]]] = []
        for lt in lots_by_drug.get(dcode, []):
            src_id = lt["facility_id"]
            bno = lt["batch_no"]
            avail = lot_transferable_map.get(bno, 0)
            if src_id == dst_id or avail <= 0:
                continue

            route = routes.get((src_id, dst_id))
            dist = float(route.get("distance_km", 999.0)) if route else 999.0
            candidate_sources.append((dist, lt))

        # Sort candidates by distance ascending (nearest first)
        candidate_sources.sort(key=lambda x: x[0])

        for dist, lt in candidate_sources:
            if needed <= 0:
                break
            bno = lt["batch_no"]
            avail = lot_transferable_map.get(bno, 0)
            if avail <= 0:
                continue

            src_id = lt["facility_id"]
            route = routes.get((src_id, dst_id))
            exp_val = lt.get("expiry")
            exp_date = date.fromisoformat(exp_val) if isinstance(exp_val, str) else exp_val

            # Earlier stock at destination
            earlier_stock = sum(
                int(dlt.get("quantity", 0))
                for dlt in dest_lots_map.get((dst_id, dcode), [])
                if (date.fromisoformat(dlt["expiry"]) if isinstance(dlt["expiry"], str) else dlt["expiry"]) < exp_date
            )

            # Evaluate feasibility F1-F6
            is_feasible, failed_rules, total_usable = evaluate_feasibility(
                source_id=src_id,
                dest_id=dst_id,
                lot_qty=avail,
                transferable_qty=avail,
                lot_expiry=exp_date,
                today=today,
                drug=drug,
                route=route,
                dest_facility=dst_fac,
                vehicles=vehicles,
                destination_daily_rate=dst_rate,
                destination_stock_expiring_before=earlier_stock,
            )

            if not is_feasible or total_usable <= 0:
                continue

            # Subtract destination capacity consumed by earlier orders
            dest_key = (dst_id, dcode)
            prior_allocated = dest_allocated_units.get(dest_key, 0)
            net_dest_usable = max(0, total_usable - prior_allocated)

            if net_dest_usable <= 0:
                continue

            # Safe transfer quantity: min(shortage, lot available, usable capacity)
            transfer_qty = min(needed, avail, net_dest_usable)
            if transfer_qty <= 0:
                continue

            # Round to pack size if appropriate and > pack_size
            if pack_size > 1 and transfer_qty > pack_size:
                transfer_qty = (transfer_qty // pack_size) * pack_size

            if transfer_qty <= 0:
                continue

            # Update availability and destination consumption
            lot_transferable_map[bno] -= transfer_qty
            dest_allocated_units[dest_key] = prior_allocated + transfer_qty
            needed -= transfer_qty

            unit_cost = float(drug.get("unit_cost_inr", 10.0))

            orders.append(
                TransferOrder(
                    order_id=f"DTA/BLR-U/2026/{order_seq:06d}",
                    plan_id="plan-greedy-f4",
                    source_facility_id=src_id,
                    destination_facility_id=dst_id,
                    drug_code=dcode,
                    batch_no=bno,
                    expiry=exp_date,
                    quantity=transfer_qty,
                    unit_cost_inr=unit_cost,
                    total_cost_inr=round(transfer_qty * unit_cost, 2),
                    shortage_reduction=transfer_qty,
                    expiry_avoided=transfer_qty,
                    vehicle_id="CV-01" if drug.get("storage_condition") == "cold_chain" else "AV-01",
                    route_id=route.get("id") if route else None,
                    status="PROPOSED",
                )
            )
            order_seq += 1

    return orders

