# ruff: noqa: E501
"""Difficulty probe — predict whether the cheap rung is doomed, and start the ladder higher.

Prong C of the pdfs/ research synthesis: blind cheapest-first pays for a doomed cheap attempt on
every hard task. The sufficient-context idea (2411.06037), MetaCogAgent capability profiles
(2605.22026) and the efficiency-frontier framework (2605.23071) all converge on the same move —
estimate task difficulty from signals available BEFORE any attempt, and route accordingly.

The probe is deliberately tiny and transparent: a logistic model over features computable from what
the router legitimately sees at intake (issue text, module size, failing-test size, package shape).
No gold patch, no hidden-oracle access, no learned embeddings. With only dozens of labeled bundles,
honesty demands leave-one-out evaluation — the eval (evals/issue_replay/predictive_routing.py)
reports LOO numbers, never trained-on-test ones.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# weights are fit by DifficultyProbe.fit; feature order is fixed and documented
FEATURE_NAMES = (
    "module_kb",        # bigger module -> harder localization/repair
    "test_kb",          # bigger failing-test file -> broader oracle, harder to satisfy
    "is_feature_add",   # issue asks to ADD/implement something new (not fix existing logic)
    "is_package",       # package bundle with sibling modules (cross-module reasoning)
    "n_funcs_over_50",  # very large API surface
)


def features(*, issue_title: str, issue_body: str, module_src: str, test_src: str,
             n_extra_files: int) -> list[float]:
    n_funcs = len(re.findall(r"^\s*def\s+\w+", module_src, re.M))
    add_words = re.search(r"\b(add|implement|support|new|introduce)\b", issue_title, re.I)
    return [
        min(len(module_src) / 1024.0, 60.0) / 60.0,
        min(len(test_src) / 1024.0, 120.0) / 120.0,
        1.0 if add_words else 0.0,
        1.0 if n_extra_files > 0 else 0.0,
        1.0 if n_funcs > 50 else 0.0,
    ]


@dataclass
class DifficultyProbe:
    """P(cheap rung FAILS). Pure-python logistic regression — auditable, dependency-free."""

    weights: list[float] = field(default_factory=lambda: [0.0] * (len(FEATURE_NAMES) + 1))

    def predict(self, x: list[float]) -> float:
        z = self.weights[0] + sum(w * v for w, v in zip(self.weights[1:], x, strict=True))
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def fit(self, xs: list[list[float]], ys: list[int], *, lr: float = 0.5, epochs: int = 400,
            l2: float = 0.05) -> DifficultyProbe:
        """ys[i] = 1 if the cheap rung FAILED bundle i. L2 keeps the tiny-n fit conservative."""
        n = len(xs)
        w = [0.0] * (len(FEATURE_NAMES) + 1)
        for _ in range(epochs):
            g = [0.0] * len(w)
            for x, y in zip(xs, ys, strict=True):
                z = w[0] + sum(wi * v for wi, v in zip(w[1:], x, strict=True))
                p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
                err = p - y
                g[0] += err
                for j, v in enumerate(x):
                    g[j + 1] += err * v
            for j in range(len(w)):
                reg = l2 * w[j] if j else 0.0
                w[j] -= lr * (g[j] / n + reg)
        self.weights = w
        return self

    def start_rung(self, x: list[float], *, threshold: float = 0.85) -> int:
        """0 = start at the cheap rung; 1 = skip it (predicted doomed) and start at the first agent."""
        return 1 if self.predict(x) >= threshold else 0
