"""Regret Ledger Engine for MedBalance-Q Redistribution Optimization.

For each transfer order:
1. Evaluates ΔH of moving its chunk to each alternative destination or to nowhere using the best sample.
2. Incorporates alternative allocations from other top-k samples.
3. Maps alternatives to standardized reason codes:
   - LOWER_USABLE: Alternative destination has lower usable capacity / absorptive need
   - HIGHER_COST: Transit route or distance incurs higher transportation expenditure
   - LOWER_VEN: Demand at alternative destination carries lower clinical urgency (V > E > N)
   - FAILED_RULE_Fx: Hard feasibility violation under rules F1 through F6
   - WORSE_FILL: Overfilling destination or exacerbating district shortage imbalance
4. Produces deterministic, numeric explanatory text.
"""

from datetime import date
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from optimizer.feasibility import get_ven_weight
from optimizer.models import Candidate, RegretEntry, TransferOrder
from optimizer.qubo_builder import energy

logger = logging.getLogger(__name__)


def compute_regret_for_orders(
    orders: List[TransferOrder],
    feasible_candidates: List[Candidate],
    infeasible_candidates: List[Candidate],
    snapshot: Dict[str, Any],
    best_bitstring: List[int],
    variable_names: List[str],
    Q: Dict[Tuple[int, int], float],
    offset: float,
    top_k_samples: Optional[List[Any]] = None,
    max_alternatives_per_order: int = 5,
) -> List[RegretEntry]:
    """Compute exact ΔH and deterministic numeric reason explanations for each order.
    
    Returns a flattened list of RegretEntry objects (up to max_alternatives_per_order per order).
    """
    if not orders:
        return []

    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    facilities_map = {f["id"]: f for f in snapshot.get("facilities", [])}
    positions_map = {
        (p["facility_id"], p["drug_code"]): p
        for p in snapshot.get("positions", [])
    }
    routes_map = {
        (r["source_facility_id"], r["destination_facility_id"]): r
        for r in snapshot.get("routes", [])
    }

    # Map candidate_id to index in variable_names
    var_idx_map: Dict[str, int] = {name: i for i, name in enumerate(variable_names)}
    
    # Index feasible candidates by candidate_id and by (batch_no, chunk_id)
    cand_by_id: Dict[str, Candidate] = {c.candidate_id: c for c in feasible_candidates}
    feasible_by_chunk: Dict[str, List[Candidate]] = {}
    for c in feasible_candidates:
        cid = c.chunk_id
        if cid not in feasible_by_chunk:
            feasible_by_chunk[cid] = []
        feasible_by_chunk[cid].append(c)

    # Index infeasible candidates by (chunk_id, destination_facility_id)
    infeasible_by_chunk_dest: Dict[Tuple[str, str], Candidate] = {
        (inf.chunk_id, inf.destination_facility_id): inf
        for inf in infeasible_candidates
    }

    # Base energy of best sample
    best_energy = energy(Q, offset, best_bitstring)

    all_regret_entries: List[RegretEntry] = []

    for order in orders:
        order_regrets: List[RegretEntry] = []
        chosen_dest = order.destination_facility_id
        chosen_cand_id = order.candidate_id or ""
        
        # Determine chunk_id from candidate or batch_no
        chosen_cand = cand_by_id.get(chosen_cand_id)
        chunk_id = chosen_cand.chunk_id if chosen_cand else f"{order.batch_no}_c0"
        chosen_var_idx = var_idx_map.get(chosen_cand_id) if chosen_cand_id else None

        chosen_reward = float(chosen_cand.reward_inr if chosen_cand else order.unit_cost_inr * order.quantity)
        chosen_cost = float(chosen_cand.cost_inr if chosen_cand else order.total_cost_inr)

        # -------------------------------------------------------------
        # Alternative 1: NOWHERE (cancel transfer)
        # -------------------------------------------------------------
        if chosen_var_idx is not None and chosen_var_idx < len(best_bitstring):
            x_nowhere = list(best_bitstring)
            x_nowhere[chosen_var_idx] = 0
            e_nowhere = energy(Q, offset, x_nowhere)
            delta_h_nowhere = round(e_nowhere - best_energy, 4)

            reason_nowhere = (
                f"Canceling transfer leaves {order.usable_quantity} units unserved shortage at {chosen_dest}, "
                f"risking ₹{order.total_cost_inr:,.2f} expiry loss at source (ΔH = +{delta_h_nowhere:.3f})."
            )
            order_regrets.append(
                RegretEntry(
                    order_id=order.order_id,
                    candidate_id=chosen_cand_id,
                    alternate_destination_id="NOWHERE",
                    delta_h=delta_h_nowhere,
                    chosen_reward=chosen_reward,
                    alternate_reward=0.0,
                    regret_delta=delta_h_nowhere,
                    reason_code="WORSE_FILL",
                    reason_text=reason_nowhere,
                    rejected_destination_id="NOWHERE",
                    regret_inr=order.total_cost_inr,
                    reason=reason_nowhere,
                    sample_rank=0,
                )
            )

        # -------------------------------------------------------------
        # Alternative 2: Other facilities in district
        # -------------------------------------------------------------
        for dest_id, dest_fac in facilities_map.items():
            if dest_id == chosen_dest or dest_id == order.source_facility_id:
                continue

            # Check if feasible candidate exists for (chunk_id, dest_id)
            alt_feasible: Optional[Candidate] = None
            for c in feasible_by_chunk.get(chunk_id, []):
                if c.destination_facility_id == dest_id:
                    alt_feasible = c
                    break

            if alt_feasible and alt_feasible.candidate_id in var_idx_map and chosen_var_idx is not None:
                # Feasible alternative: compute exact ΔH by setting chosen=0, alt=1
                alt_idx = var_idx_map[alt_feasible.candidate_id]
                x_alt = list(best_bitstring)
                x_alt[chosen_var_idx] = 0
                x_alt[alt_idx] = 1
                e_alt = energy(Q, offset, x_alt)
                delta_h = round(e_alt - best_energy, 4)

                alt_reward = float(alt_feasible.reward_inr)
                alt_cost = float(alt_feasible.cost_inr)
                u_chosen = order.usable_quantity
                u_alt = alt_feasible.usable_quantity

                # Resolve reason_code and deterministic numeric text
                drug_meta = drugs_map.get(order.drug_code, {})
                ven_cat = drug_meta.get("category", "E")

                dest_pos = positions_map.get((dest_id, order.drug_code), {})
                dest_shortage = int(dest_pos.get("shortage", 0))

                if u_alt < u_chosen:
                    reason_code = "LOWER_USABLE"
                    reason_text = (
                        f"Destination {dest_id} can only absorb {u_alt} of {alt_feasible.quantity} units "
                        f"(vs {u_chosen} units at {chosen_dest}), reducing shortage absorption by "
                        f"{u_chosen - u_alt} units (ΔH = +{delta_h:.3f})."
                    )
                elif alt_cost > chosen_cost:
                    reason_code = "HIGHER_COST"
                    cost_diff = alt_cost - chosen_cost
                    reason_text = (
                        f"Transit cost to {dest_id} is ₹{alt_cost:,.2f} (vs ₹{chosen_cost:,.2f} to {chosen_dest}), "
                        f"adding ₹{cost_diff:,.2f} transport expenditure (ΔH = +{delta_h:.3f})."
                    )
                elif dest_shortage <= 0:
                    reason_code = "WORSE_FILL"
                    reason_text = (
                        f"Destination {dest_id} has 0 residual shortage for {order.drug_code}; "
                        f"transferring causes overfill penalty (ΔH = +{delta_h:.3f})."
                    )
                else:
                    reason_code = "WORSE_FILL"
                    reason_text = (
                        f"Rerouting chunk to {dest_id} delivers suboptimal district shortage balance "
                        f"compared to vital need at {chosen_dest} (ΔH = +{delta_h:.3f})."
                    )

                order_regrets.append(
                    RegretEntry(
                        order_id=order.order_id,
                        candidate_id=alt_feasible.candidate_id,
                        alternate_destination_id=dest_id,
                        delta_h=delta_h,
                        chosen_reward=chosen_reward,
                        alternate_reward=alt_reward,
                        regret_delta=delta_h,
                        reason_code=reason_code,
                        reason_text=reason_text,
                        rejected_destination_id=dest_id,
                        regret_inr=round(max(0.0, chosen_reward - alt_reward), 2),
                        reason=reason_text,
                        sample_rank=0,
                    )
                )

            else:
                # Infeasible alternative: candidate failed F1-F6
                alt_infeasible = infeasible_by_chunk_dest.get((chunk_id, dest_id))
                failed_rules = alt_infeasible.failed_rules if alt_infeasible else []
                primary_rule = "Fx"
                rule_detail = f"Infeasible route or destination constraints at {dest_id}"
                if failed_rules:
                    primary_rule = failed_rules[0].get("rule", "Fx")
                    rule_detail = failed_rules[0].get("detail", rule_detail)
                else:
                    # Deduce rule if not pre-indexed
                    if not dest_fac.get("has_cold_storage", True) and drugs_map.get(order.drug_code, {}).get("cold_chain", False):
                        primary_rule = "F3"
                        rule_detail = f"Destination {dest_id} lacks certified cold storage"
                    else:
                        primary_rule = "F4"
                        rule_detail = f"Destination {dest_id} has zero usable capacity"

                reason_code = f"FAILED_RULE_{primary_rule}"
                reason_text = f"Infeasible under Rule {primary_rule}: {rule_detail} (ΔH = +∞)."

                order_regrets.append(
                    RegretEntry(
                        order_id=order.order_id,
                        candidate_id=alt_infeasible.candidate_id if alt_infeasible else None,
                        alternate_destination_id=dest_id,
                        delta_h=999.0,
                        chosen_reward=chosen_reward,
                        alternate_reward=0.0,
                        regret_delta=999.0,
                        reason_code=reason_code,
                        reason_text=reason_text,
                        rejected_destination_id=dest_id,
                        regret_inr=chosen_reward,
                        reason=reason_text,
                        sample_rank=0,
                    )
                )

        # -------------------------------------------------------------
        # Alternative 3: Best alternative from other top-k samples
        # -------------------------------------------------------------
        if top_k_samples and len(top_k_samples) > 1 and chosen_var_idx is not None:
            for rank_idx, sample in enumerate(top_k_samples[1:], start=2):
                s_bits = sample.bitstring if hasattr(sample, "bitstring") else sample.get("bitstring", [])
                s_energy = float(sample.energy if hasattr(sample, "energy") else sample.get("energy", 0.0))
                
                # Check if this order's variable is 0 in sample, and where the chunk went
                if chosen_var_idx < len(s_bits) and s_bits[chosen_var_idx] == 0:
                    delta_sample = round(s_energy - best_energy, 4)
                    
                    # Find which alternative destination this chunk was routed to in this sample
                    routed_dest = "NOWHERE"
                    for c in feasible_by_chunk.get(chunk_id, []):
                        v_idx = var_idx_map.get(c.candidate_id)
                        if v_idx is not None and v_idx < len(s_bits) and s_bits[v_idx] == 1:
                            routed_dest = c.destination_facility_id
                            break

                    reason_text = (
                        f"Solver top-k sample #{rank_idx} routes chunk to {routed_dest} "
                        f"with higher total system energy (ΔH = +{delta_sample:.3f})."
                    )
                    order_regrets.append(
                        RegretEntry(
                            order_id=order.order_id,
                            candidate_id=chosen_cand_id,
                            alternate_destination_id=routed_dest,
                            delta_h=delta_sample,
                            chosen_reward=chosen_reward,
                            alternate_reward=0.0,
                            regret_delta=delta_sample,
                            reason_code="WORSE_FILL" if routed_dest == "NOWHERE" else "HIGHER_COST",
                            reason_text=reason_text,
                            rejected_destination_id=routed_dest,
                            regret_inr=0.0,
                            reason=reason_text,
                            sample_rank=rank_idx,
                        )
                    )
                    break  # Include best top-k alternative

        # -------------------------------------------------------------
        # Sort by ΔH ascending (best/closest alternatives first) & keep top 5
        # -------------------------------------------------------------
        order_regrets.sort(key=lambda r: (r.delta_h, r.reason_code))
        top_regrets = order_regrets[:max_alternatives_per_order]
        all_regret_entries.extend(top_regrets)

    return all_regret_entries

