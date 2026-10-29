"""Local Statevector QAOA Max-Cut Solver (QSVLocal)."""

import logging
import time
from typing import Dict, List, Optional
import networkx as nx
import numpy as np
import qpiai_quantum as qq
from qpiai_quantum.simulator import StatevectorSimulator
from scipy.optimize import minimize

from optimizer.qaoa.base import MaxCutPort, MaxCutResult
from optimizer.qaoa.circuit import (
    bitstring_to_partition,
    build_qaoa_maxcut_circuit,
    evaluate_cut_value,
    get_graph_nodes_and_edges,
)

logger = logging.getLogger(__name__)


class QSVLocalMaxCut(MaxCutPort):
    """Local quantum circuit simulation using QpiAI StatevectorSimulator."""

    def __init__(self):
        self.simulator = StatevectorSimulator()

    def partition_graph(
        self,
        graph: nx.Graph,
        p: int = 1,
        shots: int = 512,
        timeout: float = 20.0,
    ) -> MaxCutResult:
        start_time = time.perf_counter()
        node_list, indexed_edges = get_graph_nodes_and_edges(graph)
        n = len(node_list)

        if n == 0:
            return MaxCutResult(
                partition={},
                cut_value=0.0,
                tier="qsv_local",
                depth=0,
                shots=0,
                approximation_ratio=1.0,
                time_ms=0.0,
            )

        if n == 1:
            return MaxCutResult(
                partition={node_list[0]: 0},
                cut_value=0.0,
                tier="qsv_local",
                depth=p,
                shots=shots,
                approximation_ratio=1.0,
                time_ms=0.1,
            )

        # Objective function for classical optimization over QAOA parameters
        # params: [gamma_0, ..., gamma_{p-1}, beta_0, ..., beta_{p-1}]
        eval_shots = min(shots, 256)

        def loss(params: np.ndarray) -> float:
            gammas = list(params[:p])
            betas = list(params[p:])

            qc = build_qaoa_maxcut_circuit(graph, gammas, betas, p=p)
            try:
                res = self.simulator.run(qc, shots=eval_shots)
                counts = res.get_counts()
            except Exception as e:
                logger.debug("Statevector simulation iteration failed: %s", e)
                return 0.0

            total_cut = 0.0
            total_cnt = 0
            for bs, cnt in counts.items():
                part = bitstring_to_partition(bs, node_list)
                total_cut += evaluate_cut_value(graph, part) * cnt
                total_cnt += cnt

            expected_cut = total_cut / max(total_cnt, 1)
            # Minimize negative expected cut to maximize cut
            return -expected_cut

        # Initial parameter guess
        init_params = np.array([0.5] * p + [0.3] * p)

        # Optimize variational parameters with COBYLA
        opt_res = minimize(
            loss,
            init_params,
            method="COBYLA",
            options={"maxiter": 15, "tol": 1e-3},
        )

        best_gammas = list(opt_res.x[:p])
        best_betas = list(opt_res.x[p:])

        # Final sampling with full shots from the optimized circuit
        final_qc = build_qaoa_maxcut_circuit(graph, best_gammas, best_betas, p=p)
        sim_res = self.simulator.run(final_qc, shots=shots)
        final_counts = sim_res.get_counts()

        # Find best cut among all measured samples
        best_partition = {}
        best_cut_val = -1.0

        for bs in final_counts.keys():
            part = bitstring_to_partition(bs, node_list)
            val = evaluate_cut_value(graph, part)
            if val > best_cut_val:
                best_cut_val = val
                best_partition = part

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return MaxCutResult(
            partition=best_partition,
            cut_value=best_cut_val,
            tier="qsv_local",
            depth=p,
            shots=shots,
            approximation_ratio=1.0,  # Filled by chain against exact
            time_ms=elapsed_ms,
            telemetry={
                "optimized_gammas": [round(float(g), 4) for g in best_gammas],
                "optimized_betas": [round(float(b), 4) for b in best_betas],
                "n_qubits": n,
                "n_edges": len(indexed_edges),
                "optimization_iterations": getattr(opt_res, "nfev", 15),
            },
        )
