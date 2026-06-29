# ruff: noqa: E501
"""Fair verify-stop for SWE-bench routing (P9 Track B) — the missing trust signal.

The P9 routing economics assumed an ORACLE stop (peeking at the held-out FAIL_TO_PASS). In production
you can't. This builds a FAIR stop signal and measures how trustworthy it is:

  1. generate_repro: an LLM writes standalone reproduction test(s) from the issue problem_statement
     ONLY (never the held-out FAIL_TO_PASS / gold).
  2. admit_repro: keep a repro only if it FAILS on the buggy base (P8's discipline — proven to
     reproduce the bug; a repro that passes on buggy proves nothing). Fair: base + the repro, no
     held-out test.
  3. verify_stop: a candidate diff is "verified" iff every admitted repro PASSES on it. This is the
     cheap-commit-vs-escalate decision the router needs.

Measured against the held-out grader: FALSE-COMMIT = verified but FAIL_TO_PASS actually fails (the
trust cost); MISSED = not verified but actually solved (lost cheap commits). Reuses swebench_adapter.

    uv run python -m evals.issue_replay.swebench_verify_stop --slice reports/swebench_lite_slice_pinned.json \
        --validate     # gold-vs-buggy sanity on each fair task (no agent calls)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from evals.issue_replay.swebench_adapter import (
    SweInstance,
    _sh,
    _venv_env,
    load_lite,
    prepare,
)

_REPRO_PROMPT = (
    "You are writing a STANDALONE pytest reproduction test for a reported bug. Using ONLY the issue "
    "below, write a single self-contained test file that FAILS on the current (buggy) code and would "
    "PASS once the bug is fixed. Import from the installed package as a normal user would. Assert the "
    "spec-correct behaviour the issue describes; if the issue gives a reproduction snippet, encode it. "
    "Assert ONLY the specific behaviour the issue explicitly states (the presence/absence or the exact "
    "value it names). Do NOT over-specify: avoid asserting exact log/CLI output strings, message wording, "
    "formatting, ordering, or counts that the issue does not literally give — a correct fix may word "
    "things differently, and an over-strict assertion makes a correct fix fail your test. Prefer a "
    "minimal assertion (e.g. `X in result` or `result == <value-named-in-issue>`) over matching full "
    "output. Do NOT reference any hidden or repo-internal test. Return ONLY the test file as one ```python "
    "block.\n\nREPO: {repo}\n\nISSUE:\n{problem}\n"
)


def _client():
    try:
        import anthropic
        return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ACP_ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return None


def _strip_lang(block: str) -> str:
    """Drop an optional ```language tag on the fenced block's first line WITHOUT eating code chars
    (the old p[9:]/p[7:] slices were off-by-2/1 vs len('python\\n')=7 / len('python')=6, which chopped
    the leading characters of the test source and produced SyntaxErrors)."""
    first, sep, rest = block.partition("\n")
    if sep and first.strip().lower() in ("python", "py", "python3", "pytest", ""):
        return rest
    return block


def _first_block(text: str) -> str:
    if "```" in text:
        body = max((_strip_lang(p) for p in text.split("```")[1::2]), key=len, default="")
        return body if "def test" in body else ""
    return text if "def test" in text else ""


def generate_repro(inst: SweInstance, *, client, model: str = "claude-haiku-4-5", n: int = 3) -> tuple[list[str], float]:
    """LLM writes standalone reproduction tests from the problem_statement only."""
    if client is None:
        return [], 0.0
    out: list[str] = []
    cost = 0.0
    for _ in range(n):
        try:
            msg = client.messages.create(model=model, max_tokens=1200,
                                         messages=[{"role": "user", "content": _REPRO_PROMPT.format(repo=inst.repo, problem=inst.problem_statement[:6000])}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            body = _first_block(text)
            if body.strip():
                out.append(body)
            u = getattr(msg, "usage", None)
            cost += round((getattr(u, "input_tokens", 0) or 0) / 1e6 + (getattr(u, "output_tokens", 0) or 0) * 5 / 1e6, 6)
        except Exception:  # noqa: BLE001
            continue
    return out, cost


def _run_repro_on(repo_dir: Path, py: str, repro_src: str, *, timeout: int = 120) -> str:
    """Return 'pass' | 'fail' (assertion/behavioural) | 'error' (import/collection) for a repro file."""
    f = repo_dir / "_acp_repro.py"
    f.write_text(repro_src)
    env = _venv_env(Path(py).parent.parent)
    try:
        p = subprocess.run([py, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider", "-o", "addopts=", "_acp_repro.py"],
                           cwd=repo_dir, capture_output=True, text=True, timeout=timeout, env=env)
        text = p.stdout + "\n" + p.stderr
        if p.returncode == 0:
            return "pass"
        # a real bug-reproduction is an ASSERTION failure; import/collection/syntax breakage is "error"
        # (must NOT be admitted as fail-on-base — that was letting corrupted repros masquerade as repros)
        if "AssertionError" in text:
            return "fail"
        if any(m in text for m in ("ModuleNotFoundError", "ImportError", "SyntaxError",
                                   "error during collection", "errors during collection",
                                   "AttributeError", "NameError", "TypeError")):
            return "error"
        return "fail"
    except subprocess.TimeoutExpired:
        return "fail"
    finally:
        f.unlink(missing_ok=True)


def _base_checkout(inst: SweInstance):
    """A clean base checkout (no test_patch) + the prepared venv, for running repros fairly."""
    from evals.issue_replay.swebench_solve import _solve_checkout
    return _solve_checkout(inst, "repro")


def admit_repro(inst: SweInstance, repros: list[str]) -> list[str]:
    """Keep repros that FAIL (assert-class) on the buggy base — proven to reproduce; drop pass/error."""
    co = _base_checkout(inst)
    if co is None:
        return []
    repo, py = co
    kept = []
    for r in repros:
        if _run_repro_on(repo, py, r) == "fail":
            kept.append(r)
    return kept


def verify_stop(inst: SweInstance, candidate_diff: str, admitted: list[str]) -> bool:
    """A candidate is verified iff it makes ALL admitted repros pass (applied on the base checkout).

    NOTE (W4 #1, rejected): a strict-MAJORITY relaxation was tried to lift recall but made trust WORSE —
    it committed a non-fixing diff (pylint-6506) whose loose repros mostly passed, while still missing the
    over-strict case (pylint-5859). The signal is noisy in BOTH directions, so ALL-must-pass is the better
    precision/recall point; recall is bottlenecked by LLM repro QUALITY, not by this aggregation rule."""
    if not admitted:
        return False
    co = _base_checkout(inst)
    if co is None:
        return False
    repo, py = co
    if candidate_diff.strip():
        (repo / "_cand.patch").write_text(candidate_diff)
        rc, _ = _sh(["git", "apply", "_cand.patch"], cwd=repo)
        if rc:
            rc, _ = _sh(["git", "apply", "--3way", "_cand.patch"], cwd=repo)
        if rc:
            return False
    try:
        return all(_run_repro_on(repo, py, r) == "pass" for r in admitted)
    finally:
        _sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=repo)
        _sh(["git", "clean", "-qfd"], cwd=repo)


# ---- DIFFERENTIAL verify-stop (the salvage for absolute-repro's 0/6) -------------------------------
# Absolute repros fail because the LLM guesses the wrong *correct* value. The differential signal needs
# no correct value: capture the buggy output on the issue-implicated inputs, and a candidate is
# "verified" iff its behaviour DIVERGES from buggy there (the fix changed the implicated behaviour).
# Trade-off: it false-commits on wrong-but-different fixes — measured against the held-out grader.
_PROBE_PROMPT = (
    "Write a STANDALONE python script (no pytest, no asserts) that exercises the behaviour the issue "
    "describes: import the package, call the affected API on the specific inputs the issue implicates, "
    "and `print(repr(result))` for each (wrap each in try/except and print 'RAISES <ExcType>' on error). "
    "Deterministic output only. Return ONLY the script as one ```python block.\n\nREPO: {repo}\n\nISSUE:\n{problem}\n"
)


def generate_probe(inst: SweInstance, *, client, model: str = "claude-haiku-4-5") -> tuple[str, float]:
    if client is None:
        return "", 0.0
    try:
        msg = client.messages.create(model=model, max_tokens=1200,
                                     messages=[{"role": "user", "content": _PROBE_PROMPT.format(repo=inst.repo, problem=inst.problem_statement[:6000])}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        u = getattr(msg, "usage", None)
        cost = round((getattr(u, "input_tokens", 0) or 0) / 1e6 + (getattr(u, "output_tokens", 0) or 0) * 5 / 1e6, 6)
        body = text.split("```")[1] if "```" in text else text
        body = body[7:] if body.startswith("python") else body
        return body, cost
    except Exception:  # noqa: BLE001
        return "", 0.0


def _run_probe(repo_dir: Path, py: str, probe_src: str, *, timeout: int = 90) -> str | None:
    """Run the probe script; return its stdout (the captured behaviour) or None if it can't run."""
    f = repo_dir / "_acp_probe.py"
    f.write_text(probe_src)
    env = _venv_env(Path(py).parent.parent)
    try:
        p = subprocess.run([py, "_acp_probe.py"], cwd=repo_dir, capture_output=True, text=True, timeout=timeout, env=env)
        out = (p.stdout or "").strip()
        if not out:
            return None
        # normalize non-deterministic noise (object ids, set ordering) so only real behaviour change counts
        import re as _re
        out = _re.sub(r"0x[0-9a-fA-F]+", "0xADDR", out)
        return "\n".join(sorted(out.splitlines()))
    except subprocess.TimeoutExpired:
        return None
    finally:
        f.unlink(missing_ok=True)


def differential_verify(inst: SweInstance, candidate_diff: str, probe_src: str,
                        baseline_out: str | None) -> bool:
    """Verified-differential iff the candidate's probe output DIVERGES from the buggy baseline's
    (the fix changed the implicated behaviour). No correct value required."""
    if not probe_src.strip() or baseline_out is None:
        return False
    co = _base_checkout(inst)
    if co is None:
        return False
    repo, py = co
    if candidate_diff.strip():
        (repo / "_c.patch").write_text(candidate_diff)
        rc, _ = _sh(["git", "apply", "_c.patch"], cwd=repo)
        if rc:
            rc, _ = _sh(["git", "apply", "--3way", "_c.patch"], cwd=repo)
        if rc:
            return False
    try:
        out = _run_probe(repo, py, probe_src)
        return out is not None and out != baseline_out
    finally:
        _sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=repo)
        _sh(["git", "clean", "-qfd"], cwd=repo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default="reports/swebench_lite_slice_pinned.json")
    ap.add_argument("--out", default="reports/swebench_verify_stop.json")
    ap.add_argument("--validate", action="store_true",
                    help="gold-vs-buggy sanity: admitted repro should be verified on gold, NOT on buggy")
    ap.add_argument("--mode", default="absolute", choices=["absolute", "differential"],
                    help="absolute: repro must pass (needs correct value); differential: candidate must DIVERGE from buggy")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    fair_ids = {r["instance_id"] for r in json.loads(Path(args.slice).read_text())["per_task"] if r.get("fair")}
    insts = [i for i in load_lite(limit=0) if i.instance_id in fair_ids]
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

    for inst in insts:
        if inst.instance_id in done:
            continue
        if not prepare(inst).ok:
            continue
        if args.mode == "differential":
            probe, cost = generate_probe(inst, client=client)
            co = _base_checkout(inst)
            base_out = _run_probe(co[0], co[1], probe) if (co and probe.strip()) else None
            row = {"instance_id": inst.instance_id, "family": inst.family,
                   "probe_runs_on_buggy": base_out is not None, "gen_cost_usd": round(cost, 6)}
            if args.validate:
                # gold must DIVERGE from buggy on the probe (verified-differential); buggy must NOT
                row["gold_diverges"] = differential_verify(inst, inst.gold_patch, probe, base_out)
                row["buggy_diverges"] = differential_verify(inst, "", probe, base_out)
                row["repro_discriminates"] = bool(base_out) and row["gold_diverges"] and not row["buggy_diverges"]
            rows.append(row)
            print(f"[{len(rows)}/{len(insts)}] {inst.instance_id:30} probe_ok={row['probe_runs_on_buggy']} "
                  f"gold_diverges={row.get('gold_diverges')} buggy_diverges={row.get('buggy_diverges')} "
                  f"discriminates={row.get('repro_discriminates')}", flush=True)
            _persist(args.out, rows)
            continue
        repros, cost = generate_repro(inst, client=client)
        admitted = admit_repro(inst, repros)
        row = {"instance_id": inst.instance_id, "family": inst.family,
               "n_repros": len(repros), "n_admitted": len(admitted), "gen_cost_usd": round(cost, 6)}
        if args.validate:
            # the admitted repro must be VERIFIED on gold and NOT on buggy (a trustworthy stop signal)
            row["verified_on_gold"] = verify_stop(inst, inst.gold_patch, admitted)
            row["verified_on_buggy"] = verify_stop(inst, "", admitted)
            row["repro_discriminates"] = bool(admitted) and row["verified_on_gold"] and not row["verified_on_buggy"]
        rows.append(row)
        print(f"[{len(rows)}/{len(insts)}] {inst.instance_id:30} repros={len(repros)} admitted={len(admitted)} "
              f"gold_ok={row.get('verified_on_gold')} buggy_ok={row.get('verified_on_buggy')} "
              f"discriminates={row.get('repro_discriminates')}", flush=True)
        _persist(args.out, rows)
    _summary(rows)
    return 0


def _persist(out: str, rows: list) -> None:
    disc = [r for r in rows if r.get("repro_discriminates")]
    Path(out).write_text(json.dumps({"experiment": "swebench_verify_stop", "n": len(rows),
                                     "n_signal_available": sum(1 for r in rows if r.get("n_admitted") or r.get("probe_runs_on_buggy")),
                                     "n_discriminating": len(disc),
                                     "total_gen_cost_usd": round(sum(r["gen_cost_usd"] for r in rows), 4),
                                     "per_task": rows}, indent=2) + "\n")


def _summary(rows: list) -> None:
    avail = sum(1 for r in rows if r.get("n_admitted") or r.get("probe_runs_on_buggy"))
    disc = sum(1 for r in rows if r.get("repro_discriminates"))
    print(f"\n=== VERIFY-STOP === {len(rows)} tasks | signal available {avail} | discriminates gold-vs-buggy {disc} "
          f"=> fair stop signal available on {disc}/{len(rows)}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
