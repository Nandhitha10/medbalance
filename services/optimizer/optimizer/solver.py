"""Planning pipeline execution: snapshot, positions, candidates, QUBO solver, metrics, and persistence."""

import asyncio
from datetime import date
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4
import httpx

from medbal_common.bus import publish
from medbal_common.settings import get_settings
from optimizer.baselines import greedy_f4, greedy_phone_call
from optimizer.candidates import generate_candidates
from optimizer.metrics import calculate_plan_metrics
from optimizer.models import Candidate, RegretEntry, TransferOrder
from optimizer.positions import compute_positions_for_snapshot
from optimizer.qubo_builder import build_qubo, energy, term_breakdown
from optimizer.snapshot import fetch_snapshot
from optimizer.solvers.chain import solve_chain
from optimizer.validator import repair, validate_and_simulate_fefo

logger = logging.getLogger(__name__)

# Local in-memory plan store for offline/standalone execution
_plans_store: Dict[str, Dict[str, Any]] = {}


async def _safe_publish(stream: str, data: Dict[str, Any]) -> None:
    """Publish event to Redis Streams with short timeout to prevent blocking when Redis is offline."""
    try:
        await asyncio.wait_for(publish(stream, data), timeout=0.1)
    except Exception as e:
        logger.debug(f"Redis publish skipped or timed out: {e}")


def _cands_to_orders(
    selected_cands: List[Candidate],
    snapshot: Dict[str, Any],
    breakdown: Optional[Dict[str, Any]] = None,
) -> List[TransferOrder]:
    """Convert selected Candidate objects to TransferOrder vouchers."""
    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }
    orders: List[TransferOrder] = []
    bd = breakdown or {}
    per_var_reward = bd.get("per_variable_reward", {})

    for idx, cand in enumerate(selected_cands):
        drug = drugs_map.get(cand.drug_code, {})
        unit_cost = float(drug.get("unit_cost_inr", 10.0))
        is_cold = drug.get("storage_condition") == "cold_chain"
        var_rew = per_var_reward.get(cand.candidate_id, {})

        route = routes_map.get((cand.source_facility_id, cand.destination_facility_id))
        route_id = cand.route_id or (route.get("id") if route else None)

        tb = {
            "candidate_id": cand.candidate_id,
            "chunk_id": cand.chunk_id,
            "raw_reward_inr": cand.reward_inr,
            "raw_cost_inr": cand.cost_inr,
            "net_benefit_inr": cand.net_benefit_inr,
            "norm_net_reward": var_rew.get("norm_net_reward", 0.0),
            "p2_shortage_penalty": bd.get("p2_shortage_penalty", 0.0),
            "gamma_shared_trip_bonus": bd.get("gamma_shared_trip_bonus", 0.0),
            "total_energy": bd.get("total_energy", 0.0),
        }

        orders.append(
            TransferOrder(
                order_id=f"DTA/BLR-U/2026/{idx+1:06d}",
                plan_id="pending",
                source_facility_id=cand.source_facility_id,
                destination_facility_id=cand.destination_facility_id,
                drug_code=cand.drug_code,
                batch_no=cand.batch_no,
                expiry=cand.expiry,
                quantity=cand.quantity,
                usable_quantity=cand.usable_quantity,
                unit_cost_inr=unit_cost,
                total_cost_inr=round(cand.quantity * unit_cost, 2),
                shortage_reduction=min(cand.usable_quantity, cand.quantity),
                expiry_avoided=min(cand.usable_quantity, cand.quantity),
                vehicle_id="CV-01" if is_cold else "AV-01",
                route_id=route_id,
                status="PROPOSED",
                term_breakdown=tb,
                candidate_id=cand.candidate_id,
            )
        )
    return orders


async def run_planning_pipeline(
    mode: str = "live",
    overrides: Optional[Dict[str, Any]] = None,
    solver_choice: str = "qubo",
) -> Dict[str, Any]:
    """Execute complete deterministic planning pipeline."""
    start_time = time.perf_counter()
    settings = get_settings()
    ovr = overrides or {}

    # Allow solver selection via overrides if not explicitly specified
    if "solver" in ovr and solver_choice == "qubo":
        solver_choice = str(ovr["solver"])

    # Stage 1: Fetch snapshot
    await _safe_publish("plan.progress", {"stage": "snapshot", "status": "started", "progress_pct": 10})
    snapshot = await fetch_snapshot()
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str
    await _safe_publish("plan.progress", {"stage": "snapshot", "status": "completed", "progress_pct": 20})

    # Stage 2: Positions
    await _safe_publish("plan.progress", {"stage": "positions", "status": "started", "progress_pct": 30})
    positions = compute_positions_for_snapshot(snapshot)
    snapshot["positions"] = positions
    await _safe_publish("plan.progress", {"stage": "positions", "status": "completed", "progress_pct": 40})

    # Stage 3: Candidates
    await _safe_publish("plan.progress", {"stage": "candidates", "status": "started", "progress_pct": 50})
    feasible_cands, infeasible_cands = generate_candidates(snapshot)
    await _safe_publish("plan.progress", {
        "stage": "candidates",
        "status": "completed",
        "feasible_count": len(feasible_cands),
        "infeasible_count": len(infeasible_cands),
        "progress_pct": 60,
    })

    # Stage 4: Solve
    await _safe_publish("plan.progress", {"stage": "solving", "solver": solver_choice, "progress_pct": 70})

    solver_tier_name = solver_choice
    solver_meta: Dict[str, Any] = {}
    orders: List[TransferOrder] = []

    if solver_choice == "qubo":
        p1 = float(ovr.get("P1", 2.0))
        p2 = float(ovr.get("P2", 1.5))
        p3 = float(ovr.get("P3", 1.0))
        gamma_param = float(ovr["gamma"]) if "gamma" in ovr else None

        if not feasible_cands:
            orders = []
            solver_tier_name = "none"
            solver_meta = {"solver_tier": "none", "time_ms": 0.0, "samples": []}
        else:
            # Build initial QUBO
            q_mat, offset, meta = build_qubo(
                candidates=feasible_cands,
                snapshot=snapshot,
                P1=p1,
                P2=p2,
                P3=p3,
                gamma=gamma_param,
            )

            # Solve via tiered failover chain
            solve_res = solve_chain(
                Q=q_mat,
                offset=offset,
                top_k=5,
                preferred_tier="qpiai_opt_platform",
                evidence_dir="evidence/qpiai_runs",
                variable_names=meta.variable_names,
            )

            if not solve_res.best_sample:
                logger.warning("Solver chain returned no sample; falling back to greedy_f4")
                orders = greedy_f4(snapshot)
                solver_tier_name = "greedy_f4_fallback"
                solver_meta = {
                    "solver_tier": solver_tier_name,
                    "error": "No sample from QUBO solver",
                    "tier_attempts": solve_res.tier_attempts,
                }
            else:
                solver_tier_name = solve_res.solver_tier
                best_sample = solve_res.best_sample
                selected_cands = [
                    feasible_cands[i]
                    for i, b in enumerate(best_sample.bitstring)
                    if b == 1
                ]

                # Compute formula energy and term breakdown
                breakdown = term_breakdown(
                    candidates=feasible_cands,
                    snapshot=snapshot,
                    x=best_sample.bitstring,
                    P1=p1,
                    P2=p2,
                    P3=p3,
                    gamma=gamma_param,
                )

                # Convert to TransferOrder objects
                initial_orders = _cands_to_orders(selected_cands, snapshot, breakdown)

                # Define re-solve callback for validator repair if one-place violation occurs
                def _re_solve_callback(p1_mult: float) -> List[TransferOrder]:
                    re_p1 = p1 * p1_mult
                    q_re, off_re, meta_re = build_qubo(
                        candidates=feasible_cands,
                        snapshot=snapshot,
                        P1=re_p1,
                        P2=p2,
                        P3=p3,
                        gamma=gamma_param,
                    )
                    res_re = solve_chain(
                        Q=q_re,
                        offset=off_re,
                        top_k=5,
                        preferred_tier="qpiai_opt_platform",
                        evidence_dir="evidence/qpiai_runs",
                        variable_names=meta_re.variable_names,
                    )
                    if not res_re.best_sample:
                        return []
                    re_cands = [
                        feasible_cands[i]
                        for i, b in enumerate(res_re.best_sample.bitstring)
                        if b == 1
                    ]
                    re_bd = term_breakdown(
                        candidates=feasible_cands,
                        snapshot=snapshot,
                        x=res_re.best_sample.bitstring,
                        P1=re_p1,
                        P2=p2,
                        P3=p3,
                        gamma=gamma_param,
                    )
                    return _cands_to_orders(re_cands, snapshot, re_bd)

                # Validate exact FEFO invariants and repair
                repaired_orders, violations, repair_attempts = repair(
                    orders=initial_orders,
                    snapshot=snapshot,
                    candidates=feasible_cands,
                    resolve_callback=_re_solve_callback,
                    max_attempts=3,
                )
                orders = repaired_orders

                solver_meta = {
                    "solver_tier": solver_tier_name,
                    "time_ms": solve_res.time_ms,
                    "energy": best_sample.energy,
                    "n_vars": len(meta.variable_names),
                    "top_k_samples": [
                        {
                            "bitstring": s.bitstring,
                            "energy": s.energy,
                            "feasible": s.feasible,
                            "count": s.count,
                        }
                        for s in solve_res.samples[:5]
                    ],
                    "term_breakdown": breakdown,
                    "penalties": {
                        "P1": p1,
                        "P2": p2,
                        "P3": p3,
                        "gamma": gamma_param if gamma_param is not None else meta.gamma,
                    },
                    "evidence_file": solve_res.evidence_file,
                    "tier_attempts": solve_res.tier_attempts,
                    "repair_attempts": repair_attempts,
                    "violations_count": len(violations),
                }

    elif solver_choice in ("greedy", "greedy_phone_call"):
        orders = greedy_phone_call(snapshot)
        solver_tier_name = "greedy_phone_call"
        solver_meta = {"solver_tier": "greedy_phone_call", "time_ms": 1.0}
    else:
        # Default greedy_f4
        orders = greedy_f4(snapshot)
        solver_tier_name = "greedy_f4"
        solver_meta = {"solver_tier": "greedy_f4", "time_ms": 2.0}

    await _safe_publish("plan.progress", {
        "stage": "solving",
        "status": "completed",
        "orders_count": len(orders),
        "solver_tier": solver_tier_name,
        "progress_pct": 80,
    })

    # Stage 5: Metrics and Regret Ledger
    await _safe_publish("plan.progress", {"stage": "metrics", "status": "started", "progress_pct": 85})
    metrics = calculate_plan_metrics(orders, snapshot)

    # Synthesize regret entries for explainability
    regret_entries: List[RegretEntry] = []
    for inf in infeasible_cands:
        reasons_summary = "; ".join(r.get("detail", "") for r in inf.failed_rules)
        regret_entries.append(
            RegretEntry(
                order_id=f"cand-{inf.chunk_id}",
                rejected_destination_id=inf.destination_facility_id,
                regret_inr=inf.reward_inr,
                reason=reasons_summary or "Infeasible constraint",
            )
        )
    await _safe_publish("plan.progress", {"stage": "metrics", "status": "completed", "progress_pct": 90})

    solve_duration = round(time.perf_counter() - start_time, 4)

    # Stage 6: Persistence via core-api POST /plans
    await _safe_publish("plan.progress", {"stage": "persisting", "progress_pct": 95})
    persisted_plan_id = None

    core_api_url = settings.CORE_API_URL
    if core_api_url:
        endpoints = [f"{core_api_url}/plans", f"{core_api_url}/api/core/plans"]
        payload = {
            "mode": mode,
            "solver_tier": solver_tier_name,
            "execution_time_sec": solve_duration,
            "parameters": {
                "solver": solver_choice,
                "snapshot_hash": snapshot.get("snapshot_hash", ""),
                "overrides": overrides or {},
            },
            "solver_meta": solver_meta,
            "summary": {
                "solver_tier": solver_tier_name,
                "solver_meta": solver_meta,
                "metrics": metrics,
            },
            "candidates": [c.to_dict() for c in feasible_cands],
            "orders": [o.to_dict() for o in orders],
            "transfer_orders": [o.to_dict() for o in orders],
            "regret": [r.to_dict() for r in regret_entries],
            "regret_entries": [r.to_dict() for r in regret_entries],
            "energy": -float(metrics.get("expiry_avoided_inr", 0.0)),
            "solve_time_sec": solve_duration,
        }

        async with httpx.AsyncClient(timeout=0.5) as client:
            for url in endpoints:
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        persisted_plan_id = data.get("plan_id")
                        logger.info(f"Successfully persisted plan to core-api ({persisted_plan_id})")
                        break
                except Exception as e:
                    logger.debug(f"Failed to post plan to {url}: {e}")

    # Fallback plan ID if core-api is unreachable
    if not persisted_plan_id:
        persisted_plan_id = f"PLAN-{today.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"

    # Assign final plan_id to orders
    for o in orders:
        o.plan_id = persisted_plan_id

    # Assemble complete plan response
    plan_dict = {
        "id": persisted_plan_id,
        "plan_id": persisted_plan_id,
        "mode": mode,
        "status": "COMPLETED",
        "created_at": snapshot.get("timestamp"),
        "today": today_str,
        "solver": solver_choice,
        "solver_tier": solver_tier_name,
        "solver_meta": solver_meta,
        "orders": [o.to_dict() for o in orders],
        "candidates": [c.to_dict() for c in feasible_cands],
        "infeasible_candidates": [c.to_dict() for c in infeasible_cands],
        "regret": [r.to_dict() for r in regret_entries],
        "metrics": metrics,
        "solve_time_sec": solve_duration,
    }

    _plans_store[persisted_plan_id] = plan_dict

    await _safe_publish("plan.completed", {
        "plan_id": persisted_plan_id,
        "mode": mode,
        "solver_tier": solver_tier_name,
        "orders_count": len(orders),
        "expiry_avoided_units": metrics.get("expiry_avoided_units", 0),
        "expiry_avoided_inr": metrics.get("expiry_avoided_inr", 0.0),
    })

    return plan_dict
