# ruff: noqa: E501
"""Multi-agent debate verdict (auto-referee component) — SWE-Search-style discriminator.

A single LLM judge is gameable and inherits the proposer's blind spots. A *debate* — proposer argues
the patch is correct, an adversarial critic must find a concrete reason it's wrong (a failing input, a
violated spec clause, or an overfit/test-gaming tell), and a judge weighs both — raises patch-acceptance
precision (SWE-Search: 73→84%). Crucially it can OVERRULE a single wrong synthesized check (the cause of
battery-v2's gold false-rejections): the judge sees the check failed but the critic can't justify *why*
the behaviour is wrong, so the judge keeps the patch.

Fed only fair evidence: the issue spec, the candidate source, a pass/fail summary of the independent
checks, and adversarial-scan findings on the diff. Never the hidden/gold test. Fail-closed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class DebateVerdict:
    accept: bool
    confidence: float
    rationale: str = ""
    critic_counterexample: str = ""


_PROPOSER = (
    "You are defending a proposed code fix. In <=6 sentences, argue concretely that it CORRECTLY resolves "
    "the issue: what it changes and why that matches the spec, and address the failing checks (if any) as "
    "false alarms only if you can justify it. Be specific; do not hand-wave.\n\n"
    "ISSUE:\n{issue}\n\nPROPOSED FIX:\n```python\n{cand}\n```\n\nINDEPENDENT CHECK RESULTS:\n{checks}\n"
)
_CRITIC = (
    "You are a skeptical reviewer trying to PROVE this fix is wrong or merely overfit. Give the single "
    "strongest concrete objection in <=6 sentences: name an input on which it would produce a wrong "
    "result, a spec requirement it violates, or evidence it special-cases the tests instead of fixing "
    "the cause. If you genuinely cannot find a real defect, say 'NO DEFECT FOUND'.\n\n"
    "ISSUE:\n{issue}\n\nPROPOSED FIX:\n```python\n{cand}\n```\n\nINDEPENDENT CHECK RESULTS:\n{checks}\n"
    "{adversarial}PROPOSER'S DEFENCE:\n{defence}\n"
)
_JUDGE = (
    "You are the judge. Decide whether the fix is CORRECT for the issue, weighing the defence and the "
    "objection. Reject if the critic named a real input/spec violation; accept (overruling a failing "
    "check) only if the critic found NO real defect and the defence is sound. Return ONLY JSON: "
    '{{"accept": true|false, "confidence": 0.0-1.0, "rationale": "<=2 sentences"}}.\n\n'
    "ISSUE:\n{issue}\n\nDEFENCE:\n{defence}\n\nOBJECTION:\n{objection}\n\nINDEPENDENT CHECKS:\n{checks}\n"
)


def _ask(client, model: str, prompt: str, max_tokens: int = 400) -> str:
    msg = client.messages.create(model=model, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def debate_verdict(spec, candidate_src: str, *, client, check_summary: str, diff: str | None = None,
                   model: str = "claude-haiku-4-5", rounds: int = 2) -> DebateVerdict:
    """Proposer -> Critic -> (optional rebuttal) -> Judge. Fail-closed (reject) on any error."""
    if client is None:
        return DebateVerdict(accept=False, confidence=0.0, rationale="no client (fail-closed)")
    issue = getattr(spec, "issue_text", str(spec))[:4000]
    cand = candidate_src[:6000]
    adversarial = ""
    if diff:
        try:
            from acp.schemas.workspace import DiffBundle
            from acp.verification.adversarial import scan_diff
            findings = scan_diff(DiffBundle(unified_diff=diff, changed_files=[]))
            if findings:
                adversarial = "ADVERSARIAL-SCAN FINDINGS (possible test-gaming):\n" + \
                    "\n".join(f"- {getattr(f, 'kind', f)}" for f in findings) + "\n\n"
        except Exception:  # noqa: BLE001
            adversarial = ""
    try:
        defence = _ask(client, model, _PROPOSER.format(issue=issue, cand=cand, checks=check_summary))
        objection = _ask(client, model, _CRITIC.format(issue=issue, cand=cand, checks=check_summary,
                                                       adversarial=adversarial, defence=defence))
        verdict_txt = _ask(client, model, _JUDGE.format(issue=issue, defence=defence,
                                                        objection=objection, checks=check_summary), max_tokens=300)
        m = re.search(r"\{.*\}", verdict_txt, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        accept = bool(d.get("accept", False))
        conf = float(d.get("confidence", 0.0) or 0.0)
        no_defect = "NO DEFECT FOUND" in objection.upper()
        # safety: never accept when the critic produced a concrete objection, regardless of judge text
        if accept and not no_defect and conf < 0.6:
            accept = False
        return DebateVerdict(accept=accept, confidence=round(conf, 3),
                             rationale=str(d.get("rationale", ""))[:300],
                             critic_counterexample=("" if no_defect else objection[:300]))
    except Exception as e:  # noqa: BLE001
        return DebateVerdict(accept=False, confidence=0.0, rationale=f"debate error (fail-closed): {type(e).__name__}")
