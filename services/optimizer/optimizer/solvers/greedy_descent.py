"""Tier 4: Pure deterministic greedy local 1-bit-flip descent solver."""

import logging
from typing import Dict, List, Set, Tuple

from optimizer.qubo_builder import energy
from optimizer.solvers.base import Sample, SolverPort

logger = logging.getLogger(__name__)


class GreedyDescent(SolverPort):
    """Deterministic 1-bit-flip local descent solver with multi-start restarts."""

    def __init__(self, max_restarts: int = 5):
        self.max_restarts = max_restarts

    def solve(
        self,
        Q: Dict[Tuple[int, int], float],
        offset: float,
        top_k: int = 5,
        timeout: float = 3.0,
    ) -> List[Sample]:
        n_vars = 0
        for (i, j) in Q.keys():
            n_vars = max(n_vars, i + 1, j + 1)

        if n_vars == 0:
            return [Sample(x={}, energy=offset)]

        found_samples: Dict[Tuple[int, ...], float] = {}

        # Starting points: all-zeros, all-ones, single-bit on favorable diagonals
        starts: List[List[int]] = [
            [0] * n_vars,
            [1] * n_vars,
        ]

        # Greedy start based on negative diagonal coefficients
        diag_start = [1 if Q.get((i, i), 0.0) < 0.0 else 0 for i in range(n_vars)]
        starts.append(diag_start)

        for s in starts:
            current = list(s)
            curr_e = energy(Q, offset, current)

            # Local 1-flip descent loop
            while True:
                best_flip = -1
                best_delta = 0.0

                for i in range(n_vars):
                    # Flip bit i
                    flipped = list(current)
                    flipped[i] = 1 - flipped[i]
                    f_energy = energy(Q, offset, flipped)
                    delta = f_energy - curr_e

                    if delta < best_delta - 1e-9:
                        best_delta = delta
                        best_flip = i

                if best_flip >= 0 and best_delta < -1e-9:
                    current[best_flip] = 1 - current[best_flip]
                    curr_e += best_delta
                else:
                    break

            cand_tuple = tuple(current)
            found_samples[cand_tuple] = curr_e

        # Sort found samples by energy ascending
        sorted_samples = sorted(found_samples.items(), key=lambda item: item[1])
        result: List[Sample] = []
        for state_tup, e_val in sorted_samples[:top_k]:
            sol_dict = {i: state_tup[i] for i in range(n_vars)}
            result.append(Sample(x=sol_dict, energy=round(e_val, 6)))

        return result
