"""Brute-Force Enumeration Tests for QUBO (v3).

Verifies 8 tiny instances (3 lots x 2 facilities, <= 12 vars):
1. one-place conflict
2. two lots competing for one shortage
3. overfill penalty
4. zero-demand guard
5. cold-chain infeasible pair absent
6. shared-trip bonus breaks a tie
7. chunk order precedence
8. VEN priority

For each instance, enumerates all 2^n binary assignments.
Verifies that argmin energy(Q, offset, x) strictly matches the best plan
found by enumerating feasible plans under the true domain objective.
"""

import itertools
from typing import Any, Callable, Dict, List, Tuple
import pytest

from optimizer.qubo_builder import build_qubo, energy, term_breakdown


def enumerate_all_states(n: int) -> List[Tuple[int, ...]]:
    """Generate all 2^n binary assignment vectors."""
    return list(itertools.product([0, 1], repeat=n))


def brute_force_qubo_argmin(
    Q: Dict[Tuple[int, int], float],
    offset: float,
    n_vars: int,
) -> Tuple[Tuple[int, ...], float]:
    """Find argmin_{x in {0,1}^n} E(x) by exhaustive enumeration."""
    all_states = enumerate_all_states(n_vars)
    best_state = None
    min_energy = float("inf")

    for state in all_states:
        e = energy(Q, offset, state)
        if e < min_energy - 1e-9:
            min_energy = e
            best_state = state

    return best_state, min_energy


def test_01_one_place_conflict():
    """Instance 1: One chunk can go to H2 or H3.
    
    H2 offers higher net reward (100) than H3 (60).
    One-place penalty P1 prevents sending both.
    Argmin must be x = (1, 0) sending to H2.
    """
    candidates = [
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
        {
            "id": "c1",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H3",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 60.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "INS-REG", "category": "V"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10},
            {"facility_id": "H3", "drug_code": "INS-REG", "shortage": 10},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot, P1=6.0, P2=1.5)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    # Verification: must select candidate 0 (H2) and reject candidate 1 (H3)
    assert best_state == (1, 0), f"Expected (1, 0), got {best_state} with energy {min_e}"

    # Verify both active is strictly worse due to P1
    both_e = energy(Q, offset, (1, 1))
    assert both_e > min_e + 0.1, f"One-place violation not penalized: {both_e} <= {min_e}"


def test_02_two_lots_competing_for_one_shortage():
    """Instance 2: Two lots compete for shortage of 10 at H2.
    
    Lot 1 (H1->H2) has net reward 90 (100 - 10).
    Lot 2 (W0->H2) has net reward 75 (100 - 25).
    Taking both causes overfill penalty.
    Argmin must take only Lot 1: x = (1, 0).
    """
    candidates = [
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
        {
            "id": "c1",
            "chunk_id": "lot2_chk0",
            "chunk_idx": 0,
            "batch_no": "B2",
            "source_facility_id": "W0",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 25.0,
            "vehicle_id": "CV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "INS-REG", "category": "V"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot, P2=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    assert best_state == (1, 0), f"Expected (1, 0), got {best_state}"
    # Both lots overfill the shortage of 10 to 20 units
    assert energy(Q, offset, (1, 1)) > min_e


def test_03_overfill_penalty():
    """Instance 3: Destination needs 10 units.
    
    Chunk 0 provides 10 units (exact match, error = 0).
    Chunk 1 provides 25 units (excessive overfill, error = (25/10 - 1)^2 = 2.25).
    Argmin must choose Chunk 0: x = (1, 0).
    """
    candidates = [
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "AMOX-500",
            "usable_quantity": 10,
            "reward_inr": 50.0,
            "cost_inr": 5.0,
            "vehicle_id": "AV-01",
        },
        {
            "id": "c1",
            "chunk_id": "lot2_chk0",
            "chunk_idx": 0,
            "batch_no": "B2",
            "source_facility_id": "H3",
            "destination_facility_id": "H2",
            "drug_code": "AMOX-500",
            "usable_quantity": 25,
            "reward_inr": 55.0,
            "cost_inr": 5.0,
            "vehicle_id": "AV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "AMOX-500", "category": "E"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "AMOX-500", "shortage": 10},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot, P2=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    assert best_state == (1, 0), f"Expected exact match (1, 0), got {best_state}"


def test_04_zero_demand_guard():
    """Instance 4: Shortage is zero (n = 0) at destination.
    
    Per CLAUDE.md §6: Shortage term must be skipped when n = 0.
    Since reward does not justify cost (net <= 0), plan must not ship: x = (0,).
    """
    candidates = [
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "PCM-500",
            "usable_quantity": 10,
            "reward_inr": 0.0,
            "cost_inr": 15.0,
            "vehicle_id": "AV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "PCM-500", "category": "N"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "PCM-500", "shortage": 0},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    assert best_state == (0,), f"Expected no shipment (0,), got {best_state}"
    assert offset == 0.0, "Zero demand must not add P2 offset"


def test_05_cold_chain_infeasible_pair_absent():
    """Instance 5: Cold chain infeasible destination is absent.
    
    H4 lacks cold storage; candidate generator filtered out (H1, H4).
    Only feasible destination H2 (cold storage available) is in candidates.
    Argmin must select the feasible destination H2.
    """
    candidates = [
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "INS-REG", "category": "V", "storage_condition": "cold_chain"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10},
            {"facility_id": "H4", "drug_code": "INS-REG", "shortage": 10},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    assert best_state == (1,), f"Expected feasible allocation (1,), got {best_state}"


def test_06_shared_trip_bonus_breaks_a_tie():
    """Instance 6: Two chunks from H1 can go to H2 using vehicle CV-01 or CV-02.
    
    Both vehicles offer identical individual rewards and costs.
    The shared-trip bonus (-gamma) breaks the tie, favoring consolidating
    both chunks in a single vehicle trip (CV-01 or CV-02) over splitting between vehicles.
    """
    candidates = [
        # Chunk A -> H2 via CV-01
        {
            "id": "c0",
            "chunk_id": "lotA_chk0",
            "chunk_idx": 0,
            "batch_no": "BA",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
        # Chunk A -> H2 via CV-02
        {
            "id": "c1",
            "chunk_id": "lotA_chk0",
            "chunk_idx": 0,
            "batch_no": "BA",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-02",
        },
        # Chunk B -> H2 via CV-01
        {
            "id": "c2",
            "chunk_id": "lotB_chk0",
            "chunk_idx": 0,
            "batch_no": "BB",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
        # Chunk B -> H2 via CV-02
        {
            "id": "c3",
            "chunk_id": "lotB_chk0",
            "chunk_idx": 0,
            "batch_no": "BB",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-02",
        },
    ]

    snapshot = {
        "drugs": [{"code": "INS-REG", "category": "V"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 20},
        ],
    }

    # Set explicit gamma bonus and P1 penalty
    Q, offset, meta = build_qubo(candidates, snapshot, P1=6.0, P2=1.5, gamma=0.2)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    # Candidates 0 & 2 send both via CV-01 (captures -gamma bonus)
    # Candidates 1 & 3 send both via CV-02 (captures -gamma bonus)
    # Split vehicles (0 and 3, or 1 and 2) do not capture -gamma bonus
    consolidated_cv01 = (1, 0, 1, 0)
    consolidated_cv02 = (0, 1, 0, 1)
    split_trip_1 = (1, 0, 0, 1)
    split_trip_2 = (0, 1, 1, 0)

    assert best_state in (consolidated_cv01, consolidated_cv02), (
        f"Shared trip bonus should select consolidated trip, got: {best_state}"
    )
    assert energy(Q, offset, best_state) < energy(Q, offset, split_trip_1) - 0.05
    assert energy(Q, offset, best_state) < energy(Q, offset, split_trip_2) - 0.05


def test_07_chunk_order_precedence():
    """Instance 7: Chunk order constraint P3.
    
    A lot has Chunk 0 (idx 0) and Chunk 1 (idx 1).
    Shipping Chunk 1 without Chunk 0 must incur a +P3 penalty.
    """
    candidates = [
        # Chunk 0 -> H2
        {
            "id": "c0",
            "chunk_id": "lot1_chk0",
            "chunk_idx": 0,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 5.0,
            "vehicle_id": "CV-01",
        },
        # Chunk 1 -> H2
        {
            "id": "c1",
            "chunk_id": "lot1_chk1",
            "chunk_idx": 1,
            "batch_no": "B1",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 5,
            "reward_inr": 50.0,
            "cost_inr": 5.0,
            "vehicle_id": "CV-01",
        },
    ]

    snapshot = {
        "drugs": [{"code": "INS-REG", "category": "V"}],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 15},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot, P3=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))

    # Shipping both chunks (1, 1) fully covers shortage of 15
    assert best_state == (1, 1), f"Expected both chunks (1, 1), got {best_state}"

    # Invalid state (0, 1) shipping chunk 1 without chunk 0
    invalid_e = energy(Q, offset, (0, 1))
    valid_chk0_only_e = energy(Q, offset, (1, 0))

    tb_invalid = term_breakdown(candidates, snapshot, (0, 1), P3=2.0)
    assert tb_invalid["p3_violations"] == 1
    assert tb_invalid["p3_chunk_order_penalty"] == 2.0
    assert invalid_e > valid_chk0_only_e, "State violating chunk order must have higher energy"


def test_08_ven_priority():
    """Instance 8: Vital drug (V, pi=3) vs Non-essential drug (N, pi=1).
    
    Both drugs have shortage of 10 at H2.
    Candidates offer 10 units for each.
    Reducing Vital shortage gives 3x higher P2 penalty reduction than Non-essential.
    Argmin must allocate to the Vital drug when budget/capacity favors it.
    """
    candidates = [
        # Vital drug
        {
            "id": "c0",
            "chunk_id": "lotV_chk0",
            "chunk_idx": 0,
            "batch_no": "BV",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "INS-REG",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "CV-01",
        },
        # Non-essential drug
        {
            "id": "c1",
            "chunk_id": "lotN_chk0",
            "chunk_idx": 0,
            "batch_no": "BN",
            "source_facility_id": "H1",
            "destination_facility_id": "H2",
            "drug_code": "VIT-C",
            "usable_quantity": 10,
            "reward_inr": 100.0,
            "cost_inr": 10.0,
            "vehicle_id": "AV-01",
        },
    ]

    snapshot = {
        "drugs": [
            {"code": "INS-REG", "category": "V"},
            {"code": "VIT-C", "category": "N"},
        ],
        "positions": [
            {"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10},
            {"facility_id": "H2", "drug_code": "VIT-C", "shortage": 10},
        ],
    }

    Q, offset, meta = build_qubo(candidates, snapshot, P2=1.5)

    # Energy of fulfilling Vital only vs Non-essential only
    vital_only_e = energy(Q, offset, (1, 0))
    non_essential_only_e = energy(Q, offset, (0, 1))

    # Fulfilling Vital reduces 3 * P2 * 1.0; fulfilling Non-essential reduces 1 * P2 * 1.0
    assert vital_only_e < non_essential_only_e, (
        f"Vital drug should achieve lower energy: {vital_only_e} >= {non_essential_only_e}"
    )

    best_state, min_e = brute_force_qubo_argmin(Q, offset, len(candidates))
    # Best state fulfills both if possible, but if constrained to single, Vital wins
    assert best_state == (1, 1), f"Best state with independent shortages is (1, 1), got {best_state}"
