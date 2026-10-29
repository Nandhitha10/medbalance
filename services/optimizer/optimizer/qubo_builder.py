"""QUBO (v3) Matrix Builder for MedBalance-Q Redistribution Optimization.

Constructs upper-triangular dict Q[(i, j)] and scalar offset from candidates
using the closed-form expansion of H (v3):
  H = -sum_i (s_i - c_i) x_i
      + P1 sum_k sum_{d < d'} x_kd x_kd'
      + P2 sum_{d,g, n>0} pi_g (sum_{i in (d,g)} (u_i / n_dg) x_i - 1)^2
      + P3 sum_l sum_{j>=1} (x_(l,j),d - x_(l,j),d * x_(l,j-1),d)
      - gamma sum_{same src,dst,veh, i<i'} x_i x_i'
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# VEN Priority Weights (CLAUDE.md §5: VEN -> pi = 3 / 2 / 1)
VEN_WEIGHTS: Dict[str, float] = {
    "V": 3.0,
    "E": 2.0,
    "N": 1.0,
}


@dataclass
class QuboMetadata:
    """Metadata tracking variable mappings and configuration."""
    num_variables: int
    variable_names: List[str]
    candidate_indices: Dict[int, Dict[str, Any]]
    P1: float
    P2: float
    P3: float
    gamma: float
    normalizer_M: float
    offset: float


def get_ven_weight(category: Optional[str]) -> float:
    """Resolve VEN priority multiplier pi_g."""
    if not category:
        return 1.0
    return VEN_WEIGHTS.get(str(category).upper(), 1.0)


def build_qubo(
    candidates: List[Any],
    snapshot: Dict[str, Any],
    P1: float = 2.0,
    P2: float = 1.5,
    P3: float = 1.0,
    gamma: Optional[float] = None,
    normalize_rewards: bool = True,
) -> Tuple[Dict[Tuple[int, int], float], float, QuboMetadata]:
    """Construct upper-triangular QUBO matrix Q and scalar offset.
    
    Returns:
        Q: dict mapping (i, j) with i <= j to float coefficient.
        offset: scalar constant float.
        meta: QuboMetadata with indexing details.
    """
    n_vars = len(candidates)
    Q: Dict[Tuple[int, int], float] = {}
    offset: float = 0.0

    if n_vars == 0:
        meta = QuboMetadata(
            num_variables=0,
            variable_names=[],
            candidate_indices={},
            P1=P1,
            P2=P2,
            P3=P3,
            gamma=gamma or 0.0,
            normalizer_M=1.0,
            offset=0.0,
        )
        return Q, offset, meta

    # Helper to add to upper-triangular Q
    def add_q(i: int, j: int, val: float) -> None:
        if abs(val) < 1e-12:
            return
        u, v = (i, j) if i <= j else (j, i)
        Q[(u, v)] = Q.get((u, v), 0.0) + val

    # Convert candidates to normalized dict representations
    cand_dicts: List[Dict[str, Any]] = []
    var_names: List[str] = []
    cand_indices: Dict[int, Dict[str, Any]] = {}

    for idx, c in enumerate(candidates):
        cd = c.to_dict() if hasattr(c, "to_dict") else dict(c)
        cand_dicts.append(cd)
        name = cd.get("id") or cd.get("candidate_id") or f"x_{idx}"
        var_names.append(name)
        cand_indices[idx] = cd

    # 1. Rewards and trip costs normalizer
    # Reward s_i = usable * unit_cost, cost c_i = trip cost share
    net_rewards: List[float] = []
    trip_costs: List[float] = []
    for cd in cand_dicts:
        reward = float(cd.get("reward_inr") or cd.get("reward") or 0.0)
        cost = float(cd.get("cost_inr") or cd.get("cost") or 0.0)
        net_rewards.append(reward - cost)
        trip_costs.append(cost)

    max_net = max((abs(r) for r in net_rewards), default=1.0)
    normalizer_M = max_net if (normalize_rewards and max_net > 0.0) else 1.0

    norm_net_rewards = [r / normalizer_M for r in net_rewards]
    norm_trip_costs = [c / normalizer_M for c in trip_costs]

    # Resolve gamma: default 0.3 * min positive normalised trip cost
    if gamma is None:
        pos_costs = [c for c in norm_trip_costs if c > 1e-6]
        if pos_costs:
            gamma = 0.3 * min(pos_costs)
        else:
            gamma = 0.05

    # Term 1: Linear reward minimization: - (s_i - c_i) on diagonal
    for i in range(n_vars):
        add_q(i, i, -norm_net_rewards[i])

    # Term 2: P1 One-place constraint per chunk
    # Identify chunks by chunk_id or (batch_no, chunk_index)
    chunks_map: Dict[str, List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        cid = str(cd.get("chunk_id") or f"{cd.get('batch_no')}_chk_{cd.get('chunk_idx', 0)}")
        if cid not in chunks_map:
            chunks_map[cid] = []
        chunks_map[cid].append(i)

    for cid, indices in chunks_map.items():
        if len(indices) > 1:
            for a_idx in range(len(indices)):
                for b_idx in range(a_idx + 1, len(indices)):
                    u = indices[a_idx]
                    v = indices[b_idx]
                    add_q(u, v, P1)

    # Term 3: P2 Shortage square per (destination d, drug g) with n_dg > 0
    # Group candidates by (destination, drug_code)
    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    positions_map: Dict[Tuple[str, str], int] = {}
    for p in snapshot.get("positions", []):
        positions_map[(p["facility_id"], p["drug_code"])] = int(p.get("shortage", 0))

    dest_drug_cands: Dict[Tuple[str, str], List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        dst = str(cd.get("destination_facility_id", ""))
        dcode = str(cd.get("drug_code", ""))
        key = (dst, dcode)
        if key not in dest_drug_cands:
            dest_drug_cands[key] = []
        dest_drug_cands[key].append(i)

    for (dst, dcode), indices in dest_drug_cands.items():
        n_dg = positions_map.get((dst, dcode), 0)
        # Skip shortage terms when n_dg == 0 (CLAUDE.md requirement)
        if n_dg <= 0:
            continue

        drug_info = drugs_map.get(dcode, {})
        pi_g = get_ven_weight(drug_info.get("category", "N"))

        # Expansion of: P2 * pi_g * (sum_i (u_i / n_dg) x_i - 1)^2
        # = P2 * pi_g * [ sum_i (u_i^2/n^2 - 2u_i/n) x_i + sum_{i<j} 2 u_i u_j / n^2 x_i x_j + 1 ]
        scale = P2 * pi_g
        n_sq = float(n_dg * n_dg)

        # Diagonal & offset
        offset += scale * 1.0

        for idx_i in indices:
            u_i = float(cand_dicts[idx_i].get("usable_quantity") or cand_dicts[idx_i].get("quantity", 0))
            diag_val = scale * ((u_i * u_i) / n_sq - (2.0 * u_i) / float(n_dg))
            add_q(idx_i, idx_i, diag_val)

        # Off-diagonal
        for a in range(len(indices)):
            i_var = indices[a]
            u_i = float(cand_dicts[i_var].get("usable_quantity") or cand_dicts[i_var].get("quantity", 0))
            for b in range(a + 1, len(indices)):
                j_var = indices[b]
                u_j = float(cand_dicts[j_var].get("usable_quantity") or cand_dicts[j_var].get("quantity", 0))
                off_val = scale * (2.0 * u_i * u_j / n_sq)
                add_q(i_var, j_var, off_val)

    # Term 4: P3 Chunk order constraint within lot
    # P3 * sum_l sum_{j>=1} (x_{(l,j),d} - x_{(l,j),d} * x_{(l,j-1),d})
    # Group candidates by (lot_batch_no, destination_facility_id)
    lot_dest_chunks: Dict[Tuple[str, str], Dict[int, int]] = {}
    for i, cd in enumerate(cand_dicts):
        bno = str(cd.get("batch_no") or cd.get("lot_batch_no", ""))
        dst = str(cd.get("destination_facility_id", ""))
        c_idx = int(cd.get("chunk_idx", 0))
        key = (bno, dst)
        if key not in lot_dest_chunks:
            lot_dest_chunks[key] = {}
        lot_dest_chunks[key][c_idx] = i

    for (bno, dst), chunk_dict in lot_dest_chunks.items():
        # Check consecutive pairs (j-1, j) for j >= 1
        for j in sorted(chunk_dict.keys()):
            if j >= 1 and (j - 1) in chunk_dict:
                var_j = chunk_dict[j]
                var_prev = chunk_dict[j - 1]
                # +P3 on x_j
                add_q(var_j, var_j, P3)
                # -P3 on x_j * x_{j-1}
                add_q(var_j, var_prev, -P3)

    # Term 5: Shared trip pairs bonus (-gamma)
    # - gamma * sum_{same src, dst, veh, i < i'} x_i x_i'
    trip_groups: Dict[Tuple[str, str, str], List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        src = str(cd.get("source_facility_id", ""))
        dst = str(cd.get("destination_facility_id", ""))
        veh = str(cd.get("vehicle_id", "DEFAULT_VEHICLE"))
        key = (src, dst, veh)
        if key not in trip_groups:
            trip_groups[key] = []
        trip_groups[key].append(i)

    for key, indices in trip_groups.items():
        if len(indices) > 1:
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    add_q(indices[a], indices[b], -gamma)

    meta = QuboMetadata(
        num_variables=n_vars,
        variable_names=var_names,
        candidate_indices=cand_indices,
        P1=P1,
        P2=P2,
        P3=P3,
        gamma=gamma,
        normalizer_M=normalizer_M,
        offset=round(offset, 8),
    )

    # Clean near-zero entries from Q
    clean_q: Dict[Tuple[int, int], float] = {
        k: round(v, 8) for k, v in Q.items() if abs(v) > 1e-9
    }

    return clean_q, offset, meta


def energy(
    Q: Dict[Tuple[int, int], float],
    offset: float,
    x: Union[Dict[int, int], List[int]],
) -> float:
    """Calculate exact scalar energy H(x) = offset + sum_{i<=j} Q[(i,j)] x_i x_j."""
    total = float(offset)
    for (i, j), coeff in Q.items():
        xi = x[i] if isinstance(x, (list, tuple)) else x.get(i, 0)
        xj = x[j] if isinstance(x, (list, tuple)) else x.get(j, 0)
        if xi and xj:
            total += coeff * float(xi * xj)
    return round(total, 6)


def term_breakdown(
    candidates: List[Any],
    snapshot: Dict[str, Any],
    x: Union[Dict[int, int], List[int]],
    P1: float = 2.0,
    P2: float = 1.5,
    P3: float = 1.0,
    gamma: Optional[float] = None,
    normalize_rewards: bool = True,
) -> Dict[str, Any]:
    """Compute exact per-term breakdown of energy H(x)."""
    Q, offset, meta = build_qubo(
        candidates=candidates,
        snapshot=snapshot,
        P1=P1,
        P2=P2,
        P3=P3,
        gamma=gamma,
        normalize_rewards=normalize_rewards,
    )
    n_vars = meta.num_variables
    x_vec = [x[i] if isinstance(x, (list, tuple)) else x.get(i, 0) for i in range(n_vars)]

    cand_dicts = [meta.candidate_indices[i] for i in range(n_vars)]

    # 1. Reward term: - sum (s_i - c_i) / M * x_i
    reward_contrib = 0.0
    per_var_reward: Dict[int, float] = {}
    for i in range(n_vars):
        if x_vec[i]:
            rew = float(cand_dicts[i].get("reward_inr") or cand_dicts[i].get("reward", 0.0))
            cost = float(cand_dicts[i].get("cost_inr") or cand_dicts[i].get("cost", 0.0))
            val = - (rew - cost) / meta.normalizer_M
            reward_contrib += val
            per_var_reward[i] = round(val, 6)
        else:
            per_var_reward[i] = 0.0

    # 2. P1 One-place term: P1 * sum_{k} sum_{d<d'} x_kd x_kd'
    p1_contrib = 0.0
    p1_violations = 0
    chunks_map: Dict[str, List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        cid = str(cd.get("chunk_id") or f"{cd.get('batch_no')}_chk_{cd.get('chunk_idx', 0)}")
        if cid not in chunks_map:
            chunks_map[cid] = []
        chunks_map[cid].append(i)

    for cid, indices in chunks_map.items():
        active = [idx for idx in indices if x_vec[idx]]
        if len(active) > 1:
            pairs = len(active) * (len(active) - 1) // 2
            p1_violations += pairs
            p1_contrib += P1 * pairs

    # 3. P2 Shortage term: P2 * pi_g * (sum (u/n) x - 1)^2
    p2_contrib = 0.0
    drugs_map = {d["code"]: d for d in snapshot.get("drugs", [])}
    positions_map = {
        (p["facility_id"], p["drug_code"]): int(p.get("shortage", 0))
        for p in snapshot.get("positions", [])
    }
    dest_drug_cands: Dict[Tuple[str, str], List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        key = (str(cd.get("destination_facility_id", "")), str(cd.get("drug_code", "")))
        if key not in dest_drug_cands:
            dest_drug_cands[key] = []
        dest_drug_cands[key].append(i)

    for (dst, dcode), indices in dest_drug_cands.items():
        n_dg = positions_map.get((dst, dcode), 0)
        if n_dg <= 0:
            continue
        pi_g = get_ven_weight(drugs_map.get(dcode, {}).get("category", "N"))
        delivered = sum(
            float(cand_dicts[idx].get("usable_quantity") or cand_dicts[idx].get("quantity", 0))
            for idx in indices if x_vec[idx]
        )
        ratio_term = (delivered / float(n_dg)) - 1.0
        p2_contrib += P2 * pi_g * (ratio_term * ratio_term)

    # 4. P3 Chunk order: P3 * (x_j - x_j * x_{j-1})
    p3_contrib = 0.0
    p3_violations = 0
    lot_dest_chunks: Dict[Tuple[str, str], Dict[int, int]] = {}
    for i, cd in enumerate(cand_dicts):
        bno = str(cd.get("batch_no") or cd.get("lot_batch_no", ""))
        dst = str(cd.get("destination_facility_id", ""))
        c_idx = int(cd.get("chunk_idx", 0))
        key = (bno, dst)
        if key not in lot_dest_chunks:
            lot_dest_chunks[key] = {}
        lot_dest_chunks[key][c_idx] = i

    for key, chunk_dict in lot_dest_chunks.items():
        for j in sorted(chunk_dict.keys()):
            if j >= 1 and (j - 1) in chunk_dict:
                xj = x_vec[chunk_dict[j]]
                xprev = x_vec[chunk_dict[j - 1]]
                if xj and not xprev:
                    p3_contrib += P3
                    p3_violations += 1

    # 5. Shared trip bonus: - gamma * sum_{same src, dst, veh} x_i x_j
    gamma_contrib = 0.0
    actual_gamma = meta.gamma
    trip_groups: Dict[Tuple[str, str, str], List[int]] = {}
    for i, cd in enumerate(cand_dicts):
        key = (
            str(cd.get("source_facility_id", "")),
            str(cd.get("destination_facility_id", "")),
            str(cd.get("vehicle_id", "DEFAULT_VEHICLE")),
        )
        if key not in trip_groups:
            trip_groups[key] = []
        trip_groups[key].append(i)

    for key, indices in trip_groups.items():
        active = [idx for idx in indices if x_vec[idx]]
        if len(active) > 1:
            pairs = len(active) * (len(active) - 1) // 2
            gamma_contrib -= actual_gamma * pairs

    total_calc = reward_contrib + p1_contrib + p2_contrib + p3_contrib + gamma_contrib
    mat_energy = energy(Q, offset, x_vec)

    return {
        "reward_term": round(reward_contrib, 6),
        "p1_one_place_penalty": round(p1_contrib, 6),
        "p1_violations": p1_violations,
        "p2_shortage_penalty": round(p2_contrib, 6),
        "p3_chunk_order_penalty": round(p3_contrib, 6),
        "p3_violations": p3_violations,
        "gamma_shared_trip_bonus": round(gamma_contrib, 6),
        "offset": round(offset, 6),
        "total_energy": round(mat_energy, 6),
        "formula_energy": round(total_calc, 6),
        "per_variable_reward": per_var_reward,
    }

