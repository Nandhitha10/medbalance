"""Solver interfaces and data models for QUBO solving."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple


@dataclass
class Sample:
    """A single binary assignment and its scalar energy."""
    x: Dict[int, int]
    energy: float

    @property
    def bitstring(self) -> List[int]:
        if not self.x:
            return []
        max_idx = max(self.x.keys())
        return [self.x.get(i, 0) for i in range(max_idx + 1)]

    @property
    def feasible(self) -> bool:
        return True

    @property
    def count(self) -> int:
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "bitstring": self.bitstring,
            "energy": self.energy,
        }


@dataclass
class SolverResult:
    """Result from a solver tier including samples and execution telemetry."""
    tier: str
    samples: List[Sample]
    time_ms: float
    n_vars: int
    error: Optional[str] = None
    evidence_file: Optional[str] = None
    tier_attempts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def solver_tier(self) -> str:
        return self.tier

    @property
    def best_sample(self) -> Optional[Sample]:
        return self.samples[0] if self.samples else None


class SolverPort(Protocol):
    """Protocol interface for QUBO solvers."""

    def solve(
        self,
        Q: Dict[Tuple[int, int], float],
        offset: float,
        top_k: int = 5,
        timeout: float = 20.0,
    ) -> List[Sample]:
        """Solve QUBO min_x (x^T Q x + offset) returning top_k lowest energy samples."""
        ...
