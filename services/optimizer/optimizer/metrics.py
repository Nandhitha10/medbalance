"""Plan metrics evaluation: shortage reduction, expiry avoidance, waste moved, and economics."""

from datetime import date
import math
from typing import Any, Dict, List, Tuple
from optimizer.models import TransferOrder


def calculate_plan_metrics(
    orders: List[TransferOrder],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate comprehensive plan metrics for a set of transfer orders.
    
    Evaluates:
    - shortage_reduction per (dst, drug) and total
    - expiry_avoided_units and expiry_avoided_inr
    - waste_moved_units and waste_moved_inr (units moved that will still expire at destination)
    - trips, total_km, transport_cost_inr, and net_benefit_inr
    """
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str

    drugs = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }
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

    # Sort each list by expiry
    for k in dest_lots_map:
        dest_lots_map[k].sort(
            key=lambda x: date.fromisoformat(x["expiry"]) if isinstance(x["expiry"], str) else x["expiry"]
        )

    shortage_reduction_by_dst_drug: Dict[str, int] = {}
    total_shortage_reduction = 0
    total_expiry_avoided_units = 0
    total_expiry_avoided_inr = 0.0
    total_waste_moved_units = 0
    total_waste_moved_inr = 0.0

    distinct_trips = set()
    total_km = 0.0
    total_transport_cost = 0.0

    # Track cumulative consumption of transferred lots per (destination, drug)
    dest_consumption_tracker: Dict[Tuple[str, str], int] = {}

    for order in orders:
        src = order.source_facility_id
        dst = order.destination_facility_id
        dcode = order.drug_code
        qty = order.quantity

        drug = drugs.get(dcode, {})
        unit_cost = float(drug.get("unit_cost_inr", order.unit_cost_inr))
        route = routes.get((src, dst), {})
        dist_km = float(route.get("distance_km", 25.0))
        transit_hours = float(route.get("transit_hours", 2.0))

        # Trips and distance
        trip_key = (src, dst, order.vehicle_id or "default")
        if trip_key not in distinct_trips:
            distinct_trips.add(trip_key)
            total_km += dist_km
            total_transport_cost += dist_km * 15.0  # standard base vehicle trip cost

        # Destination consumption rate
        dst_rate = forecasts.get((dst, dcode), 0.0)
        if dst_rate <= 0.0:
            pos = positions.get((dst, dcode))
            if pos:
                dst_rate = float(pos.get("daily_consumption_rate", 0.0))

        # Destination stock expiring before this order
        exp_date = order.expiry if isinstance(order.expiry, date) else date.fromisoformat(str(order.expiry))
        earlier_stock = sum(
            int(dlt.get("quantity", 0))
            for dlt in dest_lots_map.get((dst, dcode), [])
            if (date.fromisoformat(dlt["expiry"]) if isinstance(dlt["expiry"], str) else dlt["expiry"]) < exp_date
        )

        transit_days = math.ceil(transit_hours / 24.0)
        effective_days = max(0, (exp_date - today).days - transit_days - 2)
        total_dest_capacity = math.floor(dst_rate * effective_days)
        net_dest_capacity = max(0, total_dest_capacity - earlier_stock)

        # Subtract previously consumed transferred quantity for this destination & drug
        consumed_prior = dest_consumption_tracker.get((dst, dcode), 0)
        available_capacity = max(0, net_dest_capacity - consumed_prior)

        # Usable quantity at destination
        usable_at_dest = min(qty, available_capacity)
        dest_consumption_tracker[(dst, dcode)] = consumed_prior + usable_at_dest

        # Waste moved: units exceeding usable capacity
        waste_moved = max(0, qty - usable_at_dest)
        total_waste_moved_units += waste_moved
        total_waste_moved_inr += waste_moved * unit_cost

        # Expiry avoided: units that are usable at destination and were at-risk at source
        expiry_avoided = usable_at_dest
        total_expiry_avoided_units += expiry_avoided
        total_expiry_avoided_inr += expiry_avoided * unit_cost

        # Shortage reduction
        key_str = f"{dst}:{dcode}"
        pos_dst = positions.get((dst, dcode), {})
        curr_shortage = int(pos_dst.get("shortage", 0))
        reduced_for_dst = min(usable_at_dest, curr_shortage)
        shortage_reduction_by_dst_drug[key_str] = shortage_reduction_by_dst_drug.get(key_str, 0) + reduced_for_dst
        total_shortage_reduction += reduced_for_dst

    net_benefit_inr = round(total_expiry_avoided_inr - total_transport_cost, 2)

    return {
        "shortage_reduction_total": total_shortage_reduction,
        "shortage_reduction_by_dst_drug": shortage_reduction_by_dst_drug,
        "expiry_avoided_units": total_expiry_avoided_units,
        "expiry_avoided_inr": round(total_expiry_avoided_inr, 2),
        "waste_moved_units": total_waste_moved_units,
        "waste_moved_inr": round(total_waste_moved_inr, 2),
        "trips": len(distinct_trips),
        "total_km": round(total_km, 2),
        "transport_cost_inr": round(total_transport_cost, 2),
        "net_benefit_inr": net_benefit_inr,
    }
