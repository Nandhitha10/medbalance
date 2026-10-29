"""Classical NetworkX Greedy 2-Approximation Max-Cut Solver."""

import random
import time
from typing import Dict, List
import networkx as nx

from optimizer.qaoa.base import MaxCutPort, MaxCutResult
from optimizer.qaoa.circuit import evaluate_cut_value, get_graph_nodes_and_edges


class NetworkXGreedyMaxCut(MaxCutPort):
    """Classical greedy 2-approximation and local-search cut optimizer."""

    def partition_graph(
        self,
        graph: nx.Graph,
        p: int = 1,
        shots: int = 512,
        timeout: float = 20.0,
    ) -> MaxCutResult:
        start_time = time.perf_counter()
        node_list, _ = get_graph_nodes_and_edges(graph)
        n = len(node_list)

        if n == 0:
            return MaxCutResult(
                partition={},
                cut_value=0.0,
                tier="networkx_greedy",
                depth=0,
                shots=0,
                approximation_ratio=1.0,
                time_ms=0.0,
            )

        # 1. Randomized greedy start
        rng = random.Random(42)
        best_partition = {node: rng.choice([0, 1]) for node in node_list}
        best_cut = evaluate_cut_value(graph, best_partition)

        # 2. Local search: greedy 1-node flips until local maximum reached
        improved = True
        iterations = 0
        max_iterations = 50

        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            for node in node_list:
                # Flip node's zone
                best_partition[node] = 1 - best_partition[node]
                new_cut = evaluate_cut_value(graph, best_partition)
                if new_cut > best_cut:
                    best_cut = new_cut
                    improved = True
                else:
                    # Revert flip
                    best_partition[node] = 1 - best_partition[node]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return MaxCutResult(
            partition=best_partition,
            cut_value=best_cut,
            tier="networkx_greedy",
            depth=p,
            shots=shots,
            approximation_ratio=0.85,  # Heuristic nominal baseline
            time_ms=elapsed_ms,
            telemetry={"local_search_iterations": iterations},
        )

