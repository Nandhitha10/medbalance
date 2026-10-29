"""Tiered Solver Chain and Execution Evidence Dispatcher."""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from optimizer.solvers.base import Sample, SolverResult
from optimizer.solvers.greedy_descent import GreedyDescent
from optimizer.solvers.local_opt import QpiAIOptLocal
from optimizer.solvers.neal_sa import NealSA
from optimizer.solvers.platform import QpiAIOptPlatform

logger = logging.getLogger(__name__)

# Evidence directory relative to repository root
DEFAULT_EVIDENCE_DIR = Path("evidence/qpiai_runs")


def write_solver_evidence(
    record: Dict[str, Any],
    evidence_dir: Optional[Path] = None,
) -> Path:
    """Persist solver run record to evidence/qpiai_runs/<ts>_<hash>.json."""
    target_dir = evidence_dir or DEFAULT_EVIDENCE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    content_bytes = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    run_hash = hashlib.sha256(content_bytes).hexdigest()[:8]

    filename = f"{ts_str}_{run_hash}.json"
    filepath = target_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)

    logger.info("Wrote QpiAI run evidence artifact: %s", filepath)
    return filepath


def solve_chain(
    Q: Dict[Tuple[int, int], float],
    offset: float,
    top_k: int = 5,
    evidence_dir: Optional[Any] = None,
    preferred_tier: Optional[str] = None,
    variable_names: Optional[List[str]] = None,
) -> SolverResult:
    """Execute tiered solver chain across platform, local, Neal SA, and Greedy Descent.
    
    Order:
      1. QpiAIOptPlatform (20s timeout)
      2. QpiAIOptLocal (10s timeout)
      3. NealSA (5s timeout)
      4. GreedyDescent (fallback)
    """
    ev_dir = Path(evidence_dir) if evidence_dir else DEFAULT_EVIDENCE_DIR

    n_vars = 0
    for (i, j) in Q.keys():
        n_vars = max(n_vars, i + 1, j + 1)

    tiers = [
        ("qpiai_opt_platform", QpiAIOptPlatform(), 20.0),
        ("qpiai_opt_local", QpiAIOptLocal(), 10.0),
        ("dwave_neal_sa", NealSA(), 5.0),
        ("greedy_descent", GreedyDescent(), 3.0),
    ]

    if preferred_tier:
        tiers.sort(key=lambda t: 0 if t[0] == preferred_tier else 1)

    errors_encountered: List[str] = []
    tier_attempts: List[Dict[str, Any]] = []
    start_time = time.perf_counter()

    for tier_name, solver, timeout_sec in tiers:
        try:
            logger.info("Attempting solver tier: %s (timeout: %.1fs)", tier_name, timeout_sec)
            t0 = time.perf_counter()
            samples = solver.solve(Q, offset, top_k=top_k, timeout=timeout_sec)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            tier_attempts.append({
                "tier": tier_name,
                "time_ms": elapsed_ms,
                "status": "success" if samples else "empty",
                "samples_count": len(samples),
            })

            if samples:
                best_sample = samples[0]
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tier": tier_name,
                    "time_ms": elapsed_ms,
                    "energy": best_sample.energy,
                    "n_vars": n_vars,
                    "variable_names": variable_names,
                    "top_k_count": len(samples),
                    "best_sample": best_sample.x,
                    "top_k_energies": [s.energy for s in samples],
                    "prior_tier_errors": errors_encountered if errors_encountered else None,
                    "tier_attempts": tier_attempts,
                }
                evidence_path = write_solver_evidence(record, evidence_dir=ev_dir)

                return SolverResult(
                    tier=tier_name,
                    samples=samples,
                    time_ms=elapsed_ms,
                    n_vars=n_vars,
                    error=errors_encountered[0] if errors_encountered else None,
                    evidence_file=str(evidence_path),
                    tier_attempts=tier_attempts,
                )

        except Exception as exc:
            err_msg = f"{tier_name} failed: {exc}"
            logger.info(err_msg)
            errors_encountered.append(err_msg)
            tier_attempts.append({
                "tier": tier_name,
                "time_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "status": "error",
                "error": str(exc),
            })

    # If all tiers failed, return all-zeros fallback
    total_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    fallback_sample = Sample(x={i: 0 for i in range(n_vars)}, energy=offset)
    fallback_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": "all_zeros_fallback",
        "time_ms": total_ms,
        "energy": offset,
        "n_vars": n_vars,
        "variable_names": variable_names,
        "error": "; ".join(errors_encountered),
        "tier_attempts": tier_attempts,
    }
    evidence_path = write_solver_evidence(fallback_record, evidence_dir=ev_dir)

    return SolverResult(
        tier="all_zeros_fallback",
        samples=[fallback_sample],
        time_ms=total_ms,
        n_vars=n_vars,
        error="; ".join(errors_encountered),
        evidence_file=str(evidence_path),
        tier_attempts=tier_attempts,
    )
