"""QpiAI Opt solvers and tiered fallback architecture."""

from optimizer.solvers.base import Sample, SolverPort, SolverResult
from optimizer.solvers.chain import solve_chain, write_solver_evidence
from optimizer.solvers.greedy_descent import GreedyDescent
from optimizer.solvers.local_opt import QpiAIOptLocal
from optimizer.solvers.neal_sa import NealSA
from optimizer.solvers.platform import QpiAIOptPlatform

__all__ = [
    "Sample",
    "SolverPort",
    "SolverResult",
    "QpiAIOptPlatform",
    "QpiAIOptLocal",
    "NealSA",
    "GreedyDescent",
    "solve_chain",
    "write_solver_evidence",
]

