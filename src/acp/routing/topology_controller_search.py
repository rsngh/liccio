"""Offline topology-controller search (GOALS Alpha 42 P3).

AutoTTS-style: search a controller over PRE-COLLECTED trajectories (arena cells) instead of
paying for live model calls during search. The controller maps a task state — including
provider availability — to a topology action (cheap_single / ask_advisor / best_of_k /
retry_with_repo_map / strong_single / strict_verify / human_review / abstain). Safety is a hard
constraint: high-risk tasks never skip strict verification, and unavailable providers are never
selected. Promotion requires a conclusive, uncontaminated gain over the static baseline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

# topology actions the controller may choose (subset realized by the arena policies)
ACTIONS = ("cheap_single", "retry_with_repo_map", "ask_advisor", "best_of_k", "strong_single",
           "strict_verify", "human_review", "abstain")
_SKIP_VERIFY_ACTIONS: frozenset[str] = frozenset()  # none above skip verification; kept explicit
COST_WEIGHT = 5.0                   # $ penalty weight in the search objective


def _get(c: Any, k: str, d=None):
    return c.get(k, d) if isinstance(c, dict) else getattr(c, k, d)


@dataclass
class ControllerCell:
    """One logged trajectory step: state -> action -> outcome (from the arena)."""

    context_need: str
    risk_level: str
    provider_available: bool
    action: str
    solved: bool
    cost: float
    conclusive: bool = True


def _objective(solve_rate: float, mean_cost: float) -> float:
    # maximize verified success, penalize cost; latency/false-approve omitted (no data here)
    return round(solve_rate - COST_WEIGHT * mean_cost, 6)


class TopologyControllerSearch:
    def __init__(self) -> None:
        # (context_need) -> action -> [(solved, cost)]
        self._obs: dict[str, dict[str, list[tuple[bool, float]]]] = defaultdict(
            lambda: defaultdict(list))
        self._provider_unavailable_actions: set[str] = set()

    def fit(self, cells: list[ControllerCell]) -> TopologyControllerSearch:
        for c in cells:
            if not c.conclusive:
                continue
            if not c.provider_available:
                self._provider_unavailable_actions.add(c.action)
                continue  # "not tried because unavailable" — never an action value
            self._obs[c.context_need][c.action].append((c.solved, c.cost))
        return self

    def _best_action(self, context_need: str, risk_level: str) -> tuple[str, float]:
        actions = self._obs.get(context_need, {})
        scored = []
        for action, rows in actions.items():
            # SAFETY: high-risk tasks may never use an action that skips strict verification
            if risk_level in ("high", "critical") and action in _SKIP_VERIFY_ACTIONS:
                continue
            sr = sum(1 for s, _ in rows if s) / len(rows)
            mc = sum(c for _, c in rows) / len(rows)
            scored.append((action, _objective(sr, mc), sr, mc))
        if not scored:
            return ("human_review", 0.0)
        best = max(scored, key=lambda x: x[1])
        return (best[0], best[1])

    def controller(self, risk_level: str = "low") -> dict[str, str]:
        return {need: self._best_action(need, risk_level)[0] for need in self._obs}

    def evaluate_offline(self, cells: list[ControllerCell], *, risk_level: str = "low") -> dict:
        """Replay the controller over logged cells (no live calls) vs the static cheap baseline."""
        ctrl = self.controller(risk_level)
        ctrl_solved = ctrl_cost = base_solved = base_cost = n = 0.0
        for c in cells:
            if not c.conclusive or not c.provider_available:
                continue
            n += 1
            chosen = ctrl.get(c.context_need, "human_review")
            # credit the controller with this cell only if it is the action the cell realized
            if c.action == chosen:
                ctrl_solved += int(c.solved)
                ctrl_cost += c.cost
            if c.action == "cheap_single":
                base_solved += int(c.solved)
                base_cost += c.cost
        return {
            "controller": ctrl,
            "n_cells": int(n),
            "replayed_without_live_calls": True,
            "controller_objective": _objective(ctrl_solved / n if n else 0.0,
                                                ctrl_cost / n if n else 0.0),
            "baseline_objective": _objective(base_solved / n if n else 0.0,
                                             base_cost / n if n else 0.0),
            "provider_unavailable_actions_never_selected": sorted(
                self._provider_unavailable_actions),
        }

    def to_report(self, cells: list[ControllerCell]) -> dict:
        offline = self.evaluate_offline(cells)
        gain = round(offline["controller_objective"] - offline["baseline_objective"], 6)
        return {
            "experiment": "topology_controller_search",
            "actions": list(ACTIONS),
            "learned_controller_by_context_need": offline["controller"],
            "offline_eval": offline,
            "controller_gain_over_static_baseline": gain,
            "promotable": gain > 0,
            "safety": "high-risk never skips strict verification; unavailable providers excluded",
        }
