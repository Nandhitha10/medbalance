"""What-If Simulation Sandbox for MedBalance-Q Redistribution Optimization.

Enables District Drug Officers to evaluate operational interventions without altering live state:
1. Deep-copies current snapshot.
2. Applies parametric overrides:
   - add_vehicle {type, route}: Deploys additional transport units (e.g. cold vans).
   - close_route / open_route: Simulates road closures, landslips, or transit clearances.
   - set_reserve_days: Modifies hospital reserve protection policy horizon.
   - delay_days: Advances simulation date, decreasing effective shelf-life at arrival.
   - repair_cold_storage {facility}: Resolves compressor faults and certifies ILR cold storage.
   - set_multiplier {facility, drug, x}: Simulates acute epidemiological demand spikes.
3. Executes complete optimization pipeline in mode='whatif' (never persisted to live DB).
4. Returns granular diff vs live plan (orders added/removed/changed, KPI deltas).
"""

import copy
from datetime import date, timedelta
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from optimizer.metrics import calculate_plan_metrics
from optimizer.snapshot import fetch_snapshot, load_fixture_snapshot

logger = logging.getLogger(__name__)


def apply_snapshot_overrides(
    snapshot: Dict[str, Any],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply operational overrides onto a deep-copied snapshot dictionary."""
    snap = copy.deepcopy(snapshot)

    # 1. repair_cold_storage: repair facility ILR
    repair_target = overrides.get("repair_cold_storage")
    if repair_target:
        fac_id = repair_target if isinstance(repair_target, str) else repair_target.get("facility") or repair_target.get("facility_id")
        for fac in snap.get("facilities", []):
            if fac.get("id") == fac_id or fac.get("facility_id") == fac_id:
                fac["has_cold_storage"] = True
                fac["cold_storage_available"] = True
                fac["cold_storage_status"] = "OK"
                fac["ilr_status"] = "operational"
                fac["ilr_temp_c"] = 4.2
                logger.info(f"What-If: Repaired cold storage at {fac_id}")

    # 2. close_route: mark route(s) unsafe/closed
    close_routes = overrides.get("close_route") or overrides.get("close_routes")
    if close_routes:
        route_list = [close_routes] if isinstance(close_routes, str) else list(close_routes)
        for r in snap.get("routes", []):
            rid = r.get("id") or r.get("route_id")
            if rid in route_list:
                r["status"] = "unsafe"
                r["safe"] = False
                r["status_reason"] = "Simulated closure in what-if scenario"
                logger.info(f"What-If: Closed route {rid}")

    # 3. open_route: reopen route(s)
    open_routes = overrides.get("open_route") or overrides.get("open_routes")
    if open_routes:
        route_list = [open_routes] if isinstance(open_routes, str) else list(open_routes)
        for r in snap.get("routes", []):
            rid = r.get("id") or r.get("route_id")
            if rid in route_list:
                r["status"] = "active"
                r["safe"] = True
                logger.info(f"What-If: Reopened route {rid}")

    # 4. add_vehicle: add ambient or cold-chain vehicle
    add_veh = overrides.get("add_vehicle")
    if add_veh:
        v_type = add_veh.get("type", "cold_van")
        v_route = add_veh.get("route")
        v_id = add_veh.get("vehicle_id") or f"V-{v_type.upper()}-{len(snap.get('vehicles', [])) + 1}"
        is_cold = v_type in ("cold_van", "cold_chain")

        new_vehicle = {
            "id": v_id,
            "vehicle_id": v_id,
            "type": v_type,
            "cold_chain_capable": is_cold,
            "cold_ok": is_cold,
            "is_active": True,
            "current_temp_c": 4.5 if is_cold else 25.0,
            "assigned_route": v_route,
        }
        snap.setdefault("vehicles", []).append(new_vehicle)

        # If vehicle assigned to route, update route to be cold-capable
        if v_route and is_cold:
            for r in snap.get("routes", []):
                rid = r.get("id") or r.get("route_id")
                if rid == v_route:
                    r["cold_chain_capable"] = True
                    r["has_cold_vehicle"] = True
                    r["vehicle_id"] = v_id
        logger.info(f"What-If: Added vehicle {v_id} ({v_type})")

    # 5. set_reserve_days: adjust reserve policy days
    res_days = overrides.get("set_reserve_days")
    if res_days is not None:
        days_val = int(res_days)
        for pol in snap.get("policies", []):
            pol["reserve_days"] = days_val
        for fac in snap.get("facilities", []):
            fac["reserve_days"] = days_val
        logger.info(f"What-If: Set reserve days to {days_val}")

    # 6. delay_days: advance simulation date and degrade lot shelf-life
    delay = overrides.get("delay_days")
    if delay is not None:
        delay_val = int(delay)
        today_val = snap.get("today", "2026-11-01")
        if isinstance(today_val, str):
            curr_d = date.fromisoformat(today_val)
        else:
            curr_d = today_val
        new_d = curr_d + timedelta(days=delay_val)
        snap["today"] = new_d.isoformat()
        logger.info(f"What-If: Advanced date by {delay_val} days -> {snap['today']}")

    # 7. set_multiplier: scale demand/shortage for specific facility x drug
    mult_override = overrides.get("set_multiplier")
    if mult_override:
        fac = mult_override.get("facility") or mult_override.get("facility_id")
        drug = mult_override.get("drug") or mult_override.get("drug_code")
        factor = float(mult_override.get("multiplier", mult_override.get("x", 1.0)))

        for p in snap.get("positions", []):
            if (not fac or p.get("facility_id") == fac) and (not drug or p.get("drug_code") == drug):
                p["rate"] = float(p.get("rate", 1.0)) * factor
                old_shortage = int(p.get("shortage", 0))
                p["shortage"] = max(0, int(old_shortage * factor))
                logger.info(f"What-If: Multiplied {fac} {drug} demand by {factor}x")

    return snap


def compute_plan_diff(
    live_orders: List[Dict[str, Any]],
    whatif_orders: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute difference between baseline live plan and what-if plan orders."""
    # Match key: (source, destination, drug_code, batch_no)
    def _order_key(o: Dict[str, Any]) -> Tuple[str, str, str, str]:
        return (
            str(o.get("source_facility_id", "")),
            str(o.get("destination_facility_id", "")),
            str(o.get("drug_code", "")),
            str(o.get("batch_no", "")),
        )

    live_map: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {
        _order_key(o): o for o in live_orders
    }
    whatif_map: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {
        _order_key(o): o for o in whatif_orders
    }

    orders_added: List[Dict[str, Any]] = []
    orders_removed: List[Dict[str, Any]] = []
    orders_changed: List[Dict[str, Any]] = []

    for k, w_ord in whatif_map.items():
        if k not in live_map:
            orders_added.append(w_ord)
        else:
            l_ord = live_map[k]
            w_qty = int(w_ord.get("usable_quantity") or w_ord.get("quantity", 0))
            l_qty = int(l_ord.get("usable_quantity") or l_ord.get("quantity", 0))
            if w_qty != l_qty:
                orders_changed.append({
                    "order": w_ord,
                    "previous_quantity": l_qty,
                    "new_quantity": w_qty,
                    "quantity_delta": w_qty - l_qty,
                })

    for k, l_ord in live_map.items():
        if k not in whatif_map:
            orders_removed.append(l_ord)

    return {
        "orders_added": orders_added,
        "orders_removed": orders_removed,
        "orders_changed": orders_changed,
        "total_added": len(orders_added),
        "total_removed": len(orders_removed),
        "total_changed": len(orders_changed),
        "net_orders_delta": len(whatif_orders) - len(live_orders),
    }


def compute_kpi_deltas(
    live_metrics: Dict[str, Any],
    whatif_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate numerical deltas between live and what-if performance metrics."""
    def _val(m: Dict[str, Any], key: str) -> float:
        return float(m.get(key, 0.0) or 0.0)

    shortage_live = _val(live_metrics, "shortage_reduction_total")
    shortage_whatif = _val(whatif_metrics, "shortage_reduction_total")

    expiry_live = _val(live_metrics, "expiry_avoided_inr")
    expiry_whatif = _val(whatif_metrics, "expiry_avoided_inr")

    waste_live = _val(live_metrics, "waste_moved_units")
    waste_whatif = _val(whatif_metrics, "waste_moved_units")

    trips_live = _val(live_metrics, "trips")
    trips_whatif = _val(whatif_metrics, "trips")

    cost_live = _val(live_metrics, "transport_cost_inr")
    cost_whatif = _val(whatif_metrics, "transport_cost_inr")

    return {
        "shortage_reduction_delta": int(shortage_whatif - shortage_live),
        "expiry_avoided_inr_delta": round(expiry_whatif - expiry_live, 2),
        "waste_moved_delta": int(waste_whatif - waste_live),
        "trips_delta": int(trips_whatif - trips_live),
        "transport_cost_delta": round(cost_whatif - cost_live, 2),
    }
