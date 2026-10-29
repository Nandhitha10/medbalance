"""QAOA circuit construction and cut evaluation for Max-Cut problem."""

from typing import Any, Dict, List, Tuple
import networkx as nx
import qpiai_quantum as qq


def get_graph_nodes_and_edges(graph: nx.Graph) -> Tuple[List[Any], List[Tuple[int, int, float]]]:
    """Extract ordered nodes and indexed edges with weights from a NetworkX graph."""
    node_list = sorted(list(graph.nodes()))
    node_to_idx = {node: idx for idx, node in enumerate(node_list)}
    
    indexed_edges: List[Tuple[int, int, float]] = []
    for u, v, data in graph.edges(data=True):
        w = float(data.get("weight", 1.0))
        u_idx = node_to_idx[u]
        v_idx = node_to_idx[v]
        if u_idx != v_idx:
            indexed_edges.append((min(u_idx, v_idx), max(u_idx, v_idx), w))
            
    return node_list, indexed_edges


def evaluate_cut_value(graph: nx.Graph, partition: Dict[Any, int]) -> float:
    """Calculate the cut weight for a binary node partition {0, 1}."""
    cut_val = 0.0
    for u, v, data in graph.edges(data=True):
        w = float(data.get("weight", 1.0))
        if partition.get(u, 0) != partition.get(v, 0):
            cut_val += w
    return round(cut_val, 4)


def bitstring_to_partition(bitstring: str, node_list: List[Any]) -> Dict[Any, int]:
    """Convert a little-endian measurement bitstring into a node partition mapping."""
    # Rightmost bit corresponds to qubit 0
    partition = {}
    n = len(node_list)
    for idx, node in enumerate(node_list):
        bit_idx = len(bitstring) - 1 - idx
        if 0 <= bit_idx < len(bitstring):
            partition[node] = int(bitstring[bit_idx])
        else:
            partition[node] = 0
    return partition


def build_qaoa_maxcut_circuit(
    graph: nx.Graph,
    gamma: List[float],
    beta: List[float],
    p: int = 1,
) -> qq.Circuit:
    """Build a p-layer QAOA circuit for Max-Cut on the given graph.
    
    Uses standard QAOA ansatz:
    1. Initial state: |+>^n via Hadamard gates on all qubits.
    2. Alternating layers:
       - Problem unitary: e^{-i gamma_l H_C} using RZZ rotations for each edge (u, v)
       - Mixer unitary: e^{-i beta_l H_B} using RX rotations on each qubit
    3. Measure all qubits.
    """
    node_list, indexed_edges = get_graph_nodes_and_edges(graph)
    n = len(node_list)
    if n == 0:
        return qq.Circuit(1)

    qc = qq.Circuit(n)

    # 1. Uniform superposition
    for i in range(n):
        qc.h(i)

    # 2. Alternating p-layers
    for l in range(p):
        g_l = gamma[l] if l < len(gamma) else gamma[-1]
        b_l = beta[l] if l < len(beta) else beta[-1]

        # Cost Hamiltonian evolution: sum_{(u, v) in E} w_{uv} * Z_u Z_v
        # In qpiai_quantum, qc.rzz(qubit1, qubit2, theta) applies exp(-i theta/2 Z_1 Z_2)
        for u_idx, v_idx, weight in indexed_edges:
            theta = 2.0 * g_l * weight
            qc.rzz(u_idx, v_idx, theta)

        # Mixer Hamiltonian evolution: sum_{u in V} X_u
        for i in range(n):
            qc.rx(i, 2.0 * b_l)

    # 3. Measurement
    qc.measure_all()
    return qc
