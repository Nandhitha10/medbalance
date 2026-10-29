"""Tier 3: dwave-neal Simulated Annealing solver."""

import logging
from typing import Dict, List, Tuple

from optimizer.qubo_builder import energy
from optimizer.solvers.base import Sample, SolverPort

logger = logging.getLogger(__name__)


class NealSA(SolverPort):
    """Solves QUBO via dwave-neal simulated annealing."""

    def __init__(self, num_reads: int = 100, num_sweeps: int = 1000):
        self.num_reads = num_reads
        self.num_sweeps = num_sweeps

    def solve(
        self,
        Q: Dict[Tuple[int, int], float],
        offset: float,
        top_k: int = 5,
        timeout: float = 5.0,
    ) -> List[Sample]:
        try:
            import neal
        except ImportError as e:
            raise RuntimeError(f"dwave-neal not installed: {e}")

        n_vars = 0
        for (i, j) in Q.keys():
            n_vars = max(n_vars, i + 1, j + 1)

        if n_vars == 0:
            return [Sample(x={}, energy=offset)]

        sampler = neal.SimulatedAnnealingSampler()
        reads = max(self.num_reads, top_k * 15)
        sampleset = sampler.sample_qubo(Q, num_reads=reads, num_sweeps=self.num_sweeps)

        unique_samples: List[Sample] = []
        seen_states = set()

        # Iterate over samples ordered by energy ascending
        for rec in sampleset.data(fields=["sample", "energy"], sorted_by="energy"):
            sample_dict = {int(k): int(v) for k, v in rec.sample.items()}
            # Canonical tuple for deduplication
            canonical = tuple(sample_dict.get(i, 0) for i in range(n_vars))
            if canonical in seen_states:
                continue
            seen_states.add(canonical)

            e_val = energy(Q, offset, sample_dict)
            unique_samples.append(Sample(x=sample_dict, energy=e_val))

            if len(unique_samples) >= top_k:
                break

        return unique_samples

