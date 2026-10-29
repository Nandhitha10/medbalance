"""Exact Classical MILP Solver using Google OR-Tools CP-SAT."""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from ortools.sat.python import cp_model

from optimizer.metrics import calculate_plan_metrics
from optimizer.models import Candidate, TransferOrder
from optimizer.qubo_builder import build_qubo, energy
from optimizer.validator import repair

logger = logging.getLogger(__name__)


def solve_milp_exact(
    candidates: List[Any],
    snapshot: Dict[str, Any],
    P1: float = 2.0,
    P2: float = 1.5,
    P3: float = 1.0,
    gamma: Optional[float] = None,
    timeout_sec: float = 20.0,
    enforce_hard_constraints: bool = False,
) -> Dict[str, Any]:
    """Solve the redistribution decision problem to exact global optimality using OR-Tools CP-SAT.
    
    Models:
    - Binary decision variable x_i in {0, 1} per candidate chunk
    - Exact upper-triangular objective minimization matching QUBO formulation
    - Optional hard constraints for one-place chunk rule: sum_{i in chunk} x_i <= 1
    - Auxiliary variables for pairwise interactions: z_{ij} = x_i * x_j
    - Time limit: 20 seconds
    
    Returns:
      {
        "status": "OPTIMAL" | "FEASIBLE" | "TIMEOUT",
        "optimal_energy": float,
        "objective_value": float,
        "selected_indices": List[int],
        "orders": List[TransferOrder],
        "solve_time_sec": float,
        "n_vars": int,
        "metrics": Dict[str, Any]
      }
    """
    start_time = time.perf_counter()
    n_vars = len(candidates)

    if n_vars == 0:
        return {
            "status": "OPTIMAL",
            "optimal_energy": 0.0,
            "objective_value": 0.0,
            "selected_indices": [],
            "orders": [],
            "solve_time_sec": 0.0,
            "n_vars": 0,
            "metrics": {},
        }

    # Build QUBO matrix representation
    Q, offset, meta = build_qubo(
        candidates=candidates,
        snapshot=snapshot,
        P1=P1,
        P2=P2,
        P3=P3,
        gamma=gamma,
    )

    model = cp_model.CpModel()
    SCALE = 1_000_000  # Scale float coefficients to integer space

    # Decision variables for each candidate
    x = [model.new_bool_var(f"x_{i}") for i in range(n_vars)]
    z: Dict[Tuple[int, int], Any] = {}

    # Hard one-place constraint (optional or when enforce_hard_constraints=True)
    if enforce_hard_constraints:
        chunks_map: Dict[str, List[int]] = {}
        for idx, c in enumerate(candidates):
            cid = str(getattr(c, "chunk_id", None) or c.get("chunk_id", f"chk_{idx}"))
            if cid not in chunks_map:
                chunks_map[cid] = []
            chunks_map[cid].append(idx)
        for cid, indices in chunks_map.items():
            if len(indices) > 1:
                model.add(sum(x[i] for i in indices) <= 1)

    # Linear and Quadratic terms in objective
    obj_terms = []
    for (i, j), val in Q.items():
        coeff = int(round(val * SCALE))
        if coeff == 0:
            continue
        if i == j:
            obj_terms.append(coeff * x[i])
        else:
            # Pairwise interaction variable z_{ij} = x_i * x_j
            pair_key = (min(i, j), max(i, j))
            if pair_key not in z:
                zij = model.new_bool_var(f"z_{pair_key[0]}_{pair_key[1]}")
                model.add_multiplication_equality(zij, [x[pair_key[0]], x[pair_key[1]]])
                z[pair_key] = zij
            obj_terms.append(coeff * z[pair_key])

    model.minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(timeout_sec)
    solver.parameters.num_workers = 4

    solve_status = solver.solve(model)
    status_str = solver.status_name(solve_status)
    solve_duration = round(time.perf_counter() - start_time, 4)

    if solve_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected_indices = [i for i in range(n_vars) if solver.value(x[i]) == 1]
        calc_energy = round((solver.objective_value / SCALE) + offset, 6)
    else:
        selected_indices = []
        calc_energy = round(offset, 6)

    # Synthesize orders from selected candidates
    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }

    raw_orders = []
    for ord_idx, i in enumerate(selected_indices):
        cand = candidates[i]
        dcode = cand.drug_code if hasattr(cand, "drug_code") else cand["drug_code"]
        src = cand.source_facility_id if hasattr(cand, "source_facility_id") else cand["source_facility_id"]
        dst = cand.destination_facility_id if hasattr(cand, "destination_facility_id") else cand["destination_facility_id"]
        bno = cand.batch_no if hasattr(cand, "batch_no") else cand.get("batch_no") or cand.get("lot_batch_no", "")
        qty = cand.quantity if hasattr(cand, "quantity") else int(cand.get("quantity") or cand.get("chunk_quantity", 0))
        usable = cand.usable_quantity if hasattr(cand, "usable_quantity") else int(cand.get("usable_quantity", qty))
        exp = cand.expiry if hasattr(cand, "expiry") else cand.get("expiry")

        drug = drugs_map.get(dcode, {})
        uc = float(drug.get("unit_cost_inr", 10.0))
        is_cold = drug.get("storage_condition") == "cold_chain"
        r_info = routes_map.get((src, dst), {})

        raw_orders.append(
            TransferOrder(
                order_id=f"DTA/BLR-U/2026/{ord_idx+1:06d}",
                plan_id="milp-optimal",
                source_facility_id=src,
                destination_facility_id=dst,
                drug_code=dcode,
                batch_no=bno,
                expiry=exp,
                quantity=qty,
                usable_quantity=usable,
                unit_cost_inr=uc,
                total_cost_inr=round(qty * uc, 2),
                shortage_reduction=min(usable, qty),
                expiry_avoided=min(usable, qty),
                vehicle_id="CV-01" if is_cold else "AV-01",
                route_id=r_info.get("id") if r_info else None,
                status="PROPOSED",
                candidate_id=getattr(cand, "candidate_id", None) or cand.get("id"),
            )
        )

    # Validate and repair orders to guarantee invariants
    repaired_orders, violations, _ = repair(raw_orders, snapshot, candidates=candidates)
    metrics = calculate_plan_metrics(repaired_orders, snapshot)

    return {
        "status": status_str,
        "optimal_energy": calc_energy,
        "objective_value": round(float(metrics.get("expiry_avoided_inr", 0.0)), 2),
        "selected_indices": selected_indices,
        "orders": repaired_orders,
        "solve_time_sec": solve_duration,
        "n_vars": n_vars,
        "metrics": metrics,
    }
