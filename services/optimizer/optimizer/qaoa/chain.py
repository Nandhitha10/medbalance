"""Tiered MaxCut Solver Chain and QCloud Run Evidence Dispatcher."""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import networkx as nx

from optimizer.qaoa.base import MaxCutPort, MaxCutResult
from optimizer.qaoa.exact import ExactBruteForceMaxCut
from optimizer.qaoa.networkx_greedy import NetworkXGreedyMaxCut
from optimizer.qaoa.qcloud import QCloudSimulatorMaxCut
from optimizer.qaoa.qsv_local import QSVLocalMaxCut

logger = logging.getLogger(__name__)

DEFAULT_QCLOUD_EVIDENCE_DIR = Path("evidence/qcloud_runs")


def write_qcloud_evidence(
    record: Dict[str, Any],
    evidence_dir: Optional[Path] = None,
) -> Path:
    """Persist QCloud / QAOA run record to evidence/qcloud_runs/<ts>_<hash>.json."""
    target_dir = Path(evidence_dir) if evidence_dir else DEFAULT_QCLOUD_EVIDENCE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    content_bytes = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    run_hash = hashlib.sha256(content_bytes).hexdigest()[:8]

    filename = f"{ts_str}_{run_hash}.json"
    filepath = target_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)

    logger.info("Wrote QCloud run evidence artifact: %s", filepath)
    return filepath


def solve_maxcut_chain(
    graph: nx.Graph,
    p: int = 1,
    shots: int = 512,
    preferred_tier: Optional[str] = None,
    evidence_dir: Optional[Path] = None,
    timeout: float = 20.0,
) -> MaxCutResult:
    """Execute tiered Max-Cut solver chain across QCloud, QSVLocal, Brute-Force, and Greedy."""
    n = len(graph.nodes())
    tiers: List[tuple[str, MaxCutPort, float]] = [
        ("qpiai_qcloud_simulator", QCloudSimulatorMaxCut(), 20.0),
        ("qsv_local", QSVLocalMaxCut(), 10.0),
        ("exact_brute_force", ExactBruteForceMaxCut(), 5.0),
        ("networkx_greedy", NetworkXGreedyMaxCut(), 3.0),
    ]

    if preferred_tier:
        tiers.sort(key=lambda t: 0 if t[0] == preferred_tier else 1)

    # Compute ground truth exact optimum for benchmarking approximation ratio (if n <= 16)
    exact_opt_val: Optional[float] = None
    if n <= 16:
        try:
            exact_res = ExactBruteForceMaxCut().partition_graph(graph, p=1, shots=0)
            exact_opt_val = exact_res.cut_value
        except Exception as e:
            logger.debug("Exact ground truth calculation skipped: %s", e)

    errors_encountered: List[str] = []
    tier_attempts: List[Dict[str, Any]] = []
    start_time = time.perf_counter()

    for tier_name, solver, t_limit in tiers:
        # Skip exact brute force if n > 16
        if tier_name == "exact_brute_force" and n > 16:
            continue

        try:
            logger.info("Attempting MaxCut tier: %s (n=%d)", tier_name, n)
            t0 = time.perf_counter()
            res = solver.partition_graph(graph, p=p, shots=shots, timeout=t_limit)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            tier_attempts.append({
                "tier": tier_name,
                "time_ms": elapsed_ms,
                "status": "success",
                "cut_value": res.cut_value,
            })

            # Calculate exact approximation ratio
            approx_ratio = 1.0
            if exact_opt_val is not None and exact_opt_val > 1e-6:
                approx_ratio = round(res.cut_value / exact_opt_val, 4)

            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tier": tier_name,
                "depth": p,
                "shots": shots,
                "n_nodes": n,
                "n_edges": len(graph.edges()),
                "cut_value": res.cut_value,
                "exact_cut_value": exact_opt_val,
                "approximation_ratio": approx_ratio,
                "time_ms": elapsed_ms,
                "partition": res.partition,
                "prior_tier_errors": errors_encountered if errors_encountered else None,
                "tier_attempts": tier_attempts,
            }
            evidence_path = write_qcloud_evidence(record, evidence_dir=evidence_dir)

            res.exact_cut_value = exact_opt_val
            res.approximation_ratio = approx_ratio
            res.evidence_file = str(evidence_path)
            res.telemetry["tier_attempts"] = tier_attempts
            return res

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

    # Fallback to greedy if all else failed
    fallback_res = NetworkXGreedyMaxCut().partition_graph(graph, p=p, shots=shots)
    total_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    fallback_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": "fallback_networkx_greedy",
        "depth": p,
        "shots": shots,
        "n_nodes": n,
        "cut_value": fallback_res.cut_value,
        "exact_cut_value": exact_opt_val,
        "time_ms": total_ms,
        "partition": fallback_res.partition,
        "error": "; ".join(errors_encountered),
    }
    evidence_path = write_qcloud_evidence(fallback_record, evidence_dir=evidence_dir)
    fallback_res.evidence_file = str(evidence_path)
    fallback_res.error = "; ".join(errors_encountered)
    return fallback_res
