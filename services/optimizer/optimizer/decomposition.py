"""Zone-based decomposition solver: per-zone QUBOs + residual boundary QUBO."""

from copy import deepcopy
from datetime import date
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from optimizer.candidates import generate_candidates
from optimizer.metrics import calculate_plan_metrics
from optimizer.models import Candidate, TransferOrder
from optimizer.positions import compute_positions_for_snapshot
from optimizer.qubo_builder import build_qubo, term_breakdown
from optimizer.solvers.chain import solve_chain
from optimizer.validator import repair

logger = logging.getLogger(__name__)


def _solve_subproblem(
    candidates_subset: List[Candidate],
    snapshot: Dict[str, Any],
    subproblem_name: str,
    P1: float = 2.0,
    P2: float = 1.5,
    P3: float = 1.0,
    gamma: float = 0.5,
) -> Tuple[List[TransferOrder], float, Dict[str, Any]]:
    """Formulate and solve a subproblem QUBO on a subset of candidates."""
    t0 = time.perf_counter()
    if not candidates_subset:
        return [], 0.0, {"tier": "empty", "energy": 0.0, "time_ms": 0.0}

    q_mat, offset, meta = build_qubo(
        candidates=candidates_subset,
        snapshot=snapshot,
        P1=P1,
        P2=P2,
        P3=P3,
        gamma=gamma,
    )

    solve_res = solve_chain(
        Q=q_mat,
        offset=offset,
        top_k=5,
        preferred_tier="qpiai_opt_platform",
        evidence_dir="evidence/qpiai_runs",
        variable_names=meta.variable_names,
    )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    best_s = solve_res.best_sample

    if not best_s:
        return [], elapsed_ms, {"tier": solve_res.tier, "error": solve_res.error, "time_ms": elapsed_ms}

    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }

    selected_cands = [candidates_subset[i] for i, b in enumerate(best_s.bitstring) if b == 1]
    orders: List[TransferOrder] = []

    for idx, cand in enumerate(selected_cands):
        drug = drugs_map.get(cand.drug_code, {})
        uc = float(drug.get("unit_cost_inr", 10.0))
        is_cold = drug.get("storage_condition") == "cold_chain"
        r_info = routes_map.get((cand.source_facility_id, cand.destination_facility_id))

        orders.append(
            TransferOrder(
                order_id=f"DTA/BLR-U/2026/{subproblem_name[:3].upper()}-{idx+1:04d}",
                plan_id=f"decomp-{subproblem_name}",
                source_facility_id=cand.source_facility_id,
                destination_facility_id=cand.destination_facility_id,
                drug_code=cand.drug_code,
                batch_no=cand.batch_no,
                expiry=cand.expiry,
                quantity=cand.quantity,
                usable_quantity=cand.usable_quantity,
                unit_cost_inr=uc,
                total_cost_inr=round(cand.quantity * uc, 2),
                shortage_reduction=min(cand.usable_quantity, cand.quantity),
                expiry_avoided=min(cand.usable_quantity, cand.quantity),
                vehicle_id="CV-01" if is_cold else "AV-01",
                route_id=r_info.get("id") if r_info else None,
                status="PROPOSED",
                candidate_id=cand.candidate_id,
            )
        )

    telemetry = {
        "tier": solve_res.tier,
        "energy": best_s.energy,
        "time_ms": elapsed_ms,
        "n_vars": len(meta.variable_names),
        "selected_count": len(selected_cands),
    }
    return orders, elapsed_ms, telemetry


def decompose_and_solve_plan(
    snapshot: Dict[str, Any],
    partition: Dict[str, int],
    solver_choice: str = "qubo",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Decompose large district problem into per-zone QUBOs + boundary residual QUBO."""
    start_time = time.perf_counter()
    ovr = overrides or {}
    p1 = float(ovr.get("P1", 2.0))
    p2 = float(ovr.get("P2", 1.5))
    p3 = float(ovr.get("P3", 1.0))
    gamma = float(ovr.get("gamma", 0.5))

    # 1. Generate full candidate space
    snap = deepcopy(snapshot)
    if "positions" not in snap or not snap["positions"]:
        snap["positions"] = compute_positions_for_snapshot(snap)
    feasible_cands, infeasible_cands = generate_candidates(snap)

    # 2. Partition candidates into Zone 0, Zone 1, and Cross-Zone Boundary
    zone0_cands: List[Candidate] = []
    zone1_cands: List[Candidate] = []
    boundary_cands: List[Candidate] = []

    for c in feasible_cands:
        z_src = partition.get(c.source_facility_id, 0)
        z_dst = partition.get(c.destination_facility_id, 0)
        if z_src == 0 and z_dst == 0:
            zone0_cands.append(c)
        elif z_src == 1 and z_dst == 1:
            zone1_cands.append(c)
        else:
            boundary_cands.append(c)

    # 3. Solve Zone 0 QUBO
    orders_z0, time_z0, meta_z0 = _solve_subproblem(
        zone0_cands, snap, "zone_0", P1=p1, P2=p2, P3=p3, gamma=gamma
    )

    # 4. Solve Zone 1 QUBO
    orders_z1, time_z1, meta_z1 = _solve_subproblem(
        zone1_cands, snap, "zone_1", P1=p1, P2=p2, P3=p3, gamma=gamma
    )

    # 5. Compute residual shortages and remaining lot availability
    allocated_dst_shortage: Dict[Tuple[str, str], int] = {}
    allocated_lot_qty: Dict[Tuple[str, str, str], int] = {}

    for o in orders_z0 + orders_z1:
        dst_k = (o.destination_facility_id, o.drug_code)
        allocated_dst_shortage[dst_k] = allocated_dst_shortage.get(dst_k, 0) + o.quantity
        lot_k = (o.source_facility_id, o.drug_code, o.batch_no)
        allocated_lot_qty[lot_k] = allocated_lot_qty.get(lot_k, 0) + o.quantity

    # 6. Formulate boundary subproblem with residual capacity
    snap_boundary = deepcopy(snap)
    for pos in snap_boundary.get("positions", []):
        dst_k = (pos["facility_id"], pos["drug_code"])
        curr_shortage = int(pos.get("shortage", 0))
        already_filled = allocated_dst_shortage.get(dst_k, 0)
        pos["shortage"] = max(0, curr_shortage - already_filled)

    # Filter boundary candidates that still have residual shortage at destination
    active_boundary_cands: List[Candidate] = []
    for bc in boundary_cands:
        dst_k = (bc.destination_facility_id, bc.drug_code)
        lot_k = (bc.source_facility_id, bc.drug_code, bc.batch_no)
        # Check if destination still has shortage
        res_shortage = snap_boundary.get("positions_map", {})
        pos_match = next(
            (p for p in snap_boundary.get("positions", []) if p["facility_id"] == bc.destination_facility_id and p["drug_code"] == bc.drug_code),
            None,
        )
        if pos_match and pos_match.get("shortage", 0) > 0:
            active_boundary_cands.append(bc)

    # Solve Boundary QUBO
    orders_boundary, time_b, meta_b = _solve_subproblem(
        active_boundary_cands, snap_boundary, "boundary", P1=p1, P2=p2, P3=p3, gamma=gamma
    )

    # 7. Merge all subproblem orders
    raw_orders = orders_z0 + orders_z1 + orders_boundary

    # Assign sequential DTA numbering
    for idx, o in enumerate(raw_orders):
        o.order_id = f"DTA/BLR-U/2026/{idx+1:06d}"

    # 8. Post-decomposition validator repair
    repaired_orders, violations, _ = repair(raw_orders, snap, candidates=feasible_cands)
    metrics = calculate_plan_metrics(repaired_orders, snap)

    total_solve_sec = round(time.perf_counter() - start_time, 4)

    return {
        "status": "COMPLETED",
        "orders": repaired_orders,
        "metrics": metrics,
        "solve_time_sec": total_solve_sec,
        "decomposition_meta": {
            "is_decomposed": True,
            "zone_0_solve_time_ms": time_z0,
            "zone_1_solve_time_ms": time_z1,
            "boundary_solve_time_ms": time_b,
            "zone_0_orders_count": len(orders_z0),
            "zone_1_orders_count": len(orders_z1),
            "boundary_orders_count": len(orders_boundary),
            "zone_0_telemetry": meta_z0,
            "zone_1_telemetry": meta_z1,
            "boundary_telemetry": meta_b,
        },
        "violations_count": len(violations),
    }
