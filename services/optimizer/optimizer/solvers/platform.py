"""Tier 1: QpiAI Opt Platform cloud solver."""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from optimizer.qubo_builder import energy
from optimizer.solvers.base import Sample, SolverPort

logger = logging.getLogger(__name__)


class QpiAIOptPlatform(SolverPort):
    """Solves QUBO via QpiAI Opt remote cloud platform."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("QPIAI_API_KEY", "")
        self.base_url = base_url or os.getenv("QPIAI_ENDPOINT", "https://api.qpiai.tech")

    def solve(
        self,
        Q: Dict[Tuple[int, int], float],
        offset: float,
        top_k: int = 5,
        timeout: float = 20.0,
    ) -> List[Sample]:
        if not self.api_key or self.api_key in ("your_qpiai_api_key_here", "dummy", "test"):
            raise ValueError("QPIAI_API_KEY is not configured or dummy credential")

        try:
            from qpiai_opt.opt_solvers.client import Client
            from qpiai_opt.opt_solvers.local import QUBOProblem
        except ImportError as e:
            raise RuntimeError(f"qpiai_opt package not installed: {e}")

        # Derive number of variables
        n_vars = 0
        for (i, j) in Q.keys():
            n_vars = max(n_vars, i + 1, j + 1)

        if n_vars == 0:
            return [Sample(x={}, energy=offset)]

        client = Client(api_key=self.api_key, base_url=self.base_url, timeout=timeout)
        client.verify_api_key()

        # Format problem with upper-triangular integer indices
        prob = QUBOProblem(
            problem_type="QUBO",
            num_variables=n_vars,
            matrix_format="upper",
            offset=float(offset),
            variable_names=[f"x_{i}" for i in range(n_vars)],
            qubo_dict={k: float(v) for k, v in Q.items()},
        )

        # Platform solve submission
        from qpiai_opt.opt_solvers import solve as qpiai_solve
        res = qpiai_solve(prob, mode="platform", client=client, allow_platform=True, time_limit=timeout)

        sol_dict = getattr(res, "solution", {}) or getattr(res, "variable_assignment", {})
        sol_vec = {int(k): int(v) for k, v in sol_dict.items()}
        e_val = getattr(res, "objective", None)
        if e_val is None:
            e_val = energy(Q, offset, sol_vec)

        return [Sample(x=sol_vec, energy=float(e_val))]
