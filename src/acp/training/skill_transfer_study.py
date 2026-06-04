"""Cross-harness skill transfer study (Alpha 21 WS13).

The SkillOpt paper reports strong cross-harness transfer (e.g. Codex<->Claude Code). This
classifies a skill's portability from measured (direct, transferred) scores: a skill that
holds its lift on a *target* harness is PORTABLE (scope it broadly); one that loses the
lift is HARNESS-SPECIFIC (narrow its scope to the source harness). The output is a concrete
scope recommendation per skill, so ACP knows which skills are portable and which are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A transfer that retains at least this fraction of the source lift is "portable".
PORTABLE_RETENTION = 0.5
# A transferred score below baseline by more than this is negative transfer.
NEG_TRANSFER_EPS = 0.02


@dataclass
class TransferObservation:
    """One source->target measurement for a skill."""

    source_harness: str
    target_harness: str
    target_baseline: float       # target solve-rate without the skill
    target_with_skill: float     # target solve-rate with the source-optimized skill
    source_lift: float           # the lift the skill produced on its source harness


@dataclass
class TransferVerdict:
    source_harness: str
    target_harness: str
    transfer_gain: float
    portable: bool
    negative_transfer: bool
    recommendation: str


@dataclass
class TransferStudy:
    skill_name: str
    verdicts: list[TransferVerdict] = field(default_factory=list)
    scope_recommendation: str = ""


def evaluate_observation(obs: TransferObservation) -> TransferVerdict:
    gain = round(obs.target_with_skill - obs.target_baseline, 4)
    negative = gain < -NEG_TRANSFER_EPS
    portable = (obs.source_lift > 0 and gain >= PORTABLE_RETENTION * obs.source_lift)
    if negative:
        rec = f"harness-specific: hurts {obs.target_harness} -> exclude that scope"
    elif portable:
        rec = f"portable to {obs.target_harness}"
    else:
        rec = f"weak transfer to {obs.target_harness} -> keep source-scoped"
    return TransferVerdict(
        source_harness=obs.source_harness, target_harness=obs.target_harness,
        transfer_gain=gain, portable=portable, negative_transfer=negative,
        recommendation=rec)


def run_transfer_study(skill_name: str, observations: list[TransferObservation]) -> TransferStudy:
    """Aggregate observations into a study with an overall scope recommendation."""
    verdicts = [evaluate_observation(o) for o in observations]
    any_negative = any(v.negative_transfer for v in verdicts)
    all_portable = bool(verdicts) and all(v.portable for v in verdicts)
    if any_negative:
        rec = "narrow: harness-specific (negative transfer on >=1 target)"
    elif all_portable:
        rec = "broaden: portable across tested harnesses"
    else:
        rec = "keep source-scoped: transfer not established"
    return TransferStudy(skill_name=skill_name, verdicts=verdicts,
                         scope_recommendation=rec)
