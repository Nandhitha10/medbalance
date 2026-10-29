"""Base interfaces and data structures for QAOA Max-Cut graph partitioning."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
import networkx as nx


@dataclass
class MaxCutResult:
    """Result of a Max-Cut graph partitioning computation."""
    partition: Dict[str, int]  # Mapping node_id -> zone {0, 1}
    cut_value: float
    tier: str
    depth: int
    shots: int
    approximation_ratio: float
    time_ms: float
    exact_cut_value: Optional[float] = None
    evidence_file: Optional[str] = None
    error: Optional[str] = None
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partition": self.partition,
            "cut_value": self.cut_value,
            "tier": self.tier,
            "depth": self.depth,
            "shots": self.shots,
            "approximation_ratio": self.approximation_ratio,
            "time_ms": self.time_ms,
            "exact_cut_value": self.exact_cut_value,
            "evidence_file": self.evidence_file,
            "error": self.error,
            "telemetry": self.telemetry,
        }


class MaxCutPort(Protocol):
    """Protocol for graph partitioning solvers."""

    def partition_graph(
        self,
        graph: nx.Graph,
        p: int = 1,
        shots: int = 512,
        timeout: float = 20.0,
    ) -> MaxCutResult:
        """Partition graph vertices into two zones {0, 1} maximizing the cut."""
        ...
