# ruff: noqa: E501
"""Verifier-guided multi-sampling on a strong agent (#1 — the capability-ceiling experiment).

The research is unusually consistent (committee-boosting 2605.14163, VerMCTS 2402.08147, SMC
2504.13139): coverage scales with the number of independent samples when a sound verifier selects
among them. We already showed best-of-POOL = the union; this asks the sharper question — does
best-of-N on a SINGLE strong agent crack the bundles a single attempt misses, including the
universal-miss bundle (#8 "concurrent tee") that defeated the whole pool in P4?

Mechanism: run the stateful CLI agent N independent times on the same bundle (each run is stochastic),
verify each produced module against the pristine held-out test, and accept the bundle if ANY sample
passes (verifier-select). Report best-of-k coverage for k=1..N and the samples-to-first-success.

    uv run python -m evals.issue_replay.multisample --agent codex_cli --n 3 \
        --bundle-file reports/real_issue_replay_full_hard.json --limit 10 --out reports/issue_replay_multisample_codex_hard.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from evals.issue_replay.replay_runner import verify
from evals.issue_replay.replay_task import IssueReplayTask
from evals.issue_replay.run import _produce_vendor


def run_multisample(bundles: list[IssueReplayTask], agent: str, n: int, *, out: Path | None = None,
                    offset: int = 0, vendor_timeout: int = 300) -> dict:
    t0 = time.time()
    by_idx: dict[int, dict] = {}
    if out is not None and out.exists():     # RESUME: reload prior samples so windows accumulate
        try:
            prior = json.loads(out.read_text()).get("per_bundle", [])
            by_idx = {r.get("idx", i): {**r, "idx": r.get("idx", i)} for i, r in enumerate(prior)}
            print(f"resume: loaded {len(by_idx)} prior bundle records", flush=True)
        except (json.JSONDecodeError, KeyError):
            by_idx = {}
    with tempfile.TemporaryDirectory(prefix="multisample_") as d:
        root = Path(d)
        for li, b in enumerate(bundles):
            bi = offset + li   # absolute bundle index (stable across --start slices for resume)
            rec = by_idx.get(bi, {"idx": bi, "repo": b.repo_name, "issue": b.issue_title[:70],
                                  "samples": [], "solved": False, "samples_to_success": None})
            # RESUMABLE: a bundle is done once it has a passing sample or N samples already
            if rec["solved"] or len(rec["samples"]) >= n:
                by_idx[bi] = rec
                continue
            while len(rec["samples"]) < n and not rec["solved"]:
                s = len(rec["samples"])
                produced, cost, _ = _produce_vendor(b, agent, root / f"b{bi}_s{s}_{time.time_ns()}", timeout_s=vendor_timeout)
                hidden, _ = verify(b, root / f"v{bi}_s{s}_{time.time_ns()}", module_src=produced)
                rec["samples"].append(int(hidden))
                if hidden:
                    rec["solved"] = True
                    rec["samples_to_success"] = len(rec["samples"])
                print(f"[{b.repo_name} #{bi}] {agent} sample {len(rec['samples'])}/{n} hidden={hidden} "
                      f"({round(time.time() - t0, 0)}s elapsed)", flush=True)
                by_idx[bi] = rec
                if out is not None:   # persist after EVERY sample so a kill mid-bundle keeps progress
                    out.write_text(json.dumps(_summary(by_idx, agent, n, t0), indent=2) + "\n")
            by_idx[bi] = rec
    return _summary(by_idx, agent, n, t0)


def _summary(by_idx: dict[int, dict], agent: str, n: int, t0: float) -> dict:
    per_bundle = [by_idx[i] for i in sorted(by_idx)]
    done = sum(1 for r in per_bundle if r["solved"] or len(r["samples"]) >= n)
    bestofk = {k: sum(1 for r in per_bundle if any(r["samples"][:k])) for k in range(1, n + 1)}
    return {
        "experiment": "issue_replay_multisample", "agent": agent, "n_samples": n,
        "question": "does best-of-N on a single strong agent crack what single-shot misses (coverage scaling)?",
        "completed": done, "best_of_k_solved": bestofk,
        "single_shot_solved": bestofk.get(1, 0), "best_of_n_solved": bestofk.get(n, 0),
        "elapsed_s": round(time.time() - t0, 1),
        "evidence_tier": "live; N independent stateful-agent runs; pristine held-out test selects; agent cannot edit the oracle",
        "per_bundle": per_bundle,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="codex_cli", choices=["codex_cli", "claude_code", "gemini_cli"])
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--bundle-file", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", type=int, default=0, help="absolute bundle index to start at (resume-safe)")
    ap.add_argument("--vendor-timeout", type=int, default=300, help="per-sample agent time budget (s)")
    ap.add_argument("--out", default="reports/issue_replay_multisample.json")
    args = ap.parse_args()
    bundles = [IssueReplayTask(**d) for d in json.loads(Path(args.bundle_file).read_text())]
    end = args.limit or len(bundles)
    bundles = bundles[args.start:end]
    rep = run_multisample(bundles, args.agent, args.n, out=Path(args.out), offset=args.start, vendor_timeout=args.vendor_timeout)
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== MULTISAMPLE {args.agent} N={args.n} === single-shot {rep['single_shot_solved']} "
          f"-> best-of-{args.n} {rep['best_of_n_solved']} / {rep['completed']}  curve {rep['best_of_k_solved']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
