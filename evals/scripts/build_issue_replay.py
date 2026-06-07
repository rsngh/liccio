"""Validate + summarize frozen issue-replay bundles (GOALS Alpha 44 P1).

Deterministic: checks every frozen bundle is offline-fair (buggy fails hidden, gold passes
public + hidden) and that the patch-equivalence judge agrees gold==gold, then writes
reports/issue_replay_bundles.json. Clearly labels the evidence tier (frozen_synthetic).
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.issue_replay.replay_runner import offline_fairness  # noqa: E402
from evals.issue_replay.replay_task import frozen_bundles  # noqa: E402


def main() -> int:
    bundles = frozen_bundles()
    rows = []
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for b in bundles:
            fair = offline_fairness(b, root)
            rows.append({"repo": b.repo_name, "module": b.module_path, "task_type": b.task_type,
                         "context_need": b.context_need, "source": b.source,
                         "gold_patch_hash": b.gold_patch_hash, **fair})
    report = {
        "experiment": "issue_replay_bundles",
        "n_bundles": len(bundles),
        "evidence_tier": "frozen_synthetic (network-free; not scraped real_issue_replay)",
        "all_offline_fair": all(r["fair"] for r in rows),
        "by_source": dict(Counter(b.source for b in bundles)),
        "by_task_type": dict(Counter(b.task_type for b in bundles)),
        "gold_patch_withheld_from_agent": True,
        "bundles": rows,
        "note": ("framework supports online_ingest/offline_freeze/replay_only; online ingest is a "
                 "network-gated stub here, so bundles are synthetic-realistic and labeled."),
    }
    out = ROOT / "reports" / "issue_replay_bundles.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"bundles={len(bundles)} all_fair={report['all_offline_fair']} "
          f"by_type={report['by_task_type']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
