# ruff: noqa: E501
"""SkillBank A/B (Plan A) — does a family playbook distilled from OTHER bundles lift the cheap rung?

Leave-one-out on the more-itertools family (the 8 hard bundles of one codebase):
  1. CONTROL: run repair2 on each bundle with NO skill doc, recording the attempt trace
     (solved?, failure summary, capped attempt diff). Contemporaneous control — same code, same model.
  2. DISTILL (LOO): for each held-out bundle, ONE cheap gemini call turns the OTHER bundles' traces
     into a <=6-bullet family playbook (never sees the held-out bundle or any gold patch).
  3. TREATMENT: run repair2 on the held-out bundle WITH the playbook injected.

Honest design notes: distillation input is only OUR OWN attempt traces on sibling bundles (no gold,
no hidden-test leakage across bundles — the family's tests are public knowledge to an agent working
the repo). n=8 -> directional, not definitive; report per-bundle flips both ways. Resumable: persists
after every phase-step.

    uv run python -m evals.issue_replay.skill_bank_eval --out reports/issue_replay_skill_bank_ab.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from evals.issue_replay.repair_harness import _llm
from evals.issue_replay.repair_v2 import _diff_cap, repair_v2
from evals.issue_replay.replay_runner import verify
from evals.issue_replay.replay_task import IssueReplayTask
from evals.issue_replay.run import _MODELS

FAMILY = "more-itertools/more-itertools"

_DISTILL = (
    "You maintain a terse engineering playbook for fixing bugs in the `more_itertools` codebase. "
    "Below are traces of past fix attempts in this repo (issue, whether our patch passed the test "
    "suite, the failure mode if not, and the attempted diff). Distill <=6 SHORT imperative bullets "
    "of repo-specific lessons that would help the NEXT bug fix here (conventions, test expectations, "
    "API invariants, common mistakes to avoid). No generic advice ('write tests'); only what these "
    "traces actually support. Output ONLY the bullets, one per line, starting with '- '.\n\nTRACES:\n{traces}"
)


def _trace(b: IssueReplayTask, solved: bool, produced: str) -> str:
    d = _diff_cap(b.buggy, produced, cap=18) or "(no change)"
    return (f"ISSUE: {b.issue_title}\nOUTCOME: {'PASSED the suite' if solved else 'FAILED the suite'}\n"
            f"ATTEMPTED DIFF:\n{d}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/issue_replay_skill_bank_ab.json")
    args = ap.parse_args()
    out = Path(args.out)
    model_id, rate = _MODELS["gemini"]
    bundles = [IssueReplayTask(**d) for d in json.loads(Path("reports/real_issue_replay_full_hard.json").read_text())]
    fam = [(i, b) for i, b in enumerate(bundles) if b.repo_name == FAMILY]
    state: dict = {"experiment": "issue_replay_skill_bank_ab", "family": FAMILY,
                   "n_bundles": len(fam), "control": {}, "playbooks": {}, "treatment": {},
                   "cost_usd": 0.0}
    if out.exists():
        try:
            prior = json.loads(out.read_text())
            if prior.get("experiment") == state["experiment"]:
                state = prior
        except json.JSONDecodeError:
            pass

    def persist() -> None:
        out.write_text(json.dumps(state, indent=2) + "\n")

    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="skill_ab_") as d:
        root = Path(d)
        # 1) CONTROL + traces
        traces: dict[str, str] = state.setdefault("traces", {})
        for i, b in fam:
            key = str(i)
            if key in state["control"]:
                continue
            produced, cost, _ = repair_v2(b, root / f"c{i}", model_id=model_id, rate=rate)
            hidden, _pub = verify(b, root / f"vc{i}", module_src=produced)
            state["control"][key] = bool(hidden)
            state["cost_usd"] += cost
            traces[key] = _trace(b, hidden, produced)
            print(f"[control #{i}] solved={hidden} ({round(time.time()-t0)}s)", flush=True)
            persist()
        # 2) LOO DISTILL
        for i, _b in fam:
            key = str(i)
            if key in state["playbooks"]:
                continue
            other = "\n---\n".join(t for k, t in traces.items() if k != key)
            try:
                text, it, ot = _llm(model_id, _DISTILL.format(traces=other[:14000]), temperature=0.2)
                state["cost_usd"] += it * rate[0] + ot * rate[1]
            except Exception:  # noqa: BLE001
                text = ""
            bullets = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- ")][:6]
            state["playbooks"][key] = bullets
            print(f"[distill #{i}] {len(bullets)} bullets", flush=True)
            persist()
        # 3) TREATMENT
        for i, b in fam:
            key = str(i)
            if key in state["treatment"]:
                continue
            bullets = state["playbooks"].get(key) or []
            skill = ("FAMILY PLAYBOOK (more-itertools) — lessons from prior fixes in this codebase:\n"
                     + "\n".join(bullets)) if bullets else ""
            produced, cost, _ = repair_v2(b, root / f"t{i}", model_id=model_id, rate=rate, skill=skill)
            hidden, _pub = verify(b, root / f"vt{i}", module_src=produced)
            state["treatment"][key] = bool(hidden)
            state["cost_usd"] += cost
            print(f"[treatment #{i}] solved={hidden} (control={state['control'][key]})", flush=True)
            persist()

    ctrl = sum(state["control"].values())
    treat = sum(state["treatment"].values())
    flips_up = [k for k in state["control"] if not state["control"][k] and state["treatment"].get(k)]
    flips_down = [k for k in state["control"] if state["control"][k] and not state["treatment"].get(k)]
    state["summary"] = {
        "control_solved": ctrl, "treatment_solved": treat, "n": len(fam),
        "flipped_up": flips_up, "flipped_down": flips_down,
        "verdict": ("playbook LIFTS the cheap rung" if treat > ctrl else
                    "playbook HURTS" if treat < ctrl else "no net effect at this n"),
        "honest_scope": "n=8, one family, single run per arm -> directional only; flips both ways reported",
    }
    state["elapsed_s"] = round(time.time() - t0, 1)
    persist()
    print(f"\n=== SKILL-BANK A/B === control {ctrl}/{len(fam)} -> treatment {treat}/{len(fam)} "
          f"(up={flips_up} down={flips_down})  ${state['cost_usd']:.3f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
