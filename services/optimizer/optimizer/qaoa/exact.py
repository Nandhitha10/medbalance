"""Exact Brute-Force Max-Cut Solver (n <= 16)."""

import itertools
import time
from typing import Dict, List, Optional
import networkx as nx

from optimizer.qaoa.base import MaxCutPort, MaxCutResult
from optimizer.qaoa.circuit import evaluate_cut_value, get_graph_nodes_and_edges


class ExactBruteForceMaxCut(MaxCutPort):
    """Exhaustive brute-force search finding the exact global Max-Cut optimum."""

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
                tier="exact_brute_force",
                depth=0,
                shots=0,
                approximation_ratio=1.0,
                time_ms=0.0,
                exact_cut_value=0.0,
            )

        if n > 16:
            raise ValueError(f"ExactBruteForceMaxCut only supports n <= 16 nodes (received {n})")

        best_partition: Dict[str, int] = {}
        max_cut = -1.0

        # Enumerate all 2^n assignments
        for bits in itertools.product([0, 1], repeat=n):
            candidate_part = {node_list[i]: bits[i] for i in range(n)}
            val = evaluate_cut_value(graph, candidate_part)
            if val > max_cut:
                max_cut = val
                best_partition = candidate_part

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return MaxCutResult(
            partition=best_partition,
            cut_value=max_cut,
            tier="exact_brute_force",
            depth=p,
            shots=shots,
            approximation_ratio=1.0,
            time_ms=elapsed_ms,
            exact_cut_value=max_cut,
            telemetry={"total_states_evaluated": 2 ** n},
        )
