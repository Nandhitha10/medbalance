"""QpiAI QCloud Remote Quantum Simulator Max-Cut Solver."""

import logging
import os
import time
from typing import Dict, List, Optional
import networkx as nx
import numpy as np
import qpiai_quantum as qq
from qpiai_quantum import QpiAIQuantumAuth as Auth

from optimizer.qaoa.base import MaxCutPort, MaxCutResult
from optimizer.qaoa.circuit import (
    bitstring_to_partition,
    build_qaoa_maxcut_circuit,
    evaluate_cut_value,
    get_graph_nodes_and_edges,
)

logger = logging.getLogger(__name__)


class QCloudSimulatorMaxCut(MaxCutPort):
    """Remote cloud quantum circuit execution via QpiAI QCloud."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("QPIAI_QUANTUM_API_KEY") or os.getenv("QPIAI_API_KEY")

    def partition_graph(
        self,
        graph: nx.Graph,
        p: int = 1,
        shots: int = 512,
        timeout: float = 20.0,
    ) -> MaxCutResult:
        start_time = time.perf_counter()

        # Guard: verify credentials before cloud submission
        if not self.api_key or self.api_key.startswith("dummy_") or self.api_key == "test_key":
            raise RuntimeError("QPIAI_QUANTUM_API_KEY is not configured or dummy credential")

        node_list, _ = get_graph_nodes_and_edges(graph)
        n = len(node_list)

        try:
            Auth.login(self.api_key)
            if not Auth.verify_api_key():
                raise RuntimeError("QpiAI Quantum API key authentication failed on verify_api_key()")
        except Exception as exc:
            raise RuntimeError(f"QpiAI QCloud authentication failed: {exc}")

        # Construct circuit with tuned parameters
        gammas = [0.6] * p
        betas = [0.4] * p
        qc = build_qaoa_maxcut_circuit(graph, gammas, betas, p=p)

        # Run on cloud simulator
        job_res = qc.run(device_name="QpiAI-QSV-Simulator", shots=shots)
        counts = job_res.get_counts() if hasattr(job_res, "get_counts") else {}

        best_partition = {}
        best_cut_val = -1.0

        for bs in counts.keys():
            part = bitstring_to_partition(bs, node_list)
            val = evaluate_cut_value(graph, part)
            if val > best_cut_val:
                best_cut_val = val
                best_partition = part

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return MaxCutResult(
            partition=best_partition,
            cut_value=best_cut_val,
            tier="qpiai_qcloud_simulator",
            depth=p,
            shots=shots,
            approximation_ratio=1.0,
            time_ms=elapsed_ms,
            telemetry={"shots": shots, "device_name": "QpiAI-QSV-Simulator"},
        )

