"""In-process metrics counters/gauges (charter §23.2)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

METRIC_NAMES = (
    "runs_total",
    "runs_succeeded_total",
    "runs_failed_total",
    "human_review_required_total",
    "agent_attempts_total",
    "tokens_used_total",
    "estimated_cost_usd_total",
    "verification_failures_total",
    "policy_exploration_total",
)


@dataclass
class Metrics:
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _gauges: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] += value

    def observe(self, name: str, value: float) -> None:
        self._gauges[name].append(value)

    def mean(self, name: str) -> float:
        vals = self._gauges.get(name, [])
        return sum(vals) / len(vals) if vals else 0.0

    def snapshot(self) -> dict[str, float]:
        out = dict(self.counters)
        for k in self._gauges:
            out[f"{k}_mean"] = self.mean(k)
        return out
