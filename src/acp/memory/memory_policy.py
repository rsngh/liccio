"""Memory policy — governed read/write rules for the experience bank (GOALS Alpha 42 P10).

Write only conclusive attempts (no measurement noise into memory); keep negative failures so
the router learns what NOT to do; quarantine poisoned episodes (a claimed success with negative
reward, or a success that left tests un-run — internally inconsistent and likely injected).
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.memory.experience_bank import ExperienceEpisode


@dataclass
class MemoryPolicy:
    write_only_conclusive: bool = True
    write_negative_failures: bool = True
    half_life: float = 10.0

    def may_write(self, ep: ExperienceEpisode) -> bool:
        if self.write_only_conclusive and not ep.is_conclusive:
            return False  # inconclusive/infra attempts never enter memory
        return not (ep.is_negative and not self.write_negative_failures)

    @staticmethod
    def poison_detector(ep: ExperienceEpisode) -> bool:
        """Flag internally-inconsistent / likely-injected episodes for quarantine."""
        # claims solved but with a negative reward / without running tests, OR a "reverted"
        # post-merge episode that still claims a positive reward — internally inconsistent.
        claims_solved_but_bad = ep.verifier_outcome == "solved" and (
            ep.reward < 0 or not ep.tests_run)
        reverted_but_positive = ep.post_merge_outcome == "reverted" and ep.reward > 0
        return claims_solved_but_bad or reverted_but_positive
