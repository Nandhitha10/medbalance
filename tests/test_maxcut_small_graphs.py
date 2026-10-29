"""Tests for QAOA Max-Cut Graph Partitioning, Exact Solvers, and MILP Baseline."""

import networkx as nx
import pytest

from optimizer.milp import solve_milp_exact
from optimizer.qaoa.exact import ExactBruteForceMaxCut
from optimizer.qaoa.networkx_greedy import NetworkXGreedyMaxCut
from optimizer.qaoa.qsv_local import QSVLocalMaxCut
from optimizer.qaoa.circuit import evaluate_cut_value
from optimizer.qubo_builder import build_qubo
from tests.test_qubo_bruteforce import brute_force_qubo_argmin


def test_exact_maxcut_triangle():
    """Exact Max-Cut on 3-node unweighted triangle (K3).
    
    Any 2-1 partition cuts exactly 2 edges out of 3. Max cut value is 2.0.
    """
    g = nx.Graph()
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("B", "C", weight=1.0)
    g.add_edge("A", "C", weight=1.0)

    exact_solver = ExactBruteForceMaxCut()
    res = exact_solver.partition_graph(g)

    assert res.cut_value == 2.0
    assert res.approximation_ratio == 1.0
    # Exactly one node has a different partition value from the other two
    values = list(res.partition.values())
    assert values.count(0) in (1, 2)
    assert values.count(1) in (1, 2)


def test_exact_maxcut_4cycle():
    """Exact Max-Cut on 4-cycle (C4).
    
    C4 is bipartite. Alternating partition cuts all 4 edges. Max cut value is 4.0.
    """
    g = nx.cycle_graph(4)
    # Assign unit weights
    for u, v in g.edges():
        g[u][v]["weight"] = 1.0

    exact_solver = ExactBruteForceMaxCut()
    res = exact_solver.partition_graph(g)

    assert res.cut_value == 4.0
    assert res.approximation_ratio == 1.0
    # Bipartite check: adjacent nodes have different partitions
    for u, v in g.edges():
        assert res.partition[u] != res.partition[v]


def test_exact_maxcut_path_and_k4():
    """Exact Max-Cut on path graph P4 and complete graph K4."""
    # Path P4: 0-1-2-3 (3 edges)
    p4 = nx.path_graph(4)
    for u, v in p4.edges():
        p4[u][v]["weight"] = 1.0

    exact = ExactBruteForceMaxCut()
    res_p4 = exact.partition_graph(p4)
    assert res_p4.cut_value == 3.0

    # Complete graph K4 (6 edges)
    # Partition 2 vs 2 cuts 2 * 2 = 4 edges
    k4 = nx.complete_graph(4)
    for u, v in k4.edges():
        k4[u][v]["weight"] = 1.0

    res_k4 = exact.partition_graph(k4)
    assert res_k4.cut_value == 4.0


def test_qsv_local_maxcut_triangle():
    """QAOA Max-Cut on triangle graph using QSVLocal StatevectorSimulator."""
    g = nx.Graph()
    g.add_edge("A", "B", weight=1.0)
    g.add_edge("B", "C", weight=1.0)
    g.add_edge("A", "C", weight=1.0)

    qsv = QSVLocalMaxCut()
    res = qsv.partition_graph(g, p=1, shots=256)

    assert res.error is None
    assert res.tier == "qsv_local"
    assert len(res.partition) == 3
    for v in res.partition.values():
        assert v in (0, 1)
    # On triangle, QAOA easily finds the optimal 2.0 cut
    assert res.cut_value == 2.0
    assert res.approximation_ratio == 1.0


def test_qsv_local_maxcut_4cycle():
    """QAOA Max-Cut on 4-cycle graph using QSVLocal StatevectorSimulator."""
    g = nx.cycle_graph(4)
    for u, v in g.edges():
        g[u][v]["weight"] = 1.0

    qsv = QSVLocalMaxCut()
    res = qsv.partition_graph(g, p=1, shots=512)

    assert res.error is None
    assert len(res.partition) == 4
    # Cut value must be >= 3.0 (>= 75% approximation of optimal 4.0)
    assert res.cut_value >= 3.0
    assert res.approximation_ratio >= 0.75


def test_networkx_greedy_baseline():
    """NetworkX greedy Max-Cut baseline."""
    g = nx.cycle_graph(6)
    for u, v in g.edges():
        g[u][v]["weight"] = 1.0

    greedy = NetworkXGreedyMaxCut()
    res = greedy.partition_graph(g)

    assert res.tier == "networkx_greedy"
    assert len(res.partition) == 6
    assert res.cut_value >= 4.0


# ---------------------------------------------------------------------------
# MILP vs Brute-Force Argmin on the 8 tiny instances
# ---------------------------------------------------------------------------

def test_milp_matches_bruteforce_instance_01():
    """Instance 1: One-place conflict between H2 and H3."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
        {"id": "c1", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H3", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 60.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10}, {"facility_id": "H3", "drug_code": "INS-REG", "shortage": 10}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P1=6.0, P2=1.5)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 2)
    milp_res = solve_milp_exact(candidates, snapshot, P1=6.0, P2=1.5)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0]


def test_milp_matches_bruteforce_instance_02():
    """Instance 2: Two lots competing for one shortage."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
        {"id": "c1", "chunk_id": "lot2_chk0", "chunk_idx": 0, "batch_no": "B2", "source_facility_id": "W0", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 25.0, "vehicle_id": "CV-01"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P2=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 2)
    milp_res = solve_milp_exact(candidates, snapshot, P2=2.0)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0]


def test_milp_matches_bruteforce_instance_03():
    """Instance 3: Overfill penalty."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "AMOX-500", "usable_quantity": 10, "reward_inr": 50.0, "cost_inr": 5.0, "vehicle_id": "AV-01"},
        {"id": "c1", "chunk_id": "lot2_chk0", "chunk_idx": 0, "batch_no": "B2", "source_facility_id": "H3", "destination_facility_id": "H2", "drug_code": "AMOX-500", "usable_quantity": 25, "reward_inr": 55.0, "cost_inr": 5.0, "vehicle_id": "AV-01"},
    ]
    snapshot = {"drugs": [{"code": "AMOX-500", "category": "E"}], "positions": [{"facility_id": "H2", "drug_code": "AMOX-500", "shortage": 10}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P2=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 2)
    milp_res = solve_milp_exact(candidates, snapshot, P2=2.0)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0]


def test_milp_matches_bruteforce_instance_04():
    """Instance 4: Zero-demand guard."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "PCM-500", "usable_quantity": 10, "reward_inr": 0.0, "cost_inr": 15.0, "vehicle_id": "AV-01"},
    ]
    snapshot = {"drugs": [{"code": "PCM-500", "category": "N"}], "positions": [{"facility_id": "H2", "drug_code": "PCM-500", "shortage": 0}]}
    Q, offset, _ = build_qubo(candidates, snapshot)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 1)
    milp_res = solve_milp_exact(candidates, snapshot)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == []


def test_milp_matches_bruteforce_instance_05():
    """Instance 5: Cold chain infeasible pair absent."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V", "storage_condition": "cold_chain"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10}, {"facility_id": "H4", "drug_code": "INS-REG", "shortage": 10}]}
    Q, offset, _ = build_qubo(candidates, snapshot)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 1)
    milp_res = solve_milp_exact(candidates, snapshot)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0]


def test_milp_matches_bruteforce_instance_06():
    """Instance 6: Shared trip bonus breaks a tie."""
    candidates = [
        {"id": "c0", "chunk_id": "lotA_chk0", "chunk_idx": 0, "batch_no": "BA", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
        {"id": "c1", "chunk_id": "lotA_chk0", "chunk_idx": 0, "batch_no": "BA", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-02"},
        {"id": "c2", "chunk_id": "lotB_chk0", "chunk_idx": 0, "batch_no": "BB", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
        {"id": "c3", "chunk_id": "lotB_chk0", "chunk_idx": 0, "batch_no": "BB", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-02"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 20}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P1=6.0, P2=1.5, gamma=0.2)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 4)
    milp_res = solve_milp_exact(candidates, snapshot, P1=6.0, P2=1.5, gamma=0.2)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    # Both (0, 2) consolidated on CV-01 and (1, 3) consolidated on CV-02 achieve identical optimal energy
    assert milp_res["selected_indices"] in ([0, 2], [1, 3])


def test_milp_matches_bruteforce_instance_07():
    """Instance 7: Chunk order precedence."""
    candidates = [
        {"id": "c0", "chunk_id": "lot1_chk0", "chunk_idx": 0, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 5.0, "vehicle_id": "CV-01"},
        {"id": "c1", "chunk_id": "lot1_chk1", "chunk_idx": 1, "batch_no": "B1", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 5, "reward_inr": 50.0, "cost_inr": 5.0, "vehicle_id": "CV-01"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 15}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P3=2.0)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 2)
    milp_res = solve_milp_exact(candidates, snapshot, P3=2.0)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0, 1]


def test_milp_matches_bruteforce_instance_08():
    """Instance 8: VEN priority."""
    candidates = [
        {"id": "c0", "chunk_id": "lotV_chk0", "chunk_idx": 0, "batch_no": "BV", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "INS-REG", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "CV-01"},
        {"id": "c1", "chunk_id": "lotN_chk0", "chunk_idx": 0, "batch_no": "BN", "source_facility_id": "H1", "destination_facility_id": "H2", "drug_code": "VIT-C", "usable_quantity": 10, "reward_inr": 100.0, "cost_inr": 10.0, "vehicle_id": "AV-01"},
    ]
    snapshot = {"drugs": [{"code": "INS-REG", "category": "V"}, {"code": "VIT-C", "category": "N"}], "positions": [{"facility_id": "H2", "drug_code": "INS-REG", "shortage": 10}, {"facility_id": "H2", "drug_code": "VIT-C", "shortage": 10}]}
    Q, offset, _ = build_qubo(candidates, snapshot, P2=1.5)
    best_state, min_e = brute_force_qubo_argmin(Q, offset, 2)
    milp_res = solve_milp_exact(candidates, snapshot, P2=1.5)

    assert milp_res["status"] == "OPTIMAL"
    assert milp_res["optimal_energy"] == pytest.approx(min_e, abs=1e-4)
    assert milp_res["selected_indices"] == [0, 1]
