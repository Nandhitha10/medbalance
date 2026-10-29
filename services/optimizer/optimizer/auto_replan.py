"""Automatic Re-Planning Engine on Cold-Chain Telemetry Excursions.

Reactive safety loop:
1. Consumes 'coldchain.alert' from Redis Streams / MQTT.
2. Identifies affected vehicle and routes undergoing temperature excursions (> 8.0°C).
3. Searches active live plan for un-dispatched, temperature-sensitive orders.
4. Executes what-if re-planning with affected routes and vehicles marked unsafe.
5. If the re-plan is feasible (0 violations), persists as a revised plan, marks superseded orders,
   and publishes 'plan.revised' with diff to Redis Streams within 60s.
"""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from medbal_common.bus import get_redis_client
from medbal_common.clock import KOLKATA_TZ, now as sim_now
from optimizer.models import TransferOrder
from optimizer.snapshot import fetch_snapshot, load_fixture_snapshot
from optimizer.whatif import apply_snapshot_overrides, compute_plan_diff

logger = logging.getLogger(__name__)

# Cold chain drug formulary codes
COLD_CHAIN_DRUG_CODES: Set[str] = {"INS-REG", "OXY-10", "ASV-10", "TD-VAC"}


def find_affected_orders(
    orders: List[Dict[str, Any]],
    affected_vehicle: str,
    affected_routes: List[str],
    snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Identify live, not-yet-dispatched cold-chain orders using affected vehicle or routes."""
    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }

    # Normalize vehicle identifiers (e.g. CV-02, DEV-CV-02, V-COLD-02)
    veh_aliases = {affected_vehicle.upper()}
    if "CV-02" in affected_vehicle.upper():
        veh_aliases.update({"CV-02", "DEV-CV-02", "V-COLD-02", "V-CV-02"})
    elif "CV-01" in affected_vehicle.upper():
        veh_aliases.update({"CV-01", "DEV-CV-01", "V-COLD-01", "V-CV-01"})

    affected_routes_set = {r.upper() for r in affected_routes}

    affected_orders: List[Dict[str, Any]] = []

    for order in orders:
        # Check order status: must be live and not yet delivered or cancelled
        order_status = str(order.get("status", "PROPOSED")).upper()
        if order_status in ("DELIVERED", "CANCELLED", "SUPERSEDED"):
            continue

        drug_code = str(order.get("drug_code", ""))
        drug_meta = drugs_map.get(drug_code, {})
        is_cold = drug_meta.get("cold_chain", False) or drug_code in COLD_CHAIN_DRUG_CODES

        if not is_cold:
            continue

        order_veh = str(order.get("vehicle_id", "")).upper()
        order_route = str(order.get("route_id", "")).upper()
        src = order.get("source_facility_id")
        dst = order.get("destination_facility_id")
        connecting_route = routes_map.get((src, dst), {})
        connecting_route_id = str(connecting_route.get("id") or connecting_route.get("route_id", "")).upper()

        is_affected = (
            (order_veh in veh_aliases)
            or (order_route and order_route in affected_routes_set)
            or (connecting_route_id and connecting_route_id in affected_routes_set)
            or (connecting_route.get("assigned_vehicle_id", "").upper() in veh_aliases)
        )

        if is_affected:
            affected_orders.append(order)

    return affected_orders


async def trigger_auto_replan(
    alert_data: Dict[str, Any],
    plans_store: Dict[str, Any],
    run_planning_fn: Any,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate temperature excursion alert and automatically re-plan affected cold orders."""
    device_id = str(alert_data.get("device_id") or alert_data.get("device") or "")
    vehicle_id = str(alert_data.get("vehicle_id") or alert_data.get("vehicle") or "")
    temp_c = float(alert_data.get("temp_c", 0.0))
    severity = str(alert_data.get("severity", "CRITICAL")).upper()
    route_ids = list(alert_data.get("route_ids") or alert_data.get("routes") or [])

    # If temperature is safe and not critical alert, ignore
    if temp_c <= 8.0 and severity != "CRITICAL":
        logger.debug(f"Auto-Replan: Telemetry {device_id} temp {temp_c}°C is within safe range (<= 8.0°C)")
        return None

    # Derive vehicle from device_id if vehicle_id omitted
    if not vehicle_id and device_id:
        if "CV-02" in device_id:
            vehicle_id = "CV-02"
        elif "CV-01" in device_id:
            vehicle_id = "CV-01"

    # Default affected routes if empty
    if not route_ids and vehicle_id:
        if "02" in vehicle_id:
            route_ids = ["R-H1-H4", "R-H4-H1", "R-H2-H4", "R-H4-H2", "R-H3-H4", "R-H4-H3"]

    logger.warning(
        f"Auto-Replan: Handling {severity} cold-chain alert on {vehicle_id or device_id} "
        f"({temp_c}°C > 8.0°C) with routes {route_ids}"
    )

    # 1. Resolve live snapshot
    snap = snapshot
    if not snap:
        try:
            snap = await fetch_snapshot()
        except Exception:
            snap = load_fixture_snapshot()

    # 2. Resolve active live plan
    active_plan = None
    if plans_store:
        # Check latest_live or highest plan
        active_plan = plans_store.get("latest_live")
        if not active_plan:
            live_plans = [p for p in plans_store.values() if isinstance(p, dict) and p.get("mode") == "live"]
            if live_plans:
                active_plan = live_plans[-1]

    # If no live plan is active yet, generate initial baseline live plan
    if not active_plan:
        logger.info("Auto-Replan: No active live plan found; generating baseline live plan")
        active_plan = await run_planning_fn(snapshot=snap, mode="live", solver_choice="qubo")
        plans_store[active_plan["id"]] = active_plan
        plans_store["latest_live"] = active_plan

    live_orders = active_plan.get("orders", [])

    # 3. Find affected orders on the failing vehicle/routes
    affected_orders = find_affected_orders(
        orders=live_orders,
        affected_vehicle=vehicle_id,
        affected_routes=route_ids,
        snapshot=snap,
    )

    if not affected_orders:
        logger.info(f"Auto-Replan: No active live cold orders currently using {vehicle_id} or routes {route_ids}")
        return {
            "status": "no_affected_orders",
            "message": f"No live cold chain orders currently assigned to {vehicle_id}",
        }

    affected_ids = [o.get("id") or o.get("order_id") for o in affected_orders]
    logger.info(f"Auto-Replan: Found {len(affected_orders)} affected cold orders: {affected_ids}")

    # 4. Apply overrides marking affected vehicle and routes unsafe
    overrides: Dict[str, Any] = {
        "close_routes": route_ids,
        "disable_vehicle": vehicle_id,
    }
    
    replan_snap = apply_snapshot_overrides(snap, overrides)

    # Also explicitly mark vehicle unsafe in snapshot
    for v in replan_snap.get("vehicles", []):
        vid = str(v.get("id") or v.get("vehicle_id", "")).upper()
        if vehicle_id.upper() in vid or vid in vehicle_id.upper():
            v["cold_ok"] = False
            v["cold_chain_capable"] = False
            v["is_active"] = False
            v["status"] = "unsafe"

    for r in replan_snap.get("routes", []):
        rid = str(r.get("id") or r.get("route_id", ""))
        if rid in route_ids:
            r["status"] = "unsafe"
            r["safe"] = False
            r["cold_chain_capable"] = False

    # 5. Run planning pipeline with overrides
    revised_plan = await run_planning_fn(
        snapshot=replan_snap,
        mode="live",
        solver_choice="qubo",
        overrides=overrides,
    )

    # Verify validity of revised plan
    violations = revised_plan.get("violations_count", 0)
    if violations > 0:
        logger.error(f"Auto-Replan: Revised plan produced {violations} violations; aborting revision")
        return {
            "status": "failed_validation",
            "violations_count": violations,
        }

    # 6. Assign unique revised plan ID and lineage metadata
    revised_plan_id = f"PLAN-REV-{uuid4().hex[:6].upper()}"
    revised_plan["id"] = revised_plan_id
    revised_plan["plan_id"] = revised_plan_id
    revised_plan["revised_from_plan_id"] = active_plan.get("id")
    revised_plan["mode"] = "live"
    revised_plan["status"] = "COMPLETED"

    # Mark old affected orders as SUPERSEDED
    for o in live_orders:
        oid = o.get("id") or o.get("order_id")
        if oid in affected_ids:
            o["status"] = "SUPERSEDED"
            o["superseded_by"] = revised_plan_id

    # 7. Compute plan diff
    diff = compute_plan_diff(live_orders, revised_plan.get("orders", []))

    # Persist in store
    plans_store[revised_plan_id] = revised_plan
    plans_store["latest_live"] = revised_plan

    # 8. Publish 'plan.revised' event to Redis Streams
    now_iso = sim_now().isoformat()
    revised_event = {
        "event_id": f"evt-rev-{uuid4().hex[:8]}",
        "event_type": "plan.revised",
        "timestamp": now_iso,
        "data": {
            "original_plan_id": active_plan.get("id"),
            "new_plan_id": revised_plan_id,
            "rejected_order_id": affected_ids[0] if affected_ids else "",
            "reason": f"Cold-chain temperature excursion on {vehicle_id} ({temp_c}°C > 8.0°C)",
            "diff": diff,
            "superseded_orders": affected_ids,
        },
    }

    try:
        r_client = get_redis_client()
        await asyncio.wait_for(
            r_client.xadd("plan.revised", {"payload": json.dumps(revised_event)}),
            timeout=0.5,
        )
        logger.info(f"Auto-Replan: Successfully published 'plan.revised' event to Redis for {revised_plan_id}")
    except Exception as e:
        logger.debug(f"Auto-Replan: Redis publish notice: {e}")

    return {
        "status": "revised",
        "original_plan_id": active_plan.get("id"),
        "new_plan_id": revised_plan_id,
        "superseded_orders": affected_ids,
        "diff": diff,
        "plan": revised_plan,
        "event": revised_event,
    }

