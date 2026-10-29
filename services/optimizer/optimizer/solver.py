"""Planning pipeline execution: snapshot, positions, candidates, solver, metrics, and persistence."""

import asyncio
from datetime import date
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
import httpx

from medbal_common.bus import publish
from medbal_common.settings import get_settings
from optimizer.baselines import greedy_f4, greedy_phone_call
from optimizer.candidates import generate_candidates
from optimizer.metrics import calculate_plan_metrics
from optimizer.models import Candidate, RegretEntry, TransferOrder
from optimizer.positions import compute_positions_for_snapshot
from optimizer.snapshot import fetch_snapshot

logger = logging.getLogger(__name__)

# Local in-memory plan store for offline/standalone execution
_plans_store: Dict[str, Dict[str, Any]] = {}


async def _safe_publish(stream: str, data: Dict[str, Any]) -> None:
    """Publish event to Redis Streams with short timeout to prevent blocking when Redis is offline."""
    try:
        await asyncio.wait_for(publish(stream, data), timeout=0.1)
    except Exception as e:
        logger.debug(f"Redis publish skipped or timed out: {e}")


async def run_planning_pipeline(
    mode: str = "live",
    overrides: Optional[Dict[str, Any]] = None,
    solver_choice: str = "greedy_f4",
) -> Dict[str, Any]:
    """Execute complete deterministic planning pipeline."""
    start_time = time.perf_counter()
    settings = get_settings()

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

    # Stage 4: Solve with greedy_f4 (or greedy_phone_call if requested in overrides)
    await _safe_publish("plan.progress", {"stage": "solving", "solver": solver_choice, "progress_pct": 70})
    if solver_choice == "greedy_phone_call":
        orders = greedy_phone_call(snapshot)
    else:
        orders = greedy_f4(snapshot)
    await _safe_publish("plan.progress", {
        "stage": "solving",
        "status": "completed",
        "orders_count": len(orders),
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
            "parameters": {
                "solver": solver_choice,
                "snapshot_hash": snapshot.get("snapshot_hash", ""),
                "overrides": overrides or {},
            },
            "candidates": [c.to_dict() for c in feasible_cands],
            "transfer_orders": [o.to_dict() for o in orders],
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
        "orders": [o.to_dict() for o in orders],
        "candidates": [c.to_dict() for c in feasible_cands],
        "infeasible_candidates": [c.to_dict() for c in infeasible_cands],
        "regret": [r.to_dict() for r in regret_entries],
        "metrics": metrics,
        "solve_time_sec": solve_duration,
        "solver": solver_choice,
    }

    _plans_store[persisted_plan_id] = plan_dict

    await _safe_publish("plan.completed", {
        "plan_id": persisted_plan_id,
        "mode": mode,
        "orders_count": len(orders),
        "expiry_avoided_units": metrics.get("expiry_avoided_units", 0),
        "expiry_avoided_inr": metrics.get("expiry_avoided_inr", 0.0),
    })

    return plan_dict
