"""Harness evolver (Alpha 13): propose harness updates from execution evidence.

The evolution *pipeline* (`harness_evolution.py`) governs whether a proposed
harness change may be promoted. The evolver is what *authors* a proposal — from
real execution evidence. It inspects activation/adherence over recent traces and,
when a systematic weakness shows up (the harness rarely reads before writing, or
rarely runs verification, or frequently fails to activate at all), emits a
targeted, conservative prompt-diff proposal plus the evidence run ids. It never
promotes anything — its output flows into the governed pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.evaluation.harness_metrics import activation_report
from acp.schemas.trace import AgentTrace
from acp.training.harness_evolution import HarnessUpdateProposal

# Below these rates over the evidence window, the evolver proposes a fix.
_ACTIVATION_FLOOR = 0.8
_ADHERENCE_FLOOR = 0.7
_MIN_EVIDENCE = 5

_REMEDIES: dict[str, str] = {
    "activation": "Add to system prompt: you MUST use the provided tools "
                  "(read_file/write_file/run_command) to make changes; do not "
                  "answer in prose without editing the workspace.",
    "read_before_write": "Add to system prompt: ALWAYS read_file the target file "
                         "before write_file, and base your edit on its real content.",
    "verification": "Add to system prompt: after editing, run_command the project's "
                    "tests and iterate until they pass before finishing.",
}


@dataclass
class EvolverFinding:
    weakness: str          # activation | read_before_write | verification
    rate: float
    floor: float
    n_evidence: int


def analyze(harness_name: str, traces: list[AgentTrace]) -> list[EvolverFinding]:
    """Find systematic harness weaknesses over the evidence window."""
    mine = [t for t in traces if t.adapter_name == harness_name and t.is_harness]
    if len(mine) < _MIN_EVIDENCE:
        return []
    n = len(mine)
    activated = [t for t in mine if activation_report(t).activated]
    act_rate = len(activated) / n
    findings: list[EvolverFinding] = []
    if act_rate < _ACTIVATION_FLOOR:
        findings.append(EvolverFinding("activation", round(act_rate, 3),
                                       _ACTIVATION_FLOOR, n))
    # Adherence signals only make sense over the activated subset.
    if activated:
        na = len(activated)
        read_first = sum(1 for t in activated if t.file_reads > 0) / na
        verified = sum(1 for t in activated if t.commands > 0) / na
        if read_first < _ADHERENCE_FLOOR:
            findings.append(EvolverFinding("read_before_write", round(read_first, 3),
                                           _ADHERENCE_FLOOR, na))
        if verified < _ADHERENCE_FLOOR:
            findings.append(EvolverFinding("verification", round(verified, 3),
                                           _ADHERENCE_FLOOR, na))
    return findings


def propose_from_evidence(
    harness_name: str, traces: list[AgentTrace]
) -> HarnessUpdateProposal | None:
    """Author a conservative prompt-diff proposal from the strongest weakness, or
    ``None`` when the harness behaves well / there is insufficient evidence."""
    findings = analyze(harness_name, traces)
    if not findings:
        return None
    # Address the most-violated weakness first (largest gap below its floor).
    worst = max(findings, key=lambda f: f.floor - f.rate)
    remedy = _REMEDIES[worst.weakness]
    evidence_ids = [t.attempt_id for t in traces
                    if t.adapter_name == harness_name and t.is_harness]
    return HarnessUpdateProposal(
        harness_name=harness_name,
        rationale=(f"{worst.weakness} rate {worst.rate} below floor {worst.floor} "
                   f"over {worst.n_evidence} runs"),
        proposed_diff=remedy,
        evidence_run_ids=evidence_ids,
    )
