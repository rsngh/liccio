"""Preference-reward integration (Alpha 9/10, WS6).

The pairwise preference model (``learning/preference.py``) yields a learned reward
signal from human labels. This module combines it with the objective reward —

    combined_reward = objective_reward + preference_weight * preference_reward

— but only after a **gate** confirms the preference model is trustworthy:
sufficient reviewer agreement, adequate pairwise accuracy, positive post-merge
correlation, and no high-risk degradation. Until the gate passes, the preference
weight is forced to zero so routing optimizes the objective reward alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PreferenceRewardGate:
    min_reviewer_agreement: float = 0.7
    min_pairwise_accuracy: float = 0.7
    min_post_merge_correlation: float = 0.0
    max_high_risk_degradation: float = 0.0

    def evaluate(
        self,
        *,
        reviewer_agreement: float,
        pairwise_accuracy: float,
        post_merge_correlation: float,
        high_risk_degradation: float,
    ) -> dict:
        conditions = {
            "reviewer_agreement": reviewer_agreement >= self.min_reviewer_agreement,
            "pairwise_accuracy": pairwise_accuracy >= self.min_pairwise_accuracy,
            "post_merge_correlation": post_merge_correlation >= self.min_post_merge_correlation,
            "high_risk_not_degraded":
                high_risk_degradation <= self.max_high_risk_degradation + 1e-9,
        }
        passed = all(conditions.values())
        return {
            "passed": passed,
            "conditions": conditions,
            "reasons": [k for k, ok in conditions.items() if not ok] or ["all conditions met"],
        }


@dataclass
class PreferenceRewardCombiner:
    """Combines objective + (gated) preference reward into a single signal."""

    preference_weight: float = 0.5
    gate: PreferenceRewardGate = field(default_factory=PreferenceRewardGate)
    _enabled: bool = False

    def apply_gate(self, gate_result: dict) -> bool:
        """Enable the preference reward only when the gate passes."""
        self._enabled = bool(gate_result.get("passed"))
        return self._enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def combine(self, objective_reward: float, preference_reward: float) -> float:
        if not self._enabled:
            return objective_reward
        return objective_reward + self.preference_weight * preference_reward

    def components(self, objective_reward: float, preference_reward: float) -> dict:
        """Reward components dict (satisfies RewardEvent's explain-reward validator)."""
        comps = {"objective": objective_reward}
        if self._enabled:
            comps["preference"] = self.preference_weight * preference_reward
        return comps
