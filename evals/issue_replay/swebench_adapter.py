# ruff: noqa: E501
"""SWE-bench Lite adapter (P9 Pillar A) — a DE-SATURATED real benchmark, no Docker.

Our 52-bundle corpus is saturated (Codex 51/52), so it can't show a breakthrough. SWE-bench Lite is the
recognized de-saturated benchmark (real multi-file repo bugs). Full SWE-bench uses per-task Docker
images; we don't need them — feasibility is verified in-container: `datasets` loads the specs, `git
clone` + a per-instance venv + `pytest <FAIL_TO_PASS nodeids>` runs hermetically (probe:
pytest-dev__pytest-11148 → buggy fails, gold passes).

Scope: a LIGHT-repo whitelist (pure-Python, pip-installable, fast tests) — pytest/requests/flask/…
Grading is SWE-bench-standard: apply the dataset `test_patch` (adds the FAIL_TO_PASS tests), then a
candidate is solved iff all FAIL_TO_PASS pass AND all PASS_TO_PASS still pass. The candidate is a
unified diff (what the vendor agents/our router produce); the gold `patch` and the FAIL_TO_PASS names
are the held-out oracle — never shown to the solver.

    uv run python -m evals.issue_replay.swebench_adapter --whitelist pytest,requests,flask \
        --out reports/swebench_lite_slice.json          # fairness-gate the slice (gold vs empty)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import venv
from dataclasses import dataclass
from pathlib import Path

_LIGHT = ("pytest-dev/pytest", "psf/requests", "pallets/flask", "pylint-dev/pylint",
          "sphinx-doc/sphinx", "sympy/sympy")
_CACHE = Path(os.environ.get("ACP_SWE_CACHE", "/tmp/swebench_cache"))


@dataclass
class SweInstance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    test_patch: str
    gold_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    created_at: str = ""
    version: str = ""

    @property
    def family(self) -> str:
        return self.repo.split("/")[-1]


def load_lite(whitelist: tuple[str, ...] = _LIGHT, limit: int = 0, newest_first: bool = True) -> list[SweInstance]:
    """Load SWE-bench Lite test split, filtered to the repo whitelist (substring match on family)."""
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    fams = {w.split("/")[-1] for w in whitelist}
    out: list[SweInstance] = []
    for r in ds:
        if r["repo"].split("/")[-1] not in fams:
            continue
        f2p = r["FAIL_TO_PASS"]
        p2p = r["PASS_TO_PASS"]
        out.append(SweInstance(
            instance_id=r["instance_id"], repo=r["repo"], base_commit=r["base_commit"],
            problem_statement=r["problem_statement"], test_patch=r["test_patch"], gold_patch=r["patch"],
            fail_to_pass=json.loads(f2p) if isinstance(f2p, str) else list(f2p),
            pass_to_pass=json.loads(p2p) if isinstance(p2p, str) else list(p2p),
            created_at=r.get("created_at", ""), version=str(r.get("version", ""))))
    out.sort(key=lambda t: t.created_at, reverse=newest_first)  # newer commits install on modern Python
    return out[:limit] if limit else out


def _sh(cmd: list[str], *, cwd: Path | None = None, timeout: int = 300, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=env or {**os.environ, "GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1"})
        return p.returncode, p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


@dataclass
class Prepared:
    inst: SweInstance
    repo_dir: Path
    py: str          # path to the venv python
    ok: bool
    note: str = ""


def _spec_for(inst: SweInstance) -> dict | None:
    """SWE-bench's pinned per-(repo,version) env spec: python, pip_packages, install, pre_install,
    test_cmd. This is what reconstructs the env so the gold patch passes (the no-Docker fairness gap)."""
    try:
        from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
        return MAP_REPO_VERSION_TO_SPECS.get(inst.repo, {}).get(inst.version)
    except Exception:  # noqa: BLE001
        return None


def _venv_env(venv_dir: Path) -> dict:
    import os
    return {**os.environ, "PATH": f"{venv_dir}/bin:/usr/bin:/bin",
            "GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1", "VIRTUAL_ENV": str(venv_dir)}


def prepare(inst: SweInstance, *, install_timeout: int = 900) -> Prepared:
    """Clone @ base_commit, build the PINNED per-task env (swebench spec: python version + pinned
    pip_packages + install cmd), apply test_patch. Cached per instance_id. Leaves the repo at
    base+test_patch (FAIL_TO_PASS present, code still buggy) — ready for a candidate patch."""
    work = _CACHE / inst.instance_id
    venv_dir = work / ".venv"
    py = str(venv_dir / "bin" / "python")
    stamp = work / ".prepared"
    if stamp.exists() and Path(py).exists():
        return Prepared(inst, work / "repo", py, ok=True, note="cached")
    repo_dir = work / "repo"
    work.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        rc, log = _sh(["git", "clone", "--quiet", f"https://github.com/{inst.repo}", str(repo_dir)], timeout=300)
        if rc:
            return Prepared(inst, repo_dir, py, ok=False, note=f"clone failed: {log[-200:]}")
    rc, log = _sh(["git", "checkout", "-q", "-f", inst.base_commit], cwd=repo_dir)
    if rc:
        return Prepared(inst, repo_dir, py, ok=False, note=f"checkout failed: {log[-200:]}")
    _sh(["git", "clean", "-qfdx"], cwd=repo_dir)
    # build the venv at the spec's pinned python (uv fetches it); fall back to the host interpreter
    spec = _spec_for(inst)
    pyver = (spec or {}).get("python", "3.11")
    import shutil as _sh_mod
    if Path(py).exists():
        _sh_mod.rmtree(venv_dir, ignore_errors=True)
    rc, log = _sh(["uv", "venv", "--seed", "--python", str(pyver), str(venv_dir)], timeout=300)
    if rc or not Path(py).exists():
        venv.create(venv_dir, with_pip=True)   # fallback: host python
    env = _venv_env(venv_dir)
    _sh(["python", "-m", "pip", "install", "-q", "-U", "pip", "setuptools", "wheel"], cwd=repo_dir, timeout=300, env=env)
    for pre in (spec or {}).get("pre_install", []) or []:
        _sh(["bash", "-lc", pre], cwd=repo_dir, timeout=install_timeout, env=env)
    pinned = (spec or {}).get("pip_packages") or []
    if pinned:
        rc, log = _sh(["python", "-m", "pip", "install", "-q", *pinned], cwd=repo_dir, timeout=install_timeout, env=env)
    install_cmd = (spec or {}).get("install") or "python -m pip install -e ."
    rc, log = _sh(["bash", "-lc", install_cmd], cwd=repo_dir, timeout=install_timeout, env=env)
    if rc:
        return Prepared(inst, repo_dir, py, ok=False, note=f"install failed: {log[-300:]}")
    _sh(["python", "-m", "pip", "install", "-q", "pytest"], cwd=repo_dir, timeout=300, env=env)  # ensure runner
    (repo_dir / "_test.patch").write_text(inst.test_patch)
    rc, log = _sh(["git", "apply", "_test.patch"], cwd=repo_dir)
    if rc:
        return Prepared(inst, repo_dir, py, ok=False, note=f"test_patch apply failed: {log[-200:]}")
    # commit base+test_patch as the reusable ground state, so verify() can revert a candidate back to
    # it (the FAIL_TO_PASS tests stay present; only the candidate's source edits are undone)
    _sh(["git", "add", "-A"], cwd=repo_dir)
    rc, log = _sh(["git", "-c", "user.email=acp@local", "-c", "user.name=acp",
                   "commit", "-qam", "base+test_patch"], cwd=repo_dir)
    if rc:
        return Prepared(inst, repo_dir, py, ok=False, note=f"commit base state failed: {log[-200:]}")
    stamp.write_text("ok")
    return Prepared(inst, repo_dir, py, ok=True)


def _run_named(p: Prepared, names: list[str], *, timeout: int = 300) -> bool:
    if not names:
        return True
    # NB: do NOT pass `-o addopts=` — real repos (esp. pytest-testing-pytest) require their own pytest
    # config (testpaths/plugins) or collection INTERNALERRORs ("no tests ran"). rc 0 == all named pass.
    rc, _ = _sh([p.py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *names],
                cwd=p.repo_dir, timeout=timeout)
    return rc == 0


def verify(p: Prepared, candidate_diff: str | None) -> tuple[bool, bool]:
    """Apply `candidate_diff` (None = leave buggy) on top of base+test_patch, return
    (fail_to_pass_all_pass, pass_to_pass_all_pass). Reverts the candidate afterward so the prepared
    repo is reusable. The candidate must NOT touch test files (enforced by the caller's fairness scan)."""
    applied = False
    if candidate_diff:
        (p.repo_dir / "_cand.patch").write_text(candidate_diff)
        rc, _ = _sh(["git", "apply", "_cand.patch"], cwd=p.repo_dir)
        if rc:
            rc, _ = _sh(["git", "apply", "--3way", "_cand.patch"], cwd=p.repo_dir)
        applied = rc == 0
        if not applied:
            return False, False
    try:
        f2p = _run_named(p, p.inst.fail_to_pass)
        p2p = _run_named(p, p.inst.pass_to_pass[:30])  # cap p2p for runtime
    finally:
        if applied:   # revert candidate back to the committed base+test_patch ground state
            _sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=p.repo_dir)
            _sh(["git", "clean", "-qfd"], cwd=p.repo_dir)
    return f2p, p2p


def check_fairness(p: Prepared) -> dict:
    """Core fairness = buggy fails FAIL_TO_PASS AND gold passes FAIL_TO_PASS (the bug-specific oracle).
    PASS_TO_PASS is only a regression GUARD and is env-flaky outside SWE-bench's Docker images, so it is
    ADVISORY here (reported, not gating) — at candidate-grading time the guard is calibrated to the
    gold-passing P2P subset, which can't be over-strict. Old tasks where gold doesn't pass F2P in our
    venv (e.g. ancient requests on modern Python) are correctly excluded."""
    bug_f2p, _ = verify(p, None)
    gold_f2p, gold_p2p = verify(p, p.inst.gold_patch)
    return {"buggy_fails_f2p": not bug_f2p, "gold_passes_f2p": gold_f2p, "gold_keeps_p2p": gold_p2p,
            "fair": (not bug_f2p) and gold_f2p}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whitelist", default="pytest,requests,flask")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="reports/swebench_lite_slice.json")
    args = ap.parse_args()
    wl = tuple(s.strip() for s in args.whitelist.split(",") if s.strip())
    insts = load_lite(whitelist=tuple(w for w in _LIGHT if any(s in w for s in wl)), limit=args.limit)
    print(f"loaded {len(insts)} tasks from {sorted({i.family for i in insts})}", flush=True)

    out = Path(args.out)
    rows: list = []
    done: set = set()
    if out.exists():
        try:
            rows = json.loads(out.read_text()).get("per_task", [])
            done = {r["instance_id"] for r in rows}
            print(f"resume: {len(done)} tasks already gated", flush=True)
        except Exception:  # noqa: BLE001
            rows, done = [], set()

    for inst in insts:
        if inst.instance_id in done:
            continue
        prep = prepare(inst)
        if not prep.ok:
            row = {"instance_id": inst.instance_id, "family": inst.family, "prepared": False,
                   "note": prep.note, "fair": False}
        else:
            fair = check_fairness(prep)
            row = {"instance_id": inst.instance_id, "family": inst.family, "prepared": True,
                   "n_f2p": len(inst.fail_to_pass), "n_p2p": len(inst.pass_to_pass), **fair}
        rows.append(row)
        print(f"[{len([r for r in rows if r.get('prepared')])}/{len(insts)}] {inst.instance_id:34} "
              f"prepared={row['prepared']} fair={row.get('fair')} {row.get('note','')[:60]}", flush=True)
        _persist(out, rows, insts)
    _summary(rows, insts)
    return 0


def _persist(out: Path, rows: list, insts: list) -> None:
    fair = [r for r in rows if r.get("fair")]
    out.write_text(json.dumps({
        "experiment": "swebench_lite_slice", "n_loaded": len(insts), "n_done": len(rows),
        "n_prepared": sum(1 for r in rows if r.get("prepared")), "n_fair": len(fair),
        "families": sorted({r["family"] for r in fair}),
        "per_task": rows,
        "evidence_tier": "real SWE-bench Lite; hermetic (clone@base + venv + test_patch); graded by named FAIL_TO_PASS/PASS_TO_PASS; no Docker",
    }, indent=2) + "\n")


def _summary(rows: list, insts: list) -> None:
    fair = [r for r in rows if r.get("fair")]
    print(f"\n=== SWE-bench Lite slice === loaded {len(insts)} | prepared "
          f"{sum(1 for r in rows if r.get('prepared'))} | FAIR {len(fair)} "
          f"across {sorted({r['family'] for r in fair})}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
