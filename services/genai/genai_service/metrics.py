"""Health and latency metrics for GenAI gateway."""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CallMetric:
    purpose: str
    cached: bool
    latency_sec: float
    ok: bool
    fallback: bool
    schema_failure: bool
    firewall_block: bool
    timestamp: float = field(default_factory=time.time)


class MetricsTracker:
    """In-memory rolling metrics window for last 24 hours."""

    def __init__(self, window_seconds: float = 86400.0) -> None:
        self.window_seconds = window_seconds
        self._history: List[CallMetric] = []

    def record(
        self,
        purpose: str,
        cached: bool,
        latency_sec: float,
        ok: bool = True,
        fallback: bool = False,
        schema_failure: bool = False,
        firewall_block: bool = False,
    ) -> None:
        """Record an LLM call metric."""
        metric = CallMetric(
            purpose=purpose,
            cached=cached,
            latency_sec=latency_sec,
            ok=ok,
            fallback=fallback,
            schema_failure=schema_failure,
            firewall_block=firewall_block,
            timestamp=time.time(),
        )
        self._history.append(metric)
        self._trim()

    def _trim(self) -> None:
        cutoff = time.time() - self.window_seconds
        # Keep only within 24h window
        if self._history and self._history[0].timestamp < cutoff:
            self._history = [m for m in self._history if m.timestamp >= cutoff]

    def get_summary(self) -> Dict[str, Any]:
        """Aggregate stats over the rolling window."""
        self._trim()
        total_calls = len(self._history)
        if total_calls == 0:
            return {
                "total_calls": 0,
                "cache_hits": 0,
                "cache_hit_rate": 0.0,
                "p50_latency_sec": 0.0,
                "p95_latency_sec": 0.0,
                "schema_failures": 0,
                "fallbacks": 0,
                "firewall_blocks": 0,
                "by_purpose": {},
            }

        cache_hits = sum(1 for m in self._history if m.cached)
        cache_hit_rate = round(cache_hits / total_calls, 4)
        schema_failures = sum(1 for m in self._history if m.schema_failure)
        fallbacks = sum(1 for m in self._history if m.fallback)
        firewall_blocks = sum(1 for m in self._history if m.firewall_block)

        # Latencies (from non-cached calls, or all calls)
        latencies = sorted(m.latency_sec for m in self._history)
        p50 = 0.0
        p95 = 0.0
        if latencies:
            p50 = round(latencies[len(latencies) // 2], 3)
            p95_idx = min(len(latencies) - 1, int(math.ceil(0.95 * len(latencies))) - 1)
            p95 = round(latencies[p95_idx], 3)

        by_purpose: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "cache_hits": 0, "fallbacks": 0, "schema_failures": 0}
        )
        for m in self._history:
            bp = by_purpose[m.purpose]
            bp["total"] += 1
            if m.cached:
                bp["cache_hits"] += 1
            if m.fallback:
                bp["fallbacks"] += 1
            if m.schema_failure:
                bp["schema_failures"] += 1

        return {
            "total_calls": total_calls,
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hit_rate,
            "p50_latency_sec": p50,
            "p95_latency_sec": p95,
            "schema_failures": schema_failures,
            "fallbacks": fallbacks,
            "firewall_blocks": firewall_blocks,
            "by_purpose": dict(by_purpose),
        }

    def clear(self) -> None:
        self._history.clear()


# Global tracker instance
metrics_tracker = MetricsTracker()
