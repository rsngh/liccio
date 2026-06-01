"""LLM judge interface + deterministic fake judges (charter §15.3).

Real judges call an LLM and must parse strict JSON (retry on invalid). Fake
judges are deterministic, used in tests and when no key is present. All judges
share a JudgeInput and return an LLMJudgeResult.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from acp.schemas.evaluation import LLMJudgeResult


@dataclass
class JudgeInput:
    task_spec: str
    acceptance_criteria: list[str]
    context_summary: str
    diff: str
    evidence_summary: str
    rubric: str = ""


@runtime_checkable
class LLMJudge(Protocol):
    name: str

    def judge(self, inp: JudgeInput) -> LLMJudgeResult: ...


def parse_judge_json(text: str, retries: int = 2) -> dict:
    """Strict-ish JSON extraction with brace fallback (charter §15.3)."""
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_err = exc
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
                continue
            break
    raise ValueError(f"could not parse judge JSON: {last_err}")


class FakeJudge:
    """Deterministic judge driven by simple diff/evidence heuristics."""

    def __init__(self, name: str, dimension: str) -> None:
        self.name = name
        self.dimension = dimension

    def judge(self, inp: JudgeInput) -> LLMJudgeResult:
        evidence_ok = "failed" not in inp.evidence_summary.lower()
        has_diff = bool(inp.diff.strip())
        if self.dimension == "test_adequacy":
            score = 0.9 if ("test" in inp.diff.lower()) else 0.5
        elif self.dimension == "diff_risk":
            score = 0.3 if len(inp.diff) > 4000 else 0.8
        elif self.dimension == "unrelated_change":
            score = 0.4 if "unrelated" in inp.diff.lower() else 0.9
        else:  # spec_compliance / architecture_fit
            score = 0.85 if (evidence_ok and has_diff) else 0.4
        verdict = "pass" if score >= 0.7 else ("partial" if score >= 0.5 else "fail")
        return LLMJudgeResult(
            score=round(score, 3),
            confidence=0.6,
            verdict=verdict,
            reasons=[f"{self.dimension}: heuristic score {score:.2f}"],
            requires_human_review=score < 0.5,
        )


def default_fake_judges() -> list[FakeJudge]:
    return [
        FakeJudge("SpecComplianceJudge", "spec_compliance"),
        FakeJudge("DiffRiskJudge", "diff_risk"),
        FakeJudge("TestAdequacyJudge", "test_adequacy"),
        FakeJudge("ArchitectureFitJudge", "architecture_fit"),
        FakeJudge("UnrelatedChangeJudge", "unrelated_change"),
    ]
