"""Tier 2: QpiAI Opt Local solver."""

import logging
import os
from typing import Dict, List, Optional, Tuple

from optimizer.qubo_builder import energy
from optimizer.solvers.base import Sample, SolverPort

logger = logging.getLogger(__name__)


class QpiAIOptLocal(SolverPort):
    """Solves QUBO via QpiAI Opt local provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("QPIAI_API_KEY", "")

    def solve(
        self,
        Q: Dict[Tuple[int, int], float],
        offset: float,
        top_k: int = 5,
        timeout: float = 10.0,
    ) -> List[Sample]:
        if not self.api_key or self.api_key in ("your_qpiai_api_key_here", "dummy", "test"):
            raise ValueError("QPIAI_API_KEY is not configured for LocalProvider")

        try:
            from qpiai_opt.opt_solvers.client import Client
            from qpiai_opt.opt_solvers.local import LocalProvider, QUBOProblem
        except ImportError as e:
            raise RuntimeError(f"qpiai_opt package not installed: {e}")

        n_vars = 0
        for (i, j) in Q.keys():
            n_vars = max(n_vars, i + 1, j + 1)

        if n_vars == 0:
            return [Sample(x={}, energy=offset)]

        client = Client(api_key=self.api_key, timeout=timeout)
        provider = LocalProvider(client=client)

        prob = QUBOProblem(
            problem_type="QUBO",
            num_variables=n_vars,
            matrix_format="upper",
            offset=float(offset),
            variable_names=[f"x_{i}" for i in range(n_vars)],
            qubo_dict={k: float(v) for k, v in Q.items()},
        )

        res = provider.solve(prob, problem_class="QUBO", time_limit=timeout)
        sol_dict = getattr(res, "solution", {}) or getattr(res, "variable_assignment", {})
        sol_vec = {int(k): int(v) for k, v in sol_dict.items()}
        e_val = getattr(res, "objective", None)
        if e_val is None:
            e_val = energy(Q, offset, sol_vec)

        return [Sample(x=sol_vec, energy=float(e_val))]
