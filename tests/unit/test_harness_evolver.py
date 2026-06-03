"""Harness evolver: evidence-driven proposals into the governed pipeline (Alpha 13)."""

from __future__ import annotations

from acp.schemas.trace import AgentTrace
from acp.training.harness_evolution import (
    HarnessUpdateCanary,
    HarnessUpdateEval,
    HarnessUpdateReview,
    HarnessUpdateRollback,
    evaluate_update,
    scan_diff,
)
from acp.training.harness_evolver import analyze, propose_from_evidence


def _trace(i: int, *, reads: int, commands: int, tool_calls: int = 2,
           adapter: str = "openai_harness") -> AgentTrace:
    return AgentTrace(attempt_id=f"att{i}", adapter_name=adapter, is_harness=True,
                      status="succeeded", tool_calls=tool_calls, file_reads=reads,
                      file_writes=["f.py"], commands=commands, changed_files=["f.py"])


def test_no_proposal_when_harness_behaves_well() -> None:
    good = [_trace(i, reads=1, commands=1) for i in range(8)]
    assert propose_from_evidence("openai_harness", good) is None


def test_proposes_read_before_write_fix() -> None:
    # Activates + verifies, but never reads first -> read_before_write weakness.
    traces = [_trace(i, reads=0, commands=1) for i in range(8)]
    findings = {f.weakness for f in analyze("openai_harness", traces)}
    assert "read_before_write" in findings
    proposal = propose_from_evidence("openai_harness", traces)
    assert proposal is not None
    assert "read_file" in proposal.proposed_diff
    assert len(proposal.evidence_run_ids) == 8


def test_proposes_activation_fix_when_no_tool_calls() -> None:
    traces = [_trace(i, reads=0, commands=0, tool_calls=0) for i in range(8)]
    proposal = propose_from_evidence("openai_harness", traces)
    assert proposal is not None
    assert "tools" in proposal.proposed_diff.lower()


def test_insufficient_evidence_yields_no_proposal() -> None:
    assert propose_from_evidence("openai_harness",
                                 [_trace(0, reads=0, commands=0)]) is None


def test_proposal_flows_through_governed_pipeline() -> None:
    traces = [_trace(i, reads=0, commands=1) for i in range(8)]
    proposal = propose_from_evidence("openai_harness", traces)
    assert proposal is not None
    # The evolver only authors; promotion still requires full governance.
    dec = evaluate_update(
        proposal, diff=scan_diff(proposal),
        evaluation=HarnessUpdateEval(regression_passed=True,
                                     negative_transfer_passed=True,
                                     baseline_score=0.7, candidate_score=0.82),
        review=HarnessUpdateReview(approved=True, reviewer="alice"),
        canary=HarnessUpdateCanary(),
        rollback=HarnessUpdateRollback(plan="revert", previous_version="v1"))
    assert dec.promoted is True
