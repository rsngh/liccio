# ruff: noqa: E501
"""Auto-referee — the trustworthy verify-stop = mutation-validated battery AND multi-agent debate.

The whole investigation's open problem: an automatic correctness gate you can trust to auto-commit a
cheap fix. Synthesized-test gates failed because they (a) were sometimes too WEAK (non-discriminating →
vacuous pass) or (b) carried a single WRONG check (→ rejecting correct fixes), and were gameable. The
referee composes two orthogonal hardeners that each attack one failure:

  * MUTATION-VALIDATION (MuTAP): only trust the battery's verdict if its discriminating checks actually
    kill focus-region mutants (battery.mutation_info["mutation_score"] >= floor). A weak/vacuous battery
    fails this gate → the referee ABSTAINS (escalate / human-review) rather than false-committing.
  * MULTI-AGENT DEBATE (SWE-Search): a critic must find a concrete defect; the judge can overrule a
    single wrong check when no real defect is named — recovering the golds battery-v2 wrongly rejected,
    while still catching overfit (the critic flags input-special-casing; adversarial-high → reject).

accept := battery.accept() AND mutation_validated AND debate.accept. Otherwise `reason` says which gate
abstained, so the router escalates instead of committing. Never reads the hidden/gold test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from acp.verification.debate import DebateVerdict, debate_verdict
from acp.verification.repair_battery import RepairBattery, score_candidate


@dataclass
class RefereeVerdict:
    accept: bool
    battery_accept: bool
    mutation_score: float
    mutation_validated: bool
    debate: DebateVerdict
    reason: str = ""


def _check_summary(sc) -> str:
    """A fair pass/fail digest of the independent checks for the debate (no hidden test)."""
    lines = [f"discriminating checks passed: {sc.n_discrim_passed}/{sc.n_discrim_surviving} "
             f"(weighted {sc.disc_frac:.2f}); guard checks kept: {sc.n_guard_passed}/{sc.n_guard_surviving} "
             f"(weighted {sc.guard_frac:.2f}); public test passes: {sc.public_pass}; "
             f"adversarial-high: {sc.adversarial_high}"]
    lines.append(sc.feedback())
    return "\n".join(lines)


def referee(battery: RepairBattery, candidate_src: str, *, workspace_root: Path, candidate_id: str,
            diff: str | None, client, spec=None, mutation_floor: float = 0.5,
            min_disc: int = 2, debate_model: str = "claude-haiku-4-5") -> RefereeVerdict:
    """Composite accept/abstain gate. `spec` (issue_text/public_test/module_path) feeds the debate."""
    sc = score_candidate(battery, candidate_src=candidate_src, workspace_root=workspace_root,
                         candidate_id=candidate_id, diff=diff)
    battery_accept = sc.accept()
    mscore = float(battery.mutation_info.get("mutation_score", 0.0) or 0.0)
    mutation_validated = battery.valid and battery.n_discriminating >= min_disc and mscore >= mutation_floor

    # Only spend the debate when the cheaper gates already agree the patch looks correct — debate then
    # serves to CONFIRM (catch overfit / overrule a stray wrong check), not to rescue a failing battery.
    if not (battery_accept and mutation_validated):
        why = ("battery rejected" if not battery_accept else
               f"weak battery (mutation_score {mscore:.2f} < {mutation_floor} or disc {battery.n_discriminating} < {min_disc})")
        return RefereeVerdict(accept=False, battery_accept=battery_accept, mutation_score=mscore,
                              mutation_validated=mutation_validated,
                              debate=DebateVerdict(False, 0.0, "not reached"), reason=f"abstain: {why}")

    dv = debate_verdict(spec, candidate_src, client=client, check_summary=_check_summary(sc),
                        diff=diff, model=debate_model)
    accept = battery_accept and mutation_validated and dv.accept
    return RefereeVerdict(accept=accept, battery_accept=battery_accept, mutation_score=mscore,
                          mutation_validated=mutation_validated, debate=dv,
                          reason=("accepted" if accept else f"debate rejected: {dv.critic_counterexample[:120] or dv.rationale[:120]}"))
