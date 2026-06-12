# ruff: noqa: E501
"""P8 W1 go/no-go probe — does LLM-proposed property + Hypothesis input-search discriminate the bug?

Cheap (~$0.30, NO repair calls): on the diagnostic bundles, generate Hypothesis properties, admit those
the BUGGY baseline falsifies (proven to exercise the bug), then measure how many of those the GOLD fix
PASSES (a real discriminating signal: buggy fails, gold holds). Reports how many previously
example-NON-discriminating bundles are rescued.

PROCEED to the full W1 build iff >= 3 of the (~7) example-non-discriminating bundles gain a
gold-passing discriminating property; else stop W1 and pivot to W2 routing-only.

    uv run python -m evals.issue_replay.pbt_probe --out reports/issue_replay_p8_probe.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from evals.issue_replay.guided_repair import _Spec
from evals.issue_replay.guided_repair_phase0 import _client, _select_targets
from evals.issue_replay.repair_harness import _extract, _func_table, _localize
from evals.issue_replay.replay_task import IssueReplayTask

from acp.verification.property_checks import (
    admit_discriminating,
    behavior_trace,
    generate_properties,
)
from acp.verification.repair_battery import _run_check_kinds


def _example_nondiscriminating(g1_path: str) -> dict[tuple[str, str], bool]:
    """Map (module, issue) -> True if the example-test battery was non-discriminating there (invalid
    or gold not accepted) per the latest G1 report — the bundles PBT must rescue."""
    out: dict[tuple[str, str], bool] = {}
    p = Path(g1_path)
    if not p.exists():
        return out
    for r in json.loads(p.read_text()).get("per_bundle", []):
        nondisc = (not r.get("battery_valid")) or (not r.get("gold_accept"))
        out[(r["module"], r["issue"])] = bool(nondisc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="reports/real_issue_replay_full_v2.json")
    ap.add_argument("--diagnosis", default="reports/issue_replay_diagnosis.json")
    ap.add_argument("--g1", default="reports/issue_replay_p7_g1.json")
    ap.add_argument("--out", default="reports/issue_replay_p8_probe.json")
    ap.add_argument("--n-prop", type=int, default=6)
    ap.add_argument("--grounded", action="store_true",
                    help="execution-grounded generation: feed the buggy code's observed behaviour")
    args = ap.parse_args()

    bundles = [IssueReplayTask(**d) for d in json.loads(Path(args.corpus).read_text())]
    targets = _select_targets(bundles, json.loads(Path(args.diagnosis).read_text())["rows"])
    nondisc = _example_nondiscriminating(args.g1)
    client = _client()

    per_bundle: list = []
    done: set = set()
    if Path(args.out).exists():
        try:
            per_bundle = json.loads(Path(args.out).read_text()).get("per_bundle", [])
            done = {(r["module"], r["issue"]) for r in per_bundle}
            print(f"resume: {len(done)} bundles done", flush=True)
        except Exception:  # noqa: BLE001
            per_bundle, done = [], set()

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for bi, (cat, b) in enumerate(targets):
            key = (Path(b.module_path).name, b.issue_title[:50])
            if key in done:
                continue
            spec = _Spec(f"{b.issue_title}\n{b.issue_body}", b.public_test, b.module_path)
            tbl = _func_table(b.buggy)
            fn = _localize(b.buggy, b.issue_title, b.public_test, "")
            focus = _extract(b.buggy, fn, tbl) if fn else b.buggy[:6000]
            trace = (behavior_trace(b.buggy, fn, b.public_test, module_path=b.module_path,
                                    extra_files=b.extra_files, root=root / f"tr{bi}") if args.grounded else "")
            props, cost = generate_properties(spec, client=client, n_prop=args.n_prop, focus=focus, trace=trace)
            disc, guard = admit_discriminating(props, baseline_src=b.buggy, module_path=b.module_path,
                                               extra_files=b.extra_files, root=root / f"adm{bi}")
            # of the buggy-falsified properties, how many does GOLD satisfy? (valid discriminating)
            gold_pass = 0
            if disc:
                kinds = _run_check_kinds(b.gold_patch, disc, module_path=b.module_path,
                                         extra_files=b.extra_files, root=root / f"gold{bi}", tag="gold")
                gold_pass = sum(1 for k in kinds if k == "pass")
            rescued = gold_pass >= 1
            row = {"category": cat, "module": key[0], "issue": key[1],
                   "example_nondiscriminating": nondisc.get(key),
                   "n_props_generated": len(props), "n_admitted_discriminating": len(disc),
                   "n_guard": len(guard), "gold_passing_discriminating": gold_pass,
                   "pbt_rescued": rescued, "gen_cost_usd": round(cost, 6)}
            per_bundle.append(row)
            print(f"[{len(per_bundle)}/{len(targets)}] {cat:11} {key[0]:14} props={len(props)} "
                  f"disc(buggy-fails)={len(disc)} gold-passes={gold_pass} rescued={rescued} "
                  f"ex_nondisc={nondisc.get(key)}", flush=True)
            _persist(args.out, per_bundle)

    _summary(per_bundle)
    return 0


def _summary(per_bundle: list) -> dict:
    target_set = [r for r in per_bundle if r.get("example_nondiscriminating")]
    rescued = [r for r in target_set if r["pbt_rescued"]]
    any_rescue = [r for r in per_bundle if r["pbt_rescued"]]
    s = {"n_example_nondiscriminating": len(target_set),
         "rescued_of_nondiscriminating": len(rescued),
         "total_with_gold_passing_discriminating": len(any_rescue),
         "gate_threshold": "rescued_of_nondiscriminating >= 3",
         "gate_pass": len(rescued) >= 3,
         "total_gen_cost_usd": round(sum(r["gen_cost_usd"] for r in per_bundle), 4)}
    print(f"\n=== PBT PROBE === rescued {s['rescued_of_nondiscriminating']}/{s['n_example_nondiscriminating']} "
          f"example-nondiscriminating | total gold-passing-disc {s['total_with_gold_passing_discriminating']}/"
          f"{len(per_bundle)} | GATE {'PASS -> build W1' if s['gate_pass'] else 'FAIL -> pivot to W2'} "
          f"| ${s['total_gen_cost_usd']}", flush=True)
    return s


def _persist(out: str, per_bundle: list) -> None:
    Path(out).write_text(json.dumps(
        {"experiment": "issue_replay_p8_pbt_probe", "n_done": len(per_bundle),
         "summary": _summary_quiet(per_bundle), "per_bundle": per_bundle}, indent=2) + "\n")


def _summary_quiet(per_bundle: list) -> dict:
    target_set = [r for r in per_bundle if r.get("example_nondiscriminating")]
    rescued = [r for r in target_set if r["pbt_rescued"]]
    return {"n_example_nondiscriminating": len(target_set),
            "rescued_of_nondiscriminating": len(rescued),
            "gate_pass": len(rescued) >= 3,
            "total_gen_cost_usd": round(sum(r["gen_cost_usd"] for r in per_bundle), 4)}


if __name__ == "__main__":
    raise SystemExit(main())
