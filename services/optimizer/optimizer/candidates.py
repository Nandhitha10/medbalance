"""Candidate generation, chunk splitting, and sequential usable capacity calculation."""

from datetime import date
import math
from typing import Any, Dict, List, Optional, Tuple

from optimizer.feasibility import check_f4_rule, evaluate_feasibility
from optimizer.models import Candidate, Chunk


def split_lot_into_chunks(total_qty: int, pack_size: int = 1, lot_meta: Optional[Dict[str, Any]] = None) -> List[Chunk]:
    """Split transferable quantity into <= 3 chunks (50/25/25 pack-rounded, drop 0)."""
    if total_qty <= 0:
        return []

    pack_size = max(1, pack_size)
    lot_id = lot_meta.get("id") if lot_meta else None
    batch_no = str(lot_meta.get("batch_no", "LOT")) if lot_meta else "LOT"
    facility_id = str(lot_meta.get("facility_id", "")) if lot_meta else ""
    drug_code = str(lot_meta.get("drug_code", "")) if lot_meta else ""
    expiry_val = lot_meta.get("expiry") if lot_meta else date.today()
    if isinstance(expiry_val, str):
        expiry_val = date.fromisoformat(expiry_val)

    # If small quantity <= pack_size, single chunk
    if total_qty <= pack_size:
        return [
            Chunk(
                chunk_id=f"{batch_no}_c0",
                lot_id=lot_id,
                batch_no=batch_no,
                source_facility_id=facility_id,
                drug_code=drug_code,
                quantity=total_qty,
                expiry=expiry_val,
                chunk_index=0,
            )
        ]

    # Target 50%, 25%, 25%
    q1_raw = total_qty * 0.50
    q1 = max(pack_size, round(q1_raw / pack_size) * pack_size)
    q1 = min(q1, total_qty)

    rem1 = total_qty - q1
    raw_chunks: List[int] = []

    if rem1 <= 0:
        raw_chunks = [q1]
    elif rem1 <= pack_size:
        raw_chunks = [q1, rem1]
    else:
        q2_raw = total_qty * 0.25
        q2 = max(pack_size, round(q2_raw / pack_size) * pack_size)
        q2 = min(q2, rem1)
        rem2 = rem1 - q2
        if rem2 <= 0:
            raw_chunks = [q1, q2]
        else:
            raw_chunks = [q1, q2, rem2]

    # Convert to Chunk objects, dropping any zero-quantity chunk
    result: List[Chunk] = []
    for idx, qty in enumerate(raw_chunks):
        if qty > 0:
            result.append(
                Chunk(
                    chunk_id=f"{batch_no}_c{idx}",
                    lot_id=lot_id,
                    batch_no=batch_no,
                    source_facility_id=facility_id,
                    drug_code=drug_code,
                    quantity=qty,
                    expiry=expiry_val,
                    chunk_index=idx,
                )
            )

    return result


def calculate_sequential_chunk_usable(chunk_qty: int, dest_capacity: int, allocated_so_far: int) -> int:
    """Compute chunk j's usable = min(q_j, U_ld - sum earlier chunks qty)."""
    remaining_capacity = max(0, dest_capacity - allocated_so_far)
    return min(chunk_qty, remaining_capacity)


def generate_candidates(
    snapshot: Dict[str, Any],
    top_k_per_chunk: int = 3,
) -> Tuple[List[Candidate], List[Candidate]]:
    """Generate and evaluate transfer candidates for all lots across all destinations.
    
    Returns (top_k_feasible_candidates, all_infeasible_and_regret_candidates).
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

    # Index forecasts by (facility_id, drug_code)
    forecasts = {
        (fc["facility_id"], fc["drug_code"]): float(fc.get("effective_daily_rate", 0.0))
        for fc in snapshot.get("forecasts", [])
    }

    # Index destination lots by (facility_id, drug_code) sorted by expiry
    dest_lots_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for lt in snapshot.get("lots", []):
        key = (lt["facility_id"], lt["drug_code"])
        if key not in dest_lots_map:
            dest_lots_map[key] = []
        dest_lots_map[key].append(lt)

    # Sort each list by expiry
    for k in dest_lots_map:
        dest_lots_map[k].sort(
            key=lambda x: date.fromisoformat(x["expiry"]) if isinstance(x["expiry"], str) else x["expiry"]
        )

    # Index positions by (facility_id, drug_code)
    positions = {
        (p["facility_id"], p["drug_code"]): p
        for p in snapshot.get("positions", [])
    }

    # Identify transferable lots
    # Check positions lot details or lot quantity
    transferable_lots: List[Tuple[Dict[str, Any], int]] = []
    lots_in_snapshot = snapshot.get("lots", [])

    for lt in lots_in_snapshot:
        fac_id = lt["facility_id"]
        dcode = lt["drug_code"]
        bno = lt["batch_no"]
        qty = int(lt.get("quantity", 0))
        if qty <= 0:
            continue

        # Look up position lot breakdown if available
        transferable_qty = qty
        pos = positions.get((fac_id, dcode))
        if pos and "lots" in pos:
            for plt in pos["lots"]:
                if plt.get("batch_no") == bno:
                    transferable_qty = int(plt.get("transferable_quantity", qty))
                    break

        if transferable_qty > 0:
            transferable_lots.append((lt, transferable_qty))

    top_feasible_candidates: List[Candidate] = []
    infeasible_or_regret_candidates: List[Candidate] = []

    # Track sequential usable allocation per (lot_batch, destination_facility)
    dest_lot_allocation_map: Dict[Tuple[str, str], int] = {}

    for lot, trans_qty in transferable_lots:
        dcode = lot["drug_code"]
        src_id = lot["facility_id"]
        drug = drugs.get(dcode, {})
        pack_size = int(drug.get("pack_size", 1))
        unit_cost = float(drug.get("unit_cost_inr", 10.0))

        chunks = split_lot_into_chunks(total_qty=trans_qty, pack_size=pack_size, lot_meta=lot)

        for chunk in chunks:
            chunk_candidates: List[Candidate] = []

            for dst_id, dst_fac in facilities.items():
                if dst_id == src_id:
                    continue

                route = routes.get((src_id, dst_id))
                distance_km = float(route.get("distance_km", 25.0)) if route else 25.0
                transit_hours = float(route.get("transit_hours", 2.0)) if route else 2.0

                # Destination forecast rate
                dst_rate = forecasts.get((dst_id, dcode), 0.0)
                if dst_rate <= 0.0:
                    pos = positions.get((dst_id, dcode))
                    if pos:
                        dst_rate = float(pos.get("daily_consumption_rate", 0.0))

                # Sum of destination lots expiring strictly before this lot
                earlier_stock = 0
                for dlt in dest_lots_map.get((dst_id, dcode), []):
                    dlt_exp = date.fromisoformat(dlt["expiry"]) if isinstance(dlt["expiry"], str) else dlt["expiry"]
                    if dlt_exp < chunk.expiry:
                        earlier_stock += int(dlt.get("quantity", 0))

                # Evaluate feasibility F1-F6
                is_feasible, failed_rules, total_dest_usable = evaluate_feasibility(
                    source_id=src_id,
                    dest_id=dst_id,
                    lot_qty=chunk.quantity,
                    transferable_qty=trans_qty,
                    lot_expiry=chunk.expiry,
                    today=today,
                    drug=drug,
                    route=route,
                    dest_facility=dst_fac,
                    vehicles=vehicles,
                    destination_daily_rate=dst_rate,
                    destination_stock_expiring_before=earlier_stock,
                )

                # Sequential usable calculation across earlier chunks for this destination
                alloc_key = (chunk.batch_no, dst_id)
                already_allocated = dest_lot_allocation_map.get(alloc_key, 0)

                # Total consumption capacity at destination for this lot
                transit_days = math.ceil(transit_hours / 24.0)
                effective_days = max(0, (chunk.expiry - today).days - transit_days - 2)
                raw_capacity = math.floor(dst_rate * effective_days)
                dest_lot_net_capacity = max(0, raw_capacity - earlier_stock)

                chunk_usable = calculate_sequential_chunk_usable(
                    chunk_qty=chunk.quantity,
                    dest_capacity=dest_lot_net_capacity,
                    allocated_so_far=already_allocated,
                )

                if chunk_usable <= 0 and is_feasible:
                    is_feasible = False
                    failed_rules.append({
                        "rule": "F4",
                        "detail": f"F4 usable: Chunk usable is 0 (capacity {dest_lot_net_capacity} absorbed by previous chunks: {already_allocated})",
                    })

                # Economics: Reward & Trip Cost Share
                reward_inr = chunk_usable * unit_cost
                # Standard transit cost: 15 INR/km, shared across load (base estimate)
                cost_inr = round(distance_km * 12.0 * min(1.0, max(0.1, chunk.quantity / 500.0)), 2)
                net_benefit = round(reward_inr - cost_inr, 2)

                cand = Candidate(
                    candidate_id=f"cand-{chunk.chunk_id}-{dst_id}",
                    chunk_id=chunk.chunk_id,
                    source_facility_id=src_id,
                    destination_facility_id=dst_id,
                    drug_code=dcode,
                    batch_no=chunk.batch_no,
                    quantity=chunk.quantity,
                    usable_quantity=chunk_usable if is_feasible else 0,
                    expiry=chunk.expiry,
                    route_id=route.get("id") if route else None,
                    distance_km=distance_km,
                    transit_hours=transit_hours,
                    reward_inr=reward_inr,
                    cost_inr=cost_inr,
                    net_benefit_inr=net_benefit,
                    feasible=is_feasible,
                    failed_rules=failed_rules,
                )

                if is_feasible:
                    chunk_candidates.append(cand)
                else:
                    infeasible_or_regret_candidates.append(cand)

            # Sort feasible candidates for this chunk by net benefit descending
            chunk_candidates.sort(key=lambda c: c.net_benefit_inr, reverse=True)

            # Top-3 kept as active candidates
            kept = chunk_candidates[:top_k_per_chunk]
            rejected = chunk_candidates[top_k_per_chunk:]

            for k in kept:
                top_feasible_candidates.append(k)
                # Update allocation tracking for sequential chunk evaluation
                alloc_key = (k.batch_no, k.destination_facility_id)
                dest_lot_allocation_map[alloc_key] = dest_lot_allocation_map.get(alloc_key, 0) + k.usable_quantity

            for r in rejected:
                r.failed_rules.append({
                    "rule": "CAPACITY",
                    "detail": "Ranked below top-3 destinations by net benefit (s - c)",
                })
                infeasible_or_regret_candidates.append(r)

    return top_feasible_candidates, infeasible_or_regret_candidates
