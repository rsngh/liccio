"""End-to-end live autonomous self-improvement cycle (Round 19) — the capstone.

Runs the FULL governed loop against a real (weakened, for headroom) openai_harness:
build a per-scope job with a LIVE held-out scorer, run the guardrailed skill-improvement
cycle (optimize -> held-out gate -> governed deploy -> record), and emit the cycle report
+ dashboard snapshot. If the verify-skill improves the weak harness on held-out, it is
deployed to ACTIVE and the evolution timeline records it — all live, all governed.

Usage: set OPENAI_API_KEY, then run with `uv run python`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_live_bakeoff as B  # noqa: E402
from run_skillopt_live import _run_task_with_skill  # noqa: E402

import acp.db.models  # noqa: E402,F401
from acp.db.repositories import EntityStore  # noqa: E402
from acp.db.session import (  # noqa: E402
    create_all,
    make_engine,
    make_session_factory,
    session_scope,
)
from acp.observability.live_report import redact_report  # noqa: E402
from acp.schemas.skill import SkillDocument, SkillScope  # noqa: E402
from acp.training.skill_edit import SkillEdit  # noqa: E402
from acp.training.skill_improvement import (  # noqa: E402
    SkillScopeJob,
    run_skill_improvement_cycle,
    skill_dashboard,
)
from acp.training.skillopt_backend import get_backend  # noqa: E402

HELD_OUT_IDS = ["testgen_stats", "feature_lru_cache", "bugfix_fib", "security_eval"]
VERIFY = "- After editing, ALWAYS run the project's tests and fix failures before finishing."


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("[skip] OPENAI_API_KEY unset")
        return 0
    from acp.agents.openai_harness import OpenAIHarnessAdapter
    adapter = OpenAIHarnessAdapter(max_steps=3, max_nudges=0)
    spec_by_id = {s["id"]: s for s in B.TASKS if s["id"] in HELD_OUT_IDS}

    # Trusted conclusive evidence cells (one per held-out spec); build_skill_dataset
    # splits them into train/held-out; the live scorer runs the held tasks.
    cells = [{"task": sid, "task_type": spec_by_id[sid]["task_type"],
              "adapter": "openai_harness", "is_harness": True, "success": True,
              "status": "succeeded", "tool_calls": 2, "commands": 1, "file_reads": 1}
             for sid in spec_by_id]

    def scorer(skill_content, held):
        if not held:
            return 0.0
        solved = 0
        for t in held:
            spec = spec_by_id.get(t.task_id)
            if spec is None:
                continue
            with tempfile.TemporaryDirectory() as d:
                if _run_task_with_skill(adapter, spec, skill_content, Path(d)):
                    solved += 1
        return round(solved / len(held), 4)

    def proposer(train, current):
        return [] if VERIFY in current else [SkillEdit("append", content=VERIFY)]

    base = SkillDocument(name="bugfix-verify", content="# Coding skill\n",
                         scope=SkillScope(task_type="bugfix", harness="openai_harness"))
    job = SkillScopeJob(base=base, cells=cells, scorer=scorer, proposer=proposer)

    engine = make_engine("sqlite:////tmp/autonomous_cycle.db")
    create_all(engine)
    sf = make_session_factory(engine)
    with session_scope(sf) as s:
        report = run_skill_improvement_cycle(
            EntityStore(s), [job], cycle_id="live-cycle-1",
            backend=get_backend("microsoft_skillopt"), max_steps=3)
    with session_scope(sf) as s:
        dash = skill_dashboard(EntityStore(s))

    out_report = {
        "experiment": "round19_autonomous_cycle_live",
        "cycle": {"n_scopes": report.n_scopes, "n_deployed": report.n_deployed,
                  "n_no_op": report.n_no_op,
                  "n_skipped_contaminated": report.n_skipped_contaminated,
                  "events": report.events},
        "dashboard": dash,
    }
    out = Path("reports/live/autonomous_cycle.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(out_report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"autonomous cycle: deployed={report.n_deployed} no_op={report.n_no_op} "
          f"active_skills={dash['n_active_skills']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
