"""Harness-benefit training loop (Alpha 40).

The harness-benefit research distinguishes harness UPDATING from harness BENEFIT: a model can
fail to ACTIVATE a skill/harness (never loads it) or load it but fail to FOLLOW it (adherence
failure), and these are distinct from a genuine task failure. This module turns observed
attempts into the datasets + reports that measure and improve this:

- HAR / SLR (activation / skill-load rate): did the harness/skill actually engage?
- HFR (following rate): given it engaged, did the agent follow it?
- PWL (pass-when-loaded): solved among attempts where the skill was loaded.
- adherence decay: HFR dropping across the phases of a long task.

It exports an activation dataset and an adherence dataset (so a model can be trained to
activate/follow better), and a per-adapter HAR/HFR/PWL report — the routing signal that
penalizes harnesses that fail to activate or follow.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class HarnessBenefitRecord:
    adapter: str
    skill_loaded: bool        # the skill/harness artifact was provided
    activated: bool           # the agent actually engaged it (tool call / referenced it)
    followed: bool            # the agent adhered to it (did what it says)
    solved: bool
    phase: int = 0            # phase index within a multi-phase task (for decay)


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def pass_when_loaded_report(records: list) -> dict:
    """Per-adapter HAR/HFR/PWL from observed attempts (the harness-benefit metrics)."""
    by: dict[str, dict] = defaultdict(lambda: {"loaded": 0, "activated": 0, "followed": 0,
                                               "solved_loaded": 0})
    for r in records:
        a = by[r.adapter]
        if r.skill_loaded:
            a["loaded"] += 1
            a["activated"] += int(r.activated)
            a["followed"] += int(r.activated and r.followed)
            a["solved_loaded"] += int(r.solved)
    out = {}
    for adapter, a in by.items():
        out[adapter] = {
            "har": _rate(a["activated"], a["loaded"]),          # activation / skill-load rate
            "hfr": _rate(a["followed"], a["activated"]),        # following rate (given active)
            "pwl": _rate(a["solved_loaded"], a["loaded"]),      # pass when loaded
            "n_loaded": a["loaded"]}
    return {"experiment": "pass_when_loaded", "by_adapter": out}


def build_activation_dataset(records: list) -> list:
    """Training examples: (adapter, skill_loaded) -> did it ACTIVATE? (binary label)."""
    return [{"inputs": {"adapter": r.adapter, "skill_loaded": r.skill_loaded},
             "target": int(r.activated), "label_source": "observed"}
            for r in records if r.skill_loaded]


def build_adherence_dataset(records: list) -> list:
    """Training examples: among ACTIVATED attempts, did the agent FOLLOW the skill?"""
    return [{"inputs": {"adapter": r.adapter, "phase": r.phase},
             "target": int(r.followed), "label_source": "observed"}
            for r in records if r.skill_loaded and r.activated]


def adherence_decay_benchmark(records: list) -> dict:
    """HFR by phase: does adherence decay as a task gets longer? (flags the worst drop)."""
    by_phase: dict[int, dict] = defaultdict(lambda: {"activated": 0, "followed": 0})
    for r in records:
        if r.skill_loaded and r.activated:
            by_phase[r.phase]["activated"] += 1
            by_phase[r.phase]["followed"] += int(r.followed)
    phases = sorted(by_phase)
    hfr = {p: _rate(by_phase[p]["followed"], by_phase[p]["activated"]) for p in phases}
    decays = any(hfr[phases[i]] > hfr[phases[i + 1]] for i in range(len(phases) - 1))
    first_last = (round(hfr[phases[0]] - hfr[phases[-1]], 4) if len(phases) >= 2 else 0.0)
    return {"experiment": "adherence_decay", "hfr_by_phase": hfr,
            "adherence_decays": decays, "first_to_last_drop": first_last}
