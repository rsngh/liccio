"""Policy registry: champion/challenger rollout (charter §13.7, §16.4)."""

from __future__ import annotations

import random

from acp.core.enums import PolicyStatus
from acp.schemas.learning import PolicyVersion


class PolicyRegistry:
    def __init__(self, seed: int = 1234) -> None:
        self._policies: dict[str, PolicyVersion] = {}
        self._rng = random.Random(seed)

    def register(self, policy: PolicyVersion) -> PolicyVersion:
        self._policies[policy.id] = policy
        return policy

    def champion(self) -> PolicyVersion | None:
        for p in self._policies.values():
            if p.status in (PolicyStatus.CHAMPION.value, PolicyStatus.CHAMPION):
                return p
        return None

    def challenger(self) -> PolicyVersion | None:
        for p in self._policies.values():
            if p.status in (PolicyStatus.CHALLENGER.value, PolicyStatus.CHALLENGER):
                return p
        return None

    def promote(self, policy_id: str, traffic_fraction: float = 1.0) -> PolicyVersion:
        if policy_id not in self._policies:
            raise KeyError(policy_id)
        target = self._policies[policy_id]
        if traffic_fraction >= 1.0:
            # full promotion: demote current champion to archived
            current = self.champion()
            if current is not None and current.id != policy_id:
                current.status = PolicyStatus.ARCHIVED
            target.status = PolicyStatus.CHAMPION
            target.traffic_fraction = 1.0
        else:
            target.status = PolicyStatus.CHALLENGER
            target.traffic_fraction = traffic_fraction
        return target

    def rollback(self, to_policy_id: str) -> PolicyVersion:
        """Restore a previous policy to champion, archiving challengers."""
        if to_policy_id not in self._policies:
            raise KeyError(to_policy_id)
        for p in self._policies.values():
            if p.status in (PolicyStatus.CHALLENGER.value, PolicyStatus.CHAMPION.value):
                p.status = PolicyStatus.ARCHIVED
                p.traffic_fraction = 0.0
        champ = self._policies[to_policy_id]
        champ.status = PolicyStatus.CHAMPION
        champ.traffic_fraction = 1.0
        return champ

    def select_for_traffic(self) -> PolicyVersion | None:
        """Route a single request: challenger with its traffic fraction, else champion."""
        challenger = self.challenger()
        champion = self.champion()
        if challenger is not None and self._rng.random() < challenger.traffic_fraction:
            return challenger
        return champion

    def all(self) -> list[PolicyVersion]:
        return list(self._policies.values())
