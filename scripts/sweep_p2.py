#!/usr/bin/env python3
"""Parameter sweep script for QUBO P2 shortage penalty parameter.

Sweeps P2 in {0.5, 1.0, 1.5, 2.0, 3.0} across 5 random seeds (42, 43, 44, 45, 46).
Evaluates energy, shortage reduction, expiry avoidance, constraint violations,
and repair frequency to justify the chosen default P2 = 1.5.

Saves structured results to evidence/p2_sweep_results.json and prints markdown summary.
"""

import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
import logging
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Tuple

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SERVICES_DIR = ROOT_DIR / "services" / "optimizer"
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

from optimizer.candidates import generate_candidates
from optimizer.metrics import calculate_plan_metrics
from optimizer.models import Candidate, TransferOrder
from optimizer.positions import compute_positions_for_snapshot
from optimizer.qubo_builder import build_qubo, term_breakdown
from optimizer.solvers.chain import solve_chain
from optimizer.validator import repair, validate_and_simulate_fefo

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("sweep_p2")


def build_synthetic_district_snapshot(seed: int) -> Dict[str, Any]:
    """Generate a realistic district snapshot seeded deterministically."""
    rng = random.Random(seed)
    today = date(2026, 11, 1)

    facilities = [
        {"id": "H1", "name": "SIM-DH Jayanagar", "tier": "DH", "cold_storage_available": True},
        {"id": "H2", "name": "SIM-TGH Anekal", "tier": "TH", "cold_storage_available": True},
        {"id": "H3", "name": "SIM-CHC Yelahanka", "tier": "CHC", "cold_storage_available": True},
        {"id": "H4", "name": "SIM-PHC Hesaraghatta", "tier": "PHC", "cold_storage_available": False},
        {"id": "W0", "name": "SIM-Warehouse Central", "tier": "WH", "cold_storage_available": True},
    ]

    drugs = [
        {"code": "INS-REG", "name": "Insulin Regular", "category": "V", "unit": "vial", "pack_size": 1, "storage_condition": "cold_chain", "min_residual_days": 10, "unit_cost_inr": 145.50},
        {"code": "OXY-10", "name": "Oxytocin Injection", "category": "V", "unit": "ampoule", "pack_size": 5, "storage_condition": "cold_chain", "min_residual_days": 14, "unit_cost_inr": 28.00},
        {"code": "AMOX-500", "name": "Amoxicillin 500mg", "category": "E", "unit": "capsule", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 4.50},
        {"code": "CEFT-1000", "name": "Ceftriaxone 1g", "category": "E", "unit": "vial", "pack_size": 1, "storage_condition": "ambient", "min_residual_days": 21, "unit_cost_inr": 85.00},
        {"code": "PARA-500", "name": "Paracetamol 500mg", "category": "E", "unit": "tablet", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 1.20},
        {"code": "ORS-20", "name": "Oral Rehydration Salts", "category": "N", "unit": "sachet", "pack_size": 1, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 18.00},
    ]

    routes = [
        {"id": "R-W0-H1", "source_facility_id": "W0", "destination_facility_id": "H1", "distance_km": 12.0, "transit_hours": 0.8, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-W0-H2", "source_facility_id": "W0", "destination_facility_id": "H2", "distance_km": 35.0, "transit_hours": 1.8, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-W0-H3", "source_facility_id": "W0", "destination_facility_id": "H3", "distance_km": 22.0, "transit_hours": 1.2, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-W0-H4", "source_facility_id": "W0", "destination_facility_id": "H4", "distance_km": 28.0, "transit_hours": 1.5, "cold_chain_compliant": False, "status": "active"},
        {"id": "R-H1-H2", "source_facility_id": "H1", "destination_facility_id": "H2", "distance_km": 28.0, "transit_hours": 1.5, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-H1-H3", "source_facility_id": "H1", "destination_facility_id": "H3", "distance_km": 20.0, "transit_hours": 1.0, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-H2-H1", "source_facility_id": "H2", "destination_facility_id": "H1", "distance_km": 28.0, "transit_hours": 1.5, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-H3-H4", "source_facility_id": "H3", "destination_facility_id": "H4", "distance_km": 15.0, "transit_hours": 1.0, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-H4-H3", "source_facility_id": "H4", "destination_facility_id": "H3", "distance_km": 15.0, "transit_hours": 1.0, "cold_chain_compliant": True, "status": "active"},
        {"id": "R-H4-H1", "source_facility_id": "H4", "destination_facility_id": "H1", "distance_km": 30.0, "transit_hours": 1.6, "cold_chain_compliant": True, "status": "active"},
    ]

    vehicles = [
        {"id": "CV-01", "name": "Cold Van 1", "cold_chain_capable": True, "is_active": True, "current_temp_c": 4.5},
        {"id": "CV-02", "name": "Cold Van 2", "cold_chain_capable": True, "is_active": True, "current_temp_c": 5.1},
        {"id": "AV-01", "name": "Ambient Van 1", "cold_chain_capable": False, "is_active": True, "current_temp_c": 24.0},
        {"id": "AV-02", "name": "Ambient Van 2", "cold_chain_capable": False, "is_active": True, "current_temp_c": 23.5},
    ]

    # Baseline daily rates with seed jitter
    tier_scale = {"DH": 1.6, "TH": 1.2, "CHC": 0.9, "PHC": 0.4, "WH": 0.0}
    base_rates = {
        "INS-REG": 12.0,
        "OXY-10": 10.0,
        "AMOX-500": 40.0,
        "CEFT-1000": 15.0,
        "PARA-500": 100.0,
        "ORS-20": 35.0,
    }

    forecasts = []
    positions = []
    lots = []

    lot_id_counter = 1
    for f in facilities:
        fac_id = f["id"]
        scale = tier_scale[f["tier"]]

        for d in drugs:
            dcode = d["code"]
            if scale == 0.0:
                rate = 0.0
            else:
                rate = round(base_rates[dcode] * scale * rng.uniform(0.85, 1.15), 1)

            forecasts.append({
                "facility_id": fac_id,
                "drug_code": dcode,
                "effective_daily_rate": rate,
            })

            # Create positions with shortages or surplus
            shortage = 0
            at_risk = 0
            surplus = 0

            # Induce shortages at H2, H3, H4 for select drugs
            if fac_id in ("H2", "H3") and dcode in ("INS-REG", "OXY-10", "CEFT-1000"):
                shortage = int(rate * rng.randint(5, 12))
            elif fac_id == "H4" and dcode in ("AMOX-500", "PARA-500"):
                shortage = int(rate * rng.randint(6, 14))

            # Induce at-risk lots at H1, H4, W0
            if fac_id == "H4" and dcode == "INS-REG":
                # The classic H4 fridge breakdown scenario: at-risk insulin
                qty = rng.randint(40, 60)
                exp = today + timedelta(days=rng.randint(18, 25))
                lots.append({
                    "id": lot_id_counter,
                    "facility_id": fac_id,
                    "drug_code": dcode,
                    "batch_no": f"LOT-{dcode}-{fac_id}-{lot_id_counter:02d}",
                    "expiry": exp.isoformat(),
                    "quantity": qty,
                })
                lot_id_counter += 1
                at_risk += qty
            elif fac_id == "H1" and dcode in ("AMOX-500", "CEFT-1000", "OXY-10"):
                qty = rng.randint(200, 500) if dcode != "OXY-10" else rng.randint(60, 120)
                exp = today + timedelta(days=rng.randint(22, 35))
                lots.append({
                    "id": lot_id_counter,
                    "facility_id": fac_id,
                    "drug_code": dcode,
                    "batch_no": f"LOT-{dcode}-{fac_id}-{lot_id_counter:02d}",
                    "expiry": exp.isoformat(),
                    "quantity": qty,
                })
                lot_id_counter += 1
                at_risk += qty
            elif fac_id == "W0":
                # Warehouse buffer stock (long expiry)
                qty = rng.randint(500, 1500)
                exp = today + timedelta(days=rng.randint(120, 240))
                lots.append({
                    "id": lot_id_counter,
                    "facility_id": fac_id,
                    "drug_code": dcode,
                    "batch_no": f"LOT-{dcode}-{fac_id}-{lot_id_counter:02d}",
                    "expiry": exp.isoformat(),
                    "quantity": qty,
                })
                lot_id_counter += 1

            positions.append({
                "facility_id": fac_id,
                "drug_code": dcode,
                "daily_consumption_rate": rate,
                "shortage": shortage,
                "effective_stock": at_risk + (0 if fac_id != "W0" else 500),
                "at_risk": at_risk,
                "reserve": 0,
            })

    return {
        "today": today.isoformat(),
        "timestamp": "2026-11-01T08:00:00+05:30",
        "facilities": facilities,
        "drugs": drugs,
        "routes": routes,
        "vehicles": vehicles,
        "lots": lots,
        "positions": positions,
        "forecasts": forecasts,
        "snapshot_hash": f"synthetic-{seed}",
    }


def run_single_p2_evaluation(
    snapshot: Dict[str, Any],
    p2: float,
    seed: int,
) -> Dict[str, Any]:
    """Evaluate QUBO with a specific P2 on a snapshot instance."""
    start_time = time.perf_counter()

    # Stage 1: Candidates
    snap = deepcopy(snapshot)
    positions = compute_positions_for_snapshot(snap)
    snap["positions"] = positions
    feasible_cands, infeasible_cands = generate_candidates(snap)

    if not feasible_cands:
        return {
            "seed": seed,
            "P2": p2,
            "feasible_candidates": 0,
            "orders_count": 0,
            "shortage_reduction": 0,
            "expiry_avoided_units": 0,
            "expiry_avoided_inr": 0.0,
            "violations_before_repair": 0,
            "violations_after_repair": 0,
            "energy": 0.0,
            "solve_time_ms": 0.0,
        }

    # Stage 2: QUBO formulation
    p1 = 2.0
    p3 = 1.0
    gamma = 0.5

    Q, offset, meta = build_qubo(
        candidates=feasible_cands,
        snapshot=snap,
        P1=p1,
        P2=p2,
        P3=p3,
        gamma=gamma,
    )

    # Stage 3: Tiered solve chain
    solve_res = solve_chain(
        Q=Q,
        offset=offset,
        top_k=5,
        preferred_tier="qpiai_opt_platform",
        evidence_dir="evidence/qpiai_runs",
        variable_names=meta.variable_names,
    )

    best_sample = solve_res.best_sample
    bitstring = best_sample.bitstring if best_sample else [0] * len(feasible_cands)

    selected_cands = [
        feasible_cands[i]
        for i, b in enumerate(bitstring)
        if b == 1
    ]

    # Stage 4: Construct initial proposed orders
    drugs_map = {d["code"]: d for d in snap.get("drugs", [])}
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snap.get("routes", [])
    }
    initial_orders = []
    for idx, c in enumerate(selected_cands):
        d = drugs_map.get(c.drug_code, {})
        uc = float(d.get("unit_cost_inr", 10.0))
        is_cold = d.get("storage_condition") == "cold_chain"
        r_info = routes_map.get((c.source_facility_id, c.destination_facility_id))
        initial_orders.append(
            TransferOrder(
                order_id=f"DTA/BLR-U/2026/{idx+1:06d}",
                plan_id=f"plan-sweep-p2-{seed}-{p2}",
                source_facility_id=c.source_facility_id,
                destination_facility_id=c.destination_facility_id,
                drug_code=c.drug_code,
                batch_no=c.batch_no,
                expiry=c.expiry,
                quantity=c.quantity,
                usable_quantity=c.usable_quantity,
                unit_cost_inr=uc,
                total_cost_inr=round(c.quantity * uc, 2),
                shortage_reduction=min(c.usable_quantity, c.quantity),
                expiry_avoided=min(c.usable_quantity, c.quantity),
                vehicle_id="CV-01" if is_cold else "AV-01",
                route_id=r_info.get("id") if r_info else None,
                status="PROPOSED",
                candidate_id=c.candidate_id,
            )
        )

    # Stage 5: Invariant check before repair
    raw_val_res = validate_and_simulate_fefo(initial_orders, snap)
    violations_before = len(raw_val_res.violations)

    # Stage 6: Validator repair
    repaired_orders, violations_after, repair_attempts = repair(
        orders=initial_orders,
        snapshot=snap,
        candidates=feasible_cands,
        max_attempts=3,
    )

    # Stage 7: Metrics
    metrics = calculate_plan_metrics(repaired_orders, snap)
    solve_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "seed": seed,
        "P2": p2,
        "solver_tier": solve_res.solver_tier,
        "feasible_candidates": len(feasible_cands),
        "initial_orders_count": len(initial_orders),
        "repaired_orders_count": len(repaired_orders),
        "shortage_reduction": metrics.get("shortage_reduction_total", 0),
        "expiry_avoided_units": metrics.get("expiry_avoided_units", 0),
        "expiry_avoided_inr": metrics.get("expiry_avoided_inr", 0.0),
        "violations_before_repair": violations_before,
        "violations_after_repair": len(violations_after),
        "repair_attempts": repair_attempts,
        "energy": round(best_sample.energy, 4) if best_sample else 0.0,
        "solve_time_ms": solve_duration_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Sweep P2 penalty weight across multiple seeds.")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--p2-values", nargs="+", type=float, default=[0.5, 1.0, 1.5, 2.0, 3.0])
    parser.add_argument("--output", type=str, default="evidence/p2_sweep_results.json")
    args = parser.parse_args()

    results: List[Dict[str, Any]] = []

    print(f"Starting P2 parameter sweep across {len(args.seeds)} seeds and {len(args.p2_values)} P2 values...")
    print(f"Seeds: {args.seeds}")
    print(f"P2 values: {args.p2_values}\n")

    for seed in args.seeds:
        snapshot = build_synthetic_district_snapshot(seed)
        for p2 in args.p2_values:
            eval_res = run_single_p2_evaluation(snapshot, p2, seed)
            results.append(eval_res)
            print(
                f"Seed {seed:2d} | P2={p2:3.1f} | Orders: {eval_res['repaired_orders_count']:2d} | "
                f"Shortage Red: {eval_res['shortage_reduction']:4d} | Expiry Avoided: Rs.{eval_res['expiry_avoided_inr']:8.2f} | "
                f"Pre-Violations: {eval_res['violations_before_repair']:1d} | Post: {eval_res['violations_after_repair']:1d} | "
                f"Tier: {eval_res.get('solver_tier', 'unknown'):15s} | Time: {eval_res['solve_time_ms']:6.1f}ms"
            )

    # Aggregate by P2
    agg: Dict[float, Dict[str, Any]] = {}
    for p2 in args.p2_values:
        sub = [r for r in results if r["P2"] == p2]
        n = len(sub)
        if n == 0:
            continue
        agg[p2] = {
            "avg_orders": round(sum(r["repaired_orders_count"] for r in sub) / n, 2),
            "avg_shortage_reduction": round(sum(r["shortage_reduction"] for r in sub) / n, 1),
            "avg_expiry_avoided_inr": round(sum(r["expiry_avoided_inr"] for r in sub) / n, 2),
            "avg_violations_before": round(sum(r["violations_before_repair"] for r in sub) / n, 2),
            "max_violations_after": max(r["violations_after_repair"] for r in sub),
            "avg_energy": round(sum(r["energy"] for r in sub) / n, 4),
            "avg_time_ms": round(sum(r["solve_time_ms"] for r in sub) / n, 2),
        }

    # Print Markdown Summary Table
    print("\n" + "=" * 80)
    print("SUMMARY RESULTS BY P2 (Averaged over 5 seeds)")
    print("=" * 80)
    print("| P2 | Avg Orders | Shortage Red (units) | Expiry Avoided (INR) | Pre-Repair Violations | Post Violations | Avg Energy | Avg Time (ms) |")
    print("|---|---|---|---|---|---|---|---|")
    for p2, m in agg.items():
        print(
            f"| {p2:3.1f} | {m['avg_orders']:9.2f} | {m['avg_shortage_reduction']:20.1f} | "
            f"Rs.{m['avg_expiry_avoided_inr']:16.2f} | {m['avg_violations_before']:21.2f} | "
            f"{m['max_violations_after']:15d} | {m['avg_energy']:10.4f} | {m['avg_time_ms']:13.2f} |"
        )

    # Save output JSON
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": date.today().isoformat(),
                "seeds": args.seeds,
                "p2_values": args.p2_values,
                "summary": agg,
                "runs": results,
            },
            f,
            indent=2,
        )
    print(f"\nWrote full sweep results to {out_path}")


if __name__ == "__main__":
    main()
