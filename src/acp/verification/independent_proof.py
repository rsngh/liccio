# ruff: noqa: E501
"""Independent proof signal — approximate held-out correctness WITHOUT the hidden test.

The measured binding constraint on routing this project: selection/escalation use "the PUBLIC test
passes" as the proof signal, so a candidate that OVERFITS the single public test (passes public,
fails the held-out hidden test) is chosen wrongly. The held-out hidden test is the oracle — but it
is unavailable at real selection time. This module builds a *proxy* for it from signals the
candidate never saw:

  1. INDEPENDENT TESTS generated from the issue spec (an LLM writes fresh tests from the issue text +
     the public test's import, never seeing the candidate or the hidden test).
  2. DIFFERENTIAL CONSENSUS across the k diverse candidates: a generated test that the *majority* of
     candidates fail is probably a BAD test (wrong expectation), so it is dropped — this hardens the
     proxy against noisy generated tests.
  3. ADVERSARIAL/SAFETY scan of the diff (reuses verification.adversarial): a high-severity gaming
     finding (deleted/weakened tests, swallowed exceptions, touched sensitive paths) fails the proxy.

``proxy_pass = public_pass AND passes-all-surviving-independent-checks AND not adversarial_high``.

Pure ``src`` (no eval imports): callers pass plain spec fields and candidate workspace paths. The
proxy's precision/recall against the true hidden oracle is measured in the eval and reported
honestly — the proxy is never claimed to equal the hidden test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from acp.verification.adversarial import has_high_severity, scan_diff


class SpecLike(Protocol):
    issue_text: str
    public_test: str
    module_path: str


@dataclass
class ProxyVerdict:
    candidate_id: str
    proxy_pass: bool
    public_pass: bool
    independent_pass: bool        # passed all surviving generated checks
    adversarial_high: bool
    n_checks_run: int
    n_checks_surviving: int
    n_checks_failed: int
    detail: str = ""


@dataclass
class GeneratedChecks:
    checks: list[str] = field(default_factory=list)   # each a full pytest module source
    cost_usd: float = 0.0
    model: str = ""


def _run_pytest(repo: Path, test_name: str) -> bool:
    """Run one test file in `repo` with a hermetic env; True iff it passes."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", test_name],
            cwd=repo, capture_output=True, text=True, timeout=60, check=False, env=env)
    except subprocess.TimeoutExpired:
        return False  # a hanging generated check fails closed, never crashes the verifier
    return proc.returncode == 0


# --- generation: an LLM writes independent tests from the SPEC (not the candidate) ----------

_GEN_PROMPT = (
    "You are a senior test engineer. Write {n} NEW, diverse pytest tests that check whether an "
    "implementation meets this specification. You are given the issue and ONE existing public test "
    "(which shows the import to use). Write DIFFERENT tests than the public one — cover edge cases, "
    "boundaries, and tricky inputs implied by the spec. Each test must be fully self-contained "
    "(include the import) and must NOT import or reference any hidden/secret test.\n\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...` function).\n\n"
    "ISSUE:\n{issue}\n\nEXISTING PUBLIC TEST (for the import + one example):\n{public}\n"
)


def generate_checks(spec: SpecLike, *, client, model: str = "claude-haiku-4-5",
                    n: int = 6) -> GeneratedChecks:
    """Generate independent tests from the spec via a cheap LLM. Never sees the candidate/hidden."""
    if client is None:
        return GeneratedChecks(model="(none)")
    prompt = _GEN_PROMPT.format(n=n, issue=spec.issue_text, public=spec.public_test)
    try:
        msg = client.messages.create(model=model, max_tokens=1500,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        checks = _parse_check_array(text)
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        return GeneratedChecks(checks=checks[:n], cost_usd=cost, model=model)
    except Exception as exc:  # noqa: BLE001 - generation is best-effort
        return GeneratedChecks(model=f"error:{str(exc)[:40]}")


def _parse_check_array(text: str) -> list[str]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        arr = json.loads(text[start:end + 1])
        return [s for s in arr if isinstance(s, str) and "def test" in s]
    except Exception:  # noqa: BLE001
        return []


# --- evaluation: run checks per candidate, consensus-filter, compose the proxy verdict -------

def _run_checks_on(workspace: Path, checks: list[str], root: Path, cand_id: str) -> list[bool]:
    """Copy the candidate workspace once, run each generated check, return per-check pass flags."""
    proxy_ws = root / f"proxy_{cand_id}_{time.time_ns()}"
    shutil.copytree(workspace, proxy_ws, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    out: list[bool] = []
    for i, src in enumerate(checks):
        name = f"test_indep_{i}.py"
        (proxy_ws / name).write_text(src)
        try:
            out.append(_run_pytest(proxy_ws, name))
        except Exception:  # noqa: BLE001 - a malformed generated test counts as not-passed
            out.append(False)
        (proxy_ws / name).unlink(missing_ok=True)
    shutil.rmtree(proxy_ws, ignore_errors=True)
    return out


def proxy_evaluate(spec: SpecLike, candidates: list[dict], root: Path, *,
                   checks: list[str], consensus_floor: float = 0.5) -> dict[str, ProxyVerdict]:
    """Score every candidate with the proxy.

    ``candidates`` items: ``{"id", "workspace" (Path), "public_pass" (bool), "diff" (str|None)}``.
    A generated check that < ``consensus_floor`` of candidates pass is dropped as likely-wrong
    (differential consensus). ``proxy_pass`` = public_pass AND passes all surviving checks AND not
    adversarial-high.
    """
    ids = [c["id"] for c in candidates]
    matrix = {c["id"]: (_run_checks_on(c["workspace"], checks, root, c["id"]) if checks else [])
              for c in candidates}
    n_checks = len(checks)
    surviving = []
    for j in range(n_checks):
        passes = sum(1 for cid in ids if matrix[cid][j])
        if passes >= max(1, int(round(consensus_floor * len(ids)))):
            surviving.append(j)
    verdicts: dict[str, ProxyVerdict] = {}
    for c in candidates:
        cid = c["id"]
        flags = matrix[cid]
        failed = [j for j in surviving if not flags[j]]
        independent_pass = len(failed) == 0
        adv_high = False
        diff = c.get("diff")
        if diff:
            from acp.schemas.workspace import DiffBundle
            adv_high = has_high_severity(scan_diff(DiffBundle(unified_diff=diff, changed_files=[])))
        ppass = bool(c["public_pass"])
        proxy_pass = ppass and independent_pass and not adv_high
        verdicts[cid] = ProxyVerdict(
            candidate_id=cid, proxy_pass=proxy_pass, public_pass=ppass,
            independent_pass=independent_pass, adversarial_high=adv_high,
            n_checks_run=n_checks, n_checks_surviving=len(surviving), n_checks_failed=len(failed),
            detail=f"failed_checks={failed}" if failed else "")
    return verdicts
