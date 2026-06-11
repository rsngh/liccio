# ruff: noqa: E501
"""Verifier-guided repair — climb the dense battery gradient instead of guessing at a binary oracle.

Same localize -> propose -> splice machinery as repair_v2, but two principled changes:
  1. The in-loop accept signal is the FAIR, CONTINUOUS `repair_battery` score (spec + public test +
     buggy baseline), never `task.hidden_test`. The hidden test is reserved strictly for grading by
     the caller (`replay_runner.verify`). This both fixes the privilege leak in repair_harness/repair_v2
     and gives the search a gradient to climb.
  2. Each proposal is conditioned on the battery's STRUCTURED feedback (which discriminating checks are
     still failing, which guard checks regressed), not just a single test's traceback.

`search_mode`:
  * "greedy" (Phase 0): repair_v2's best-of-k loop, ranking candidates by battery score and seeding the
    next round with the best candidate's feedback. The minimal test of "does a dense fair signal carry a
    climbable gradient a binary oracle does not".
  * "beam" / "mcts" (Phase 1/2): added on top of the same Node/value/expansion primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from evals.issue_replay.repair_harness import (
    _extract,
    _first_block,
    _func_table,
    _llm,
    _localize,
    _parse_funcs,
    _splice,
)
from evals.issue_replay.repair_v2 import (
    _CRITIC,
    _PROMPT,
    _ast_hash,
    _diff_cap,
    module_skeleton,
    sibling_signatures,
)
from evals.issue_replay.replay_task import IssueReplayTask

from acp.verification.repair_battery import (
    RepairBattery,
    build_battery,
    score_candidate,
)


@dataclass
class _Spec:
    issue_text: str
    public_test: str
    module_path: str


@dataclass
class GuidedResult:
    module_src: str
    cost_usd: float
    ran: bool
    telemetry: dict = field(default_factory=dict)


def _instr(whole: bool) -> str:
    return ("Return ONLY the full corrected module in a ```python code block." if whole else
            "Return ONLY the corrected full definition(s) of the function(s) shown, in a ```python "
            "code block — same names, same signatures, nothing else.")


def guided_repair(task: IssueReplayTask, root: Path, *, model_id: str, rate: tuple[float, float],
                  client, search_mode: str = "greedy", k: int = 3, rounds: int = 3,
                  n_example: int = 8, n_property: int = 4, skill: str = "",
                  battery: RepairBattery | None = None,
                  record_candidates: bool = False) -> GuidedResult:
    """Greedy verifier-guided repair. Returns the best-scoring candidate module (graded by the caller).

    NEVER reads task.hidden_test. Localization + the in-loop oracle use only the public test + spec +
    buggy baseline (the battery)."""
    root.mkdir(parents=True, exist_ok=True)
    bench = root / "battery_ws"
    bench.mkdir(parents=True, exist_ok=True)

    spec = _Spec(issue_text=f"{task.issue_title}\n{task.issue_body}", public_test=task.public_test,
                 module_path=task.module_path)
    if battery is None:
        battery = build_battery(spec, client=client, module_path=task.module_path,
                                extra_files=task.extra_files, baseline_src=task.buggy,
                                public_test=task.public_test, workspace_root=bench,
                                n_example=n_example, n_property=n_property)

    current = task.buggy
    table = _func_table(current)
    # FAIR localization: use the public (failing) test, never the hidden test.
    focus_names = _localize(current, task.issue_title, task.public_test, "")
    whole = not focus_names
    focus = _extract(current, focus_names, table) if focus_names else current[:14000]
    skeleton = module_skeleton(current) or "(unavailable)"
    sibs = sibling_signatures(task.extra_files)
    sib_block = f"SIBLING MODULES (callable API):\n{sibs}\n\n" if sibs else ""
    instr = _instr(whole)

    base_score = score_candidate(battery, candidate_src=current, workspace_root=bench, candidate_id="base")
    best_cand, best_score = current, base_score
    cost = battery.gen_cost_usd
    ran = False
    diagnosis = ""
    failed_patches: list[str] = []
    seen = {_ast_hash(current)}
    trajectory = [base_score.score]
    n_expansions = 0
    scored: list[dict] = []   # (score, proxy_pass, src) per candidate — for value-function quality eval

    for rnd in range(rounds):
        feedback = best_score.feedback()
        diag_block = f"REVIEWER DIAGNOSIS (address this directly):\n{diagnosis}\n\n" if diagnosis else ""
        failed_block = ("PATCHES THAT ALREADY FAILED — do NOT repeat these approaches:\n"
                        + "\n---\n".join(failed_patches[-3:]) + "\n") if failed_patches else ""
        prompt = (skill + "\n\n" if skill else "") + _PROMPT.format(
            instr=instr, issue=spec.issue_text, skeleton=skeleton, siblings=sib_block, focus=focus,
            failure=feedback, diagnosis=diag_block, failed=failed_block)
        temps = [0.0, 0.7, 1.0] if rnd == 0 else [0.4, 0.8, 1.0]
        round_best_diff = ""
        for i in range(k):
            try:
                text, it, ot = _llm(model_id, prompt, temperature=temps[min(i, len(temps) - 1)])
            except Exception:  # noqa: BLE001 - provider hiccup: skip the sample
                continue
            ran = True
            cost += it * rate[0] + ot * rate[1]
            cand = (_first_block(text) or current) if whole else (
                _splice(current, table, _parse_funcs(text)) if _parse_funcs(text) else current)
            h = _ast_hash(cand)
            if not h or h in seen:                 # early prune: unparseable or already-tried
                continue
            seen.add(h)
            n_expansions += 1
            sc = score_candidate(battery, candidate_src=cand, workspace_root=bench,
                                 candidate_id=f"r{rnd}s{i}", diff=_diff_cap(task.buggy, cand))
            if record_candidates:
                scored.append({"score": round(sc.score, 4), "proxy_pass": sc.proxy_pass, "src": cand})
            if sc.score > best_score.score:
                best_cand, best_score = cand, sc
                round_best_diff = _diff_cap(task.buggy, cand)
            if sc.score < 1.0:                     # a not-yet-perfect candidate is a "failed" approach
                failed_patches.append(_diff_cap(task.buggy, cand) or "(no-op patch)")
        trajectory.append(best_score.score)
        if best_score.proxy_pass:                  # battery fully satisfied -> stop early (fair stop)
            break
        # critic round (reuse repair_v2._CRITIC) keyed to the best candidate's battery feedback
        if rnd < rounds - 1 and round_best_diff:
            try:
                diagnosis, it, ot = _llm(model_id, _CRITIC.format(
                    issue=task.issue_title, focus=focus, diff=round_best_diff, failure=best_score.feedback()),
                    temperature=0.2)
                cost += it * rate[0] + ot * rate[1]
            except Exception:  # noqa: BLE001
                diagnosis = ""

    telemetry = {
        "search_mode": search_mode, "focus_names": focus_names, "whole_module": whole,
        "n_checks": len(battery.checks), "n_discriminating": battery.n_discriminating,
        "n_guard": battery.n_guard, "n_expansions": n_expansions,
        "best_score": round(best_score.score, 4), "best_proxy_pass": best_score.proxy_pass,
        "score_trajectory": [round(s, 4) for s in trajectory],
        "gen_cost_usd": round(battery.gen_cost_usd, 6),
    }
    if record_candidates:
        telemetry["candidates"] = scored
    return GuidedResult(module_src=best_cand, cost_usd=round(cost, 6), ran=ran, telemetry=telemetry)
