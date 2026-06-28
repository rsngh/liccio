# ruff: noqa: E501
"""Repo-level FAIR referee for multi-file SWE-bench (P12 W4) — extend the trustworthy verify-stop
beyond single-module repair to the real benchmark.

The single-module auto-referee (battery + mutation + debate) doesn't apply to SWE-bench: the candidate
is a multi-file unified diff on a real repo, not one module with a synthesized battery. So the
de-saturated routing win (P9: pool union beats best-single) is only proven under an ORACLE stop. This
builds a repo-level fair verifier that decides commit/escalate from FAIR signals ONLY — the held-out
FAIL_TO_PASS is the GRADER, never an input to the decision:

  1. REGRESSION GUARD (differential, fair): discover the repo's OWN existing tests that touch the
     changed files (present at base_commit, NOT the held-out test_patch). Record which pass at base,
     apply the candidate, re-run: the guard fails iff any test that PASSED at base now fails (the
     candidate introduced a regression). New-failure-only — a test already broken at base is not the
     candidate's fault.
  2. REPRODUCTION (fair, when admissible): swebench_verify_stop.generate_repro writes a repro from the
     problem_statement only; admit it iff it FAILS on base (proven to reproduce); require it to PASS on
     the candidate. Skipped when no repro is admissible (then the decision rests on guard + debate).
  3. DIFF-DEBATE: debate.debate_verdict (proposer/critic/judge) on the unified diff.

Accept iff regression_ok AND (repro_pass when a repro is admissible, else debate_accept): the regression
guard is the hard fail-closed gate; an admissible fails-on-buggy reproduction test is the PRIMARY required
correctness signal (far stronger than diff-debate, which alone commits P2P-breakers); debate is the
FALLBACK only when no repro is admissible. The guard confirms regressions are deterministic (stable double base-run + re-confirm) to avoid flaky false-
positives. Graded by the FULL held-out criterion (FAIL_TO_PASS passes AND PASS_TO_PASS kept = SWE-bench
solved): FALSE-COMMIT = accepted but not fully solved (incl. a committed diff that breaks PASS_TO_PASS);
MISSED = not accepted but actually solved. Reuses swebench_adapter / swebench_solve / swebench_verify_stop / debate.

    uv run python -m evals.issue_replay.swebench_referee --slice reports/swebench_lite_slice_pinned.json \
        --diffs reports/swebench_solve_gemini_cli.json --out reports/swebench_referee_eval.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from evals.issue_replay.swebench_adapter import (
    SweInstance,
    _sh,
    _venv_env,
    load_lite,
    prepare,
    verify,
)
from evals.issue_replay.swebench_verify_stop import (
    _client,
    admit_repro,
    generate_repro,
    verify_stop,
)


@dataclass
class RefereeDecision:
    accept: bool
    regression_ok: bool
    repro_admissible: bool
    repro_pass: bool
    debate_accept: bool
    reason: str = ""
    n_repro_admitted: int = 0
    guard_tests_run: int = 0


def changed_files(diff: str) -> list[str]:
    """Source files the candidate diff touches (b-side paths), excluding test files."""
    out: list[str] = []
    for line in diff.splitlines():
        m = re.match(r"\+\+\+ b/(.+)", line)
        if m:
            p = m.group(1).strip()
            if p and p != "/dev/null" and not _is_test_path(p):
                out.append(p)
    return out


def _is_test_path(p: str) -> bool:
    base = p.split("/")[-1]
    return ("/tests/" in p or "/test/" in p or base.startswith("test_")
            or base.endswith("_test.py"))


def _changed_modules(files: list[str]) -> set[str]:
    """Importable module stems of the changed files (e.g. src/pkg/util.py -> {util, pkg})."""
    mods: set[str] = set()
    for f in files:
        if not f.endswith(".py"):
            continue
        parts = f[:-3].split("/")
        mods.add(parts[-1])
        # the package directory name is a strong import-association signal
        for seg in parts[:-1]:
            if seg not in ("src", "lib", ""):
                mods.add(seg)
    return {m for m in mods if m and m != "__init__"}


def _discover_guard_tests(repo: Path, mods: set[str], *, cap: int = 6) -> list[str]:
    """Existing test files (at base) that reference any changed module — the fair regression set.
    Bounded to `cap` files for runtime; prefers tests that name more changed modules."""
    if not mods:
        return []
    scored: list[tuple[int, str]] = []
    for tf in repo.rglob("test_*.py"):
        rel = tf.relative_to(repo).as_posix()
        if not _is_test_path(rel):
            continue
        try:
            txt = tf.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        hits = sum(1 for m in mods if re.search(rf"\b{re.escape(m)}\b", txt))
        if hits:
            scored.append((hits, rel))
    scored.sort(reverse=True)
    return [rel for _h, rel in scored[:cap]]


def _per_test_outcomes(repo: Path, py: str, test_files: list[str], *, timeout: int = 240) -> dict[str, str] | None:
    """Run the test subset and return {nodeid: PASSED|FAILED|ERROR}. None if pytest can't run at all
    (so the guard fails open to ABSTAIN rather than risk a false-commit/false-regression)."""
    if not test_files:
        return {}
    env = _venv_env(Path(py).parent.parent)
    try:
        import subprocess
        # -v prints one "nodeid PASSED|FAILED|ERROR" line per test (quiet mode only prints dots,
        # which carry no per-test outcome to diff base-vs-candidate against).
        # --continue-on-collection-errors: a single unimportable test file (missing dev-only dep, e.g.
        # GitPython/attrs not in the prepared venv) otherwise ABORTS the whole session -> no outcomes ->
        # the guard fail-closes on the entire repo. With the flag, collectable tests still run; the
        # uncollectable file reports ERROR (never in base_pass, so never counted as a regression).
        p = subprocess.run([py, "-m", "pytest", "-p", "no:cacheprovider", "--tb=no", "-v",
                            "--no-header", "--continue-on-collection-errors", *test_files],
                           cwd=repo, capture_output=True, text=True, timeout=timeout, env=env)
    except Exception:  # noqa: BLE001
        return None
    text = p.stdout + "\n" + p.stderr
    if "INTERNALERROR" in text or "no tests ran" in text and "passed" not in text:
        return None
    outcomes: dict[str, str] = {}
    for m in re.finditer(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR)", text, re.MULTILINE):
        outcomes[m.group(1)] = m.group(2)
    if not outcomes:
        # fall back to the summary verb form "PASSED path::test" (older pytest -v formats)
        for m in re.finditer(r"^(PASSED|FAILED|ERROR)\s+(\S+::\S+)", text, re.MULTILINE):
            outcomes[m.group(2)] = m.group(1)
    return outcomes or None


def regression_guard(inst: SweInstance, candidate_diff: str, *, agent_tag: str = "referee") -> tuple[bool, int]:
    """Differential fair guard: no test that PASSED at base may FAIL on the candidate. Returns
    (guard_ok, n_tests_considered). Fail-CLOSED (guard_ok False) when the base test set can't be run —
    the referee then abstains rather than risk committing a regression it couldn't check."""
    from evals.issue_replay.swebench_solve import _solve_checkout
    files = changed_files(candidate_diff)
    mods = _changed_modules(files)
    co = _solve_checkout(inst, agent_tag)
    if co is None:
        return False, 0
    repo, py = co
    tests = _discover_guard_tests(repo, mods)
    if not tests:
        return True, 0          # nothing to regress against -> guard is vacuously satisfied
    base = _per_test_outcomes(repo, py, tests)
    if base is None:
        return False, 0          # can't establish a baseline -> abstain (fail-closed)
    # STABLE baseline (W4 fix): re-run base and keep only tests that pass BOTH times. Flaky-at-base
    # tests are dropped from the protected set so their noise can't masquerade as a candidate regression.
    base2 = _per_test_outcomes(repo, py, tests)
    base_pass = {nid for nid, v in base.items()
                 if v == "PASSED" and (base2 is None or base2.get(nid) == "PASSED")}
    if not base_pass:
        return True, 0          # no stably-passing test to protect -> vacuously clean
    if not _apply(repo, candidate_diff):
        return False, len(base_pass)
    try:
        cand = _per_test_outcomes(repo, py, tests)
        confirmed_fail: set = set()
        if cand is not None:
            suspected = {nid for nid in base_pass if cand.get(nid) in ("FAILED", "ERROR")}
            if suspected:
                # confirm determinism (W4 fix): re-run ONLY the suspected nodeids; a candidate-flaky
                # test that now passes is dropped, so only reproducible breaks count as regressions.
                confirm = _per_test_outcomes(repo, py, sorted(suspected))
                confirmed_fail = {nid for nid in suspected
                                  if confirm is None or confirm.get(nid) in ("FAILED", "ERROR")}
    finally:
        _sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=repo)
        _sh(["git", "clean", "-qfd", "-e", ".venv"], cwd=repo)
    if cand is None:
        return False, len(base_pass)          # can't re-run on candidate -> fail-closed
    return (not confirmed_fail), len(base_pass)


def _apply(repo: Path, diff: str) -> bool:
    if not diff.strip():
        return True
    (repo / "_cand.patch").write_text(diff)
    rc, _ = _sh(["git", "apply", "_cand.patch"], cwd=repo)
    if rc:
        rc, _ = _sh(["git", "apply", "--3way", "_cand.patch"], cwd=repo)
    return rc == 0


def decide(regression_ok: bool, repro_admissible: bool, repro_pass: bool,
           debate_accept: bool) -> tuple[bool, str]:
    """Pure decision core (unit-tested). Accept iff regression_ok AND (repro_pass when a repro is
    admissible, else debate_accept).

    The regression guard is the hard fail-closed gate. When a FAIR reproduction test is admissible
    (fails on the buggy base), it is the PRIMARY correctness signal and is REQUIRED: a fails-on-buggy /
    passes-on-candidate repro is far stronger evidence than diff-debate, which the W4 pilot showed will
    commit P2P-breakers on its own (v5/v6: debate accepted pytest-11143, which breaks PASS_TO_PASS, while
    the repro correctly withheld it). Debate is the FALLBACK only when no repro is admissible. (Repro is
    trustworthy here only after fixing the extraction corruption that previously made it 0/6.)"""
    if not regression_ok:
        return False, "regression guard: candidate breaks an existing passing test (or unverifiable)"
    if repro_admissible:
        if repro_pass:
            return True, "accept (regression-clean, repro fails-on-buggy/passes-on-candidate)"
        return False, "reproduction test admitted but the candidate does not make it pass"
    if debate_accept:
        return True, "accept (regression-clean, no admissible repro, debate-accept)"
    return False, "no admissible repro and diff-debate rejects"


def referee(inst: SweInstance, candidate_diff: str, *, client, model: str = "claude-haiku-4-5",
            n_repro: int = 3) -> RefereeDecision:
    """Repo-level fair referee. NEVER consults FAIL_TO_PASS. Fail-closed on the guard."""
    reg_ok, n_guard = regression_guard(inst, candidate_diff)
    repros, _c = generate_repro(inst, client=client, n=n_repro)
    admitted = admit_repro(inst, repros) if repros else []
    repro_admissible = bool(admitted)
    repro_pass = verify_stop(inst, candidate_diff, admitted) if repro_admissible else False
    # diff-debate on the unified diff (fair: issue text + the change only)
    from acp.verification.debate import debate_verdict

    class _Spec:
        issue_text = inst.problem_statement
        public_test = ""
    check = (f"regression-guard: {'clean' if reg_ok else 'FAIL/unverifiable'} ({n_guard} base-passing tests); "
             f"reproduction: {'admitted+' + ('pass' if repro_pass else 'FAIL') if repro_admissible else 'none admissible'}")
    dv = debate_verdict(_Spec(), candidate_diff, client=client, check_summary=check,
                        diff=candidate_diff, model=model)
    accept, reason = decide(reg_ok, repro_admissible, repro_pass, dv.accept)
    return RefereeDecision(accept=accept, regression_ok=reg_ok, repro_admissible=repro_admissible,
                           repro_pass=repro_pass, debate_accept=dv.accept, reason=reason,
                           n_repro_admitted=len(admitted), guard_tests_run=n_guard)


def _load_diffs(path: Path) -> dict[str, str]:
    """Map instance_id -> candidate diff from a swebench_solve report."""
    data = json.loads(path.read_text())
    rows = data.get("per_task") or data.get("results") or []
    out: dict[str, str] = {}
    for r in rows:
        d = r.get("candidate_diff") or r.get("diff") or ""
        if r.get("instance_id") and d:
            out[r["instance_id"]] = d
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default="reports/swebench_lite_slice_pinned.json")
    ap.add_argument("--diffs", required=True, help="a swebench_solve_*.json with per-task candidate diffs")
    ap.add_argument("--out", default="reports/swebench_referee_eval.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    fair_ids = {r["instance_id"] for r in json.loads(Path(args.slice).read_text())["per_task"] if r.get("fair")}
    diffs = _load_diffs(Path(args.diffs))
    insts = [i for i in load_lite(limit=0) if i.instance_id in fair_ids and i.instance_id in diffs]
    if args.limit:
        insts = insts[:args.limit]
    client = _client()

    rows: list = []
    done: set = set()
    if Path(args.out).exists():
        try:
            rows = json.loads(Path(args.out).read_text()).get("per_task", [])
            done = {r["instance_id"] for r in rows}
        except Exception:  # noqa: BLE001
            rows, done = [], set()

    def persist() -> None:
        committed = [r for r in rows if r["accept"]]
        false_commit = sum(1 for r in committed if not r["graded_solved"])
        missed = sum(1 for r in rows if not r["accept"] and r["graded_solved"])
        Path(args.out).write_text(json.dumps({
            "experiment": "swebench_referee_eval",
            "question": "does the repo-level FAIR referee (regression-guard + admitted-repro + diff-debate) "
                        "commit correct multi-file diffs with a bounded false-commit rate? (graded = FAIL_TO_PASS AND PASS_TO_PASS)",
            "evidence_tier": "real SWE-bench Lite, no Docker; fair signals only in the decision; held-out FAIL_TO_PASS+PASS_TO_PASS used solely to grade commits (full SWE-bench solved)",
            "diffs_source": args.diffs, "n": len(rows),
            "committed": len(committed), "committed_correct": sum(1 for r in committed if r["graded_solved"]),
            "false_commit": false_commit,
            "false_commit_rate": round(false_commit / len(committed), 3) if committed else 0.0,
            "missed": missed, "solvable_in_diffs": sum(1 for r in rows if r["graded_solved"]),
            "per_task": rows}, indent=2) + "\n")

    t0 = time.time()
    for inst in insts:
        if inst.instance_id in done:
            continue
        p = prepare(inst)
        if not p.ok:
            continue
        cand = diffs[inst.instance_id]
        # GRADER ONLY (never an input to the decision). Full SWE-bench "solved" = FAIL_TO_PASS passes
        # AND PASS_TO_PASS kept: a diff that fixes the target but breaks an existing test is NOT solved,
        # so committing it is a FALSE-COMMIT (F2P-only grading hides P2P regressions the guard misses).
        graded_f2p, graded_p2p = verify(p, cand)
        d = referee(inst, cand, client=client)
        row = {"instance_id": inst.instance_id, "family": inst.family, "accept": d.accept,
               "graded_solved": bool(graded_f2p and graded_p2p),
               "graded_f2p": bool(graded_f2p), "graded_p2p": bool(graded_p2p),
               "regression_ok": d.regression_ok,
               "repro_admissible": d.repro_admissible, "repro_pass": d.repro_pass,
               "debate_accept": d.debate_accept, "n_repro_admitted": d.n_repro_admitted,
               "guard_tests_run": d.guard_tests_run, "reason": d.reason}
        rows.append(row)
        print(f"[{len(rows)}/{len(insts)}] {inst.instance_id:30} accept={d.accept} graded_solved={bool(graded_f2p)} "
              f"reg={d.regression_ok} repro={d.repro_admissible}/{d.repro_pass} debate={d.debate_accept} "
              f"({round(time.time()-t0)}s)", flush=True)
        persist()

    committed = [r for r in rows if r["accept"]]
    fc = sum(1 for r in committed if not r["graded_solved"])
    print(f"\n=== SWE-BENCH REFEREE === {len(rows)} tasks | committed {len(committed)} "
          f"(correct {sum(1 for r in committed if r['graded_solved'])}) | false-commit {fc} "
          f"(rate {round(fc/len(committed),3) if committed else 0.0}) | "
          f"missed {sum(1 for r in rows if not r['accept'] and r['graded_solved'])}", flush=True)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
