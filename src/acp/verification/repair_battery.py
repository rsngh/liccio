# ruff: noqa: E501
"""Dense, fair, in-loop repair oracle — the continuous gradient the binary hidden test never gave.

The measured wall (issue_replay_diagnosis.json) is `no_progress`: the cheap repair loop localizes the
right function and still writes a wrong fix. Verified in code, that loop's in-loop accept signal is
the held-out hidden test (`repair_harness.py:178/217`) — BINARY (pass/fail) and PRIVILEGED (the vendor
CLIs never see it). A single 0/1 bit over k samples gives the model nothing to climb.

This module turns the existing `independent_proof` proxy into a *continuous* value function the repair
search can climb, built ONLY from signals the candidate never saw (issue spec + public test + the
buggy baseline) — never the hidden test (which stays reserved for grading) and never the gold patch.

Signal types (all fair):
  * EXAMPLE checks   — fresh spec-derived tests (reuses `independent_proof.generate_checks`).
  * PROPERTY checks  — metamorphic / invariant assertions implied by the spec (idempotence,
                       round-trip, bounds, type-stability).
  * DIFFERENTIAL     — computed for free by running every check on the BUGGY BASELINE once:
      - a check the baseline FAILS is *discriminating* (it exercises the bug; the fix must flip it);
      - a check the baseline PASSES is a *regression guard* (behavior that must stay identical).
    No input-capture needed; the discriminating/guard split falls straight out of baseline results.

Continuous score in [0,1]:
    0.0                              if adversarial-high or the public test fails
    else  w_d * (discriminating passed / discriminating surviving)
        + w_g * (guard passed        / guard surviving)
        + w_p * public_pass
The binary `proxy_pass` is recoverable (`score == 1.0` with >= min_surviving discriminating checks),
so the existing stop-signal / red-team gates keep working. Pure `src` (callers pass plain paths).
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from acp.verification.adversarial import has_high_severity, scan_diff
from acp.verification.independent_proof import _parse_check_array, _run_pytest


class SpecLike(Protocol):
    issue_text: str
    public_test: str
    module_path: str


# weights: discriminating (did we fix the bug) dominates; guard (did we break neighbours) protects
# against the `regressed` failure row; public is the canonical discriminating behaviour.
_W_DISCRIM, _W_GUARD, _W_PUBLIC = 0.6, 0.3, 0.1


@dataclass
class CheckResult:
    check_id: str
    kind: str               # "example" | "property"
    role: str               # "discriminating" | "guard"  (vs the buggy baseline)
    passed: bool
    surviving: bool = True   # survived cross-candidate consensus (Phase 1 score_pool); True otherwise
    detail: str = ""


@dataclass
class BatteryScore:
    candidate_id: str
    score: float
    public_pass: bool
    adversarial_high: bool
    n_discrim_surviving: int
    n_discrim_passed: int
    n_guard_surviving: int
    n_guard_passed: int
    results: list[CheckResult] = field(default_factory=list)
    disc_frac: float = 0.0               # weighted fraction of surviving discriminating checks passed
    guard_frac: float = 0.0              # weighted fraction of surviving guard checks passed
    battery_valid: bool = True

    def accept(self, *, disc_floor: float = 0.8, guard_floor: float = 0.9) -> bool:
        """Relaxed acceptance bar (replaces the all-checks `proxy_pass` that rejected gold 11/11):
        a minority of WRONG generated checks must not poison the verdict. Mutant-sensitivity weights
        already damp weak checks, so weighted fractions over the floors = accept."""
        return (self.battery_valid and self.public_pass and not self.adversarial_high
                and self.n_discrim_surviving >= 2
                and self.disc_frac >= disc_floor and self.guard_frac >= guard_floor)

    @property
    def proxy_pass(self) -> bool:
        """Binary fail-closed verdict (recovers the independent_proof contract): public passes, no
        adversarial-high, and every surviving discriminating + guard check passes over >=1 discrim."""
        return (self.public_pass and not self.adversarial_high and self.n_discrim_surviving >= 1
                and self.n_discrim_passed == self.n_discrim_surviving
                and self.n_guard_passed == self.n_guard_surviving)

    def feedback(self, *, max_checks: int = 4) -> str:
        """Structured NL the search conditions its next expansion on: which checks still fail."""
        if self.adversarial_high:
            return "ADVERSARIAL: the diff weakens/deletes tests or swallows exceptions — fix the real cause instead."
        if not self.public_pass:
            return "The public (failing) test still does not pass — the core behaviour is still wrong."
        lines: list[str] = []
        for r in self.results:
            if r.surviving and not r.passed:
                tag = "still-buggy" if r.role == "discriminating" else "REGRESSION (this used to pass)"
                lines.append(f"- {r.kind} check {r.check_id} FAILED [{tag}]: {r.detail}")
            if len(lines) >= max_checks:
                break
        if not lines:
            return "All surviving checks pass."
        return ("Checks still failing (make these pass without breaking the rest):\n" + "\n".join(lines))


@dataclass
class RepairBattery:
    checks: list[tuple[str, str]]        # (kind, test_source)
    baseline_pass: list[bool]            # per-check pass flag on the BUGGY baseline (computed once)
    public_test: str
    module_path: str
    extra_files: dict[str, str]
    gen_cost_usd: float = 0.0
    model: str = ""
    valid: bool = True                   # False => no discriminating checks could be produced; the
    invalid_reason: str = ""             # score is then capped (never 1.0) and callers must escalate
    check_weights: list[float] = field(default_factory=list)  # mutant-sensitivity weights (v2)
    mutation_info: dict = field(default_factory=dict)

    def weight(self, j: int) -> float:
        return self.check_weights[j] if j < len(self.check_weights) else 1.0

    @property
    def n_discriminating(self) -> int:
        return sum(1 for p in self.baseline_pass if not p)

    @property
    def n_guard(self) -> int:
        return sum(1 for p in self.baseline_pass if p)


# CRITICAL import-pinning: bundles are often flattened (e.g. boltons/dictutils.py -> dictutils.py,
# imported as `import dictutils`). Generators left to their own devices use the real-world package
# path (`from boltons import dictutils`) -> ModuleNotFoundError -> the check ERRORS on buggy AND gold
# and is mis-counted as discriminating. Pinning the import to the public test's convention + a
# collect-only validity filter is what makes the battery score a real gradient (gold must pass).
_IMPORT_RULE = (
    "CRITICAL: import the module under test EXACTLY as the public test does — use ONLY these import "
    "line(s) verbatim and NO other module import (do NOT import from any package such as `from "
    "<pkg> import ...`):\n{imports}\n"
)

_EXAMPLE_PROMPT = (
    "You are a senior test engineer. Write {n} NEW, diverse pytest tests that check whether an "
    "implementation meets this specification. Cover edge cases, boundaries, and tricky inputs implied "
    "by the spec; write DIFFERENT tests than the public one. Each test must be fully self-contained, "
    "must NOT reference any hidden/secret test, and must only assert behaviour the spec guarantees.\n\n"
    "{import_rule}\n{entail_rule}\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...`).\n\nISSUE:\n{issue}\n\nEXISTING PUBLIC TEST:\n{public}\n"
)

_PROP_PROMPT = (
    "You are a senior test engineer writing PROPERTY-BASED / metamorphic tests. Write {n} NEW pytest "
    "tests that assert INVARIANTS implied by the spec rather than single input/output pairs — e.g. "
    "idempotence (f(f(x))==f(x)), round-trip (decode(encode(x))==x), monotonicity, bounds/range, "
    "type-stability, or behaviour on empty / singleton / boundary inputs. Each test must be fully "
    "self-contained, must NOT reference any hidden/secret test, and must only use behaviour the spec "
    "guarantees.\n\n{import_rule}\n{entail_rule}\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...`).\n\nISSUE:\n{issue}\n\nEXISTING PUBLIC TEST:\n{public}\n"
)


def _extract_imports(public_test: str) -> str:
    """The import line(s) the public test uses — the bundle's real import convention."""
    lines = [ln for ln in public_test.splitlines()
             if ln.strip().startswith(("import ", "from ")) and "import" in ln]
    return "\n".join(lines) if lines else "(use the import shown in the public test)"


# ---- v2 (discriminating-by-construction) prompts -------------------------------------------------
# The generator may see the BUGGY focus region: the repair model sees the exact same region, gold and
# the hidden test stay withheld, and every emitted check is execution-validated (must FAIL on the
# buggy baseline), so showing buggy code cannot pin buggy behaviour into the battery.

# The single most important rule, learned from G1: when the issue does not state the exact expected
# value, a guessed exact assertion fails the TRUE fix too (e.g. "fix infinite daterange(x,x)" — is the
# result 0 elements or 1? the issue doesn't say). The check must then assert only the property that
# separates fixed from buggy: termination (via itertools.islice bounds), no exception, count bounds,
# membership, ordering — NEVER a guessed exact value.
_ENTAIL_RULE = (
    "EXPECTATION RULE (critical): assert ONLY what the issue text or the public test explicitly "
    "entails. If the exact expected value is not stated, DO NOT guess it — assert the weakest property "
    "that still distinguishes fixed from buggy code: termination (always bound potentially-infinite "
    "iteration with itertools.islice(..., K)), 'does not raise', count bounds (<=, >=), membership, or "
    "ordering. Never let a test hang: bound every loop/iterator. The public test is authoritative "
    "about semantics where it speaks.\n"
)

_REGEN_PROMPT = (
    "You are a senior test engineer. The code below contains a BUG described by the issue. Every test "
    "written so far PASSES on this buggy code — they fail to exercise the bug at all. Write {n} NEW "
    "pytest tests that FAIL on the code below precisely because of the described bug, and that would "
    "pass once the bug is fixed per the issue. Target the specific wrong behaviour. Each test must be "
    "fully self-contained and must NOT reference any hidden/secret test.\n\n{import_rule}\n{entail_rule}\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...`).\n\nISSUE:\n{issue}\n\nBUGGY CODE (the suspected region):\n```python\n{focus}\n```\n\n"
    "EXISTING PUBLIC TEST:\n{public}\n"
)

_ENTAIL_FILTER_PROMPT = (
    "You are auditing pytest tests for SPEC ENTAILMENT. For each numbered test below, decide whether "
    "its asserted expectations are EXPLICITLY entailed by the issue text / public test, or whether "
    "any expected value is a GUESS the spec does not determine (e.g. asserting an exact count or "
    "value the issue never states). Judge the assertions, not the style.\n\n"
    "Return ONLY a JSON array of the NUMBERS of tests whose expectations are guesses (empty array if "
    "none).\n\nISSUE:\n{issue}\n\nPUBLIC TEST (authoritative):\n{public}\n\nTESTS:\n{tests}\n"
)

_PIN_PROMPT = (
    "You are a senior test engineer documenting CURRENT behaviour. The code below has a bug described "
    "by the issue. Write {n} pytest tests that PASS on the code AS IT IS NOW, each pinning a concrete "
    "input/output of the very behaviour the issue says is wrong (call the affected function with "
    "inputs the issue implicates and assert what the buggy code ACTUALLY returns/does today). Each "
    "test must be fully self-contained.\n\n{import_rule}\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...`).\n\nISSUE:\n{issue}\n\nCURRENT (BUGGY) CODE:\n```python\n{focus}\n```\n\n"
    "EXISTING PUBLIC TEST:\n{public}\n"
)

_FLIP_PROMPT = (
    "Each pytest test below currently PASSES on a buggy implementation — its assertions pin the WRONG "
    "behaviour described by the issue. Rewrite EACH test so its assertions state the SPEC-CORRECT "
    "expected behaviour instead (what a fixed implementation should do per the issue). Keep the same "
    "imports, function calls and inputs; change ONLY the expected values/assertions. If the issue does "
    "not state the exact corrected value, assert the weakest property that distinguishes fixed from "
    "buggy (not-equal to the buggy value, bounds, 'does not raise', bounded termination) instead of "
    "guessing. Return ONLY a JSON array of the rewritten test files, same length and order as the "
    "input.\n\nISSUE:\n{issue}\n\nTESTS PINNING BUGGY BEHAVIOUR:\n{tests_json}\n"
)


def _generate(spec: SpecLike, *, client, model: str, n: int, template: str, **extra) -> tuple[list[str], float]:
    """Generate checks with the import pinned to the public test's convention."""
    if client is None or n <= 0:
        return [], 0.0
    import_rule = _IMPORT_RULE.format(imports=_extract_imports(spec.public_test))
    prompt = template.format(n=n, issue=spec.issue_text, public=spec.public_test,
                             import_rule=import_rule, entail_rule=_ENTAIL_RULE, **extra)
    try:
        msg = client.messages.create(model=model, max_tokens=1600,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        checks = _parse_check_array(text)[:n]
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        return checks, cost
    except Exception:  # noqa: BLE001 - generation is best-effort
        return [], 0.0


def _collects_cleanly(check_src: str, *, module_path: str, baseline_src: str,
                      extra_files: dict[str, str], root: Path) -> bool:
    """Validity filter: a check that cannot even IMPORT/collect (e.g. wrong package path) is broken,
    not discriminating. Run pytest --collect-only against the baseline; keep only checks that collect."""
    import os
    import subprocess
    ws = _build_ws(root, module_path, baseline_src, extra_files, "collect")
    (ws / "test_collect.py").write_text(check_src)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        p = subprocess.run(["python", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                            "-o", "addopts=", "test_collect.py"], cwd=ws, capture_output=True,
                           text=True, timeout=30, check=False, env=env)
        ok = p.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    return ok


def _build_ws(root: Path, module_path: str, module_src: str, extra_files: dict[str, str], tag: str) -> Path:
    ws = root / f"battery_{tag}_{time.time_ns()}"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / module_path).parent.mkdir(parents=True, exist_ok=True)
    (ws / module_path).write_text(module_src)
    for p, c in extra_files.items():
        (ws / p).parent.mkdir(parents=True, exist_ok=True)
        (ws / p).write_text(c)
    (ws / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    return ws


def _run_checks(module_src: str, checks: list[tuple[str, str]], *, module_path: str,
                extra_files: dict[str, str], root: Path, tag: str,
                per_check_timeout: int = 15, budget_s: float = 90.0) -> list[bool]:
    """Build one workspace for `module_src`, run each check file, return per-check pass flags.

    Bounded (the stall fix): each generated check is a tiny unit test, so a short per-check timeout
    (a hang fails closed) plus an overall budget keep candidate SCORING from stalling — a battery of
    ~20 checks at the old 60s ceiling could take minutes/candidate and hours over a greedy run."""
    import os
    import subprocess
    import time as _time
    ws = _build_ws(root, module_path, module_src, extra_files, tag)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out: list[bool] = []
    deadline = _time.monotonic() + budget_s
    for i, (_kind, src) in enumerate(checks):
        if _time.monotonic() > deadline:
            out.append(False)            # unrun under budget -> fail closed (never a false pass)
            continue
        name = f"test_battery_{i}.py"
        (ws / name).write_text(src)
        try:
            p = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "-o", "addopts=", name], cwd=ws, capture_output=True, text=True,
                               timeout=per_check_timeout, check=False, env=env)
            out.append(p.returncode == 0)
        except subprocess.TimeoutExpired:
            out.append(False)            # a hanging generated check fails closed
        except Exception:  # noqa: BLE001 - malformed generated test counts as not-passed
            out.append(False)
        (ws / name).unlink(missing_ok=True)
    shutil.rmtree(ws, ignore_errors=True)
    return out


_ERROR_MARKERS = ("AttributeError", "TypeError", "NameError", "ImportError", "ModuleNotFoundError",
                  "errors during collection", "error during collection")


def _run_check_kinds(module_src: str, checks: list[tuple[str, str]], *, module_path: str,
                     extra_files: dict[str, str], root: Path, tag: str,
                     per_check_timeout: int = 25, budget_s: float = 180.0) -> list[str]:
    """Per-check verdict KIND on `module_src`: 'pass' | 'assert' (behavioural disagreement, incl.
    pytest.raises DID-NOT-RAISE, and hangs) | 'error' (AttributeError/TypeError/... — the check
    mis-uses the API so it fails EVERY implementation and can never discriminate).

    Bounded (the ioutils stall fix): each check has a short timeout, and once the overall budget is
    spent the rest are marked 'error' so they get DROPPED — never silently kept as discriminating."""
    import os
    import subprocess
    import time as _time
    ws = _build_ws(root, module_path, module_src, extra_files, tag)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out: list[str] = []
    deadline = _time.monotonic() + budget_s
    for i, (_kind, src) in enumerate(checks):
        if _time.monotonic() > deadline:
            out.append("error")          # unclassified under budget -> drop (safer than mis-keeping)
            continue
        name = f"test_battery_{i}.py"
        (ws / name).write_text(src)
        try:
            p = subprocess.run(["python", "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider",
                                "-o", "addopts=", name], cwd=ws, capture_output=True, text=True,
                               timeout=per_check_timeout, check=False, env=env)
            text = p.stdout + "\n" + p.stderr
            if p.returncode == 0:
                out.append("pass")
            elif any(m in text for m in _ERROR_MARKERS) and "AssertionError" not in text:
                out.append("error")
            else:
                out.append("assert")
        except subprocess.TimeoutExpired:
            # a hang IS behavioural (e.g. the infinite-loop bug itself) — treat as assert-class
            out.append("assert")
        (ws / name).unlink(missing_ok=True)
    shutil.rmtree(ws, ignore_errors=True)
    return out


def _public_passes(module_src: str, public_test: str, *, module_path: str,
                   extra_files: dict[str, str], root: Path, tag: str) -> bool:
    ws = _build_ws(root, module_path, module_src, extra_files, f"pub_{tag}")
    (ws / "test_public.py").write_text(public_test)
    try:
        ok = _run_pytest(ws, "test_public.py")
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    return ok


def build_battery(spec: SpecLike, *, client, module_path: str, extra_files: dict[str, str],
                  baseline_src: str, public_test: str, workspace_root: Path,
                  n_example: int = 8, n_property: int = 4,
                  model: str = "claude-haiku-4-5") -> RepairBattery:
    """Synthesize the dense battery (example + property checks) and compute the buggy-baseline pass
    vector once (this defines the discriminating/guard split). Fair: spec + public test only.

    Two safeguards make the battery score a real gradient (validated by: gold should pass it): the
    generators pin the import to the public test's convention, and a collect-only validity filter
    drops any check that cannot import/collect (the dominant failure on flattened package bundles)."""
    ex, ex_cost = _generate(spec, client=client, model=model, n=n_example, template=_EXAMPLE_PROMPT)
    props, prop_cost = _generate(spec, client=client, model=model, n=n_property, template=_PROP_PROMPT)
    raw: list[tuple[str, str]] = [("example", c) for c in ex] + [("property", c) for c in props]
    # drop checks that don't even import/collect against the baseline (broken, not discriminating)
    checks = [(kind, src) for kind, src in raw
              if _collects_cleanly(src, module_path=module_path, baseline_src=baseline_src,
                                   extra_files=extra_files, root=workspace_root)]
    baseline_pass = (_run_checks(baseline_src, checks, module_path=module_path, extra_files=extra_files,
                                 root=workspace_root, tag="base") if checks else [])
    return RepairBattery(checks=checks, baseline_pass=baseline_pass, public_test=public_test,
                         module_path=module_path, extra_files=extra_files,
                         gen_cost_usd=round(ex_cost + prop_cost, 6), model=model)


def _keep_by_baseline(cands: list[str], *, want_fail: bool, module_path: str, baseline_src: str,
                      extra_files: dict[str, str], root: Path, kind: str) -> list[tuple[str, str]]:
    """Collect-filter then execution-gate candidate checks against the buggy baseline.
    want_fail=True (Otter fail-to-pass): keep only ASSERT-class failures — an error-class failure
    (hallucinated API, wrong call) fails every implementation and can never discriminate.
    want_fail=False (AssertFlip pins): keep only passes."""
    ok = [(kind, c) for c in cands
          if _collects_cleanly(c, module_path=module_path, baseline_src=baseline_src,
                               extra_files=extra_files, root=root)]
    if not ok:
        return []
    kinds = _run_check_kinds(baseline_src, ok, module_path=module_path, extra_files=extra_files,
                             root=root, tag=f"gate_{kind}")
    want = "assert" if want_fail else "pass"
    return [c for c, kk in zip(ok, kinds, strict=True) if kk == want]


def _entailment_filter(spec: SpecLike, checks: list[tuple[str, str]], idxs: list[int], *,
                       client, model: str) -> tuple[set[int], float]:
    """Self-audit: which discriminating checks assert GUESSED expectations the spec never states?
    Returns the indices (into `checks`) judged guesses, to be dropped. Fail-open (empty set)."""
    if client is None or not idxs:
        return set(), 0.0
    import json as _json
    numbered = "\n\n".join(f"### {j}\n{checks[j][1]}" for j in idxs)
    prompt = _ENTAIL_FILTER_PROMPT.format(issue=spec.issue_text, public=spec.public_test,
                                          tests=numbered)
    try:
        msg = client.messages.create(model=model, max_tokens=300,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\[[\d,\s]*\]", text)
        flagged = set(_json.loads(m.group(0))) if m else set()
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        return {j for j in flagged if j in set(idxs)}, cost
    except Exception:  # noqa: BLE001
        return set(), 0.0


def _flip_assertions(spec: SpecLike, pins: list[str], *, client, model: str) -> tuple[list[str], float]:
    """AssertFlip step 2: rewrite passing buggy-behaviour pins into spec-correct expectations."""
    if client is None or not pins:
        return [], 0.0
    import json as _json
    prompt = _FLIP_PROMPT.format(issue=spec.issue_text, tests_json=_json.dumps(pins))
    try:
        msg = client.messages.create(model=model, max_tokens=2000,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        flipped = _parse_check_array(text)[:len(pins)]
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        return flipped, cost
    except Exception:  # noqa: BLE001
        return [], 0.0


def build_battery_v2(spec: SpecLike, *, client, module_path: str, extra_files: dict[str, str],
                     baseline_src: str, public_test: str, workspace_root: Path,
                     focus_src: str = "", focus_spans: list[tuple[int, int]] | None = None,
                     n_example: int = 10, n_property: int = 4, n_invert: int = 6,
                     max_regen_rounds: int = 2, mutant_cap: int = 16,
                     min_disc: int = 5, model: str = "claude-haiku-4-5",
                     use_pbt: bool = True, rebuilds_on_invalid: int = 1) -> RepairBattery:
    """build_battery_v2 with variance control (P7 G3 finding): generation is stochastic — the same
    bundle oscillates useful<->invalid across builds (mathutils/ioutils were useful in one run,
    invalid the next, costing recoveries). An invalid battery triggers up to `rebuilds_on_invalid`
    full rebuilds (fresh sampling, ~$0.03 each); the attempt with the most discriminating checks
    wins. Total generation cost is accumulated on the returned battery."""
    best: RepairBattery | None = None
    total_cost = 0.0
    for _ in range(rebuilds_on_invalid + 1):
        bat = _build_battery_v2_once(
            spec, client=client, module_path=module_path, extra_files=extra_files,
            baseline_src=baseline_src, public_test=public_test, workspace_root=workspace_root,
            focus_src=focus_src, focus_spans=focus_spans, n_example=n_example,
            n_property=n_property, n_invert=n_invert, max_regen_rounds=max_regen_rounds,
            mutant_cap=mutant_cap, min_disc=min_disc, model=model, use_pbt=use_pbt)
        total_cost += bat.gen_cost_usd
        if best is None or bat.n_discriminating > best.n_discriminating:
            best = bat
        if best.valid:
            break
    assert best is not None
    best.gen_cost_usd = round(total_cost, 6)
    return best


def _build_battery_v2_once(spec: SpecLike, *, client, module_path: str, extra_files: dict[str, str],
                     baseline_src: str, public_test: str, workspace_root: Path,
                     focus_src: str = "", focus_spans: list[tuple[int, int]] | None = None,
                     n_example: int = 10, n_property: int = 4, n_invert: int = 6,
                     max_regen_rounds: int = 2, mutant_cap: int = 16,
                     min_disc: int = 5, model: str = "claude-haiku-4-5",
                     use_pbt: bool = True) -> RepairBattery:
    """Discriminating-by-construction battery (P7 W1). On top of v1's import-pin + collect filter:

    * Otter fail-to-pass gate — while the battery has <2 discriminating checks, regenerate showing
      the BUGGY focus region ("every check so far PASSES this buggy code; write checks it FAILS"),
      keeping ONLY checks that execute-and-fail on the baseline.
    * AssertFlip — generate tests that PASS on buggy pinning the implicated behaviour (execution-
      verified), then flip their assertions to the spec-correct expectation; keep only flips that now
      FAIL on buggy. Rejected pins/flips are dropped entirely (a pin kept as a guard would punish the
      true fix).
    * MuTAP sensitivity weights — focus-region mutants; checks whose verdicts never react to the
      region get the floor weight (CPU-only).
    * `valid=False` (never a vacuous 1.0 score) when <2 discriminating checks survive everything.
    """
    focus = focus_src or baseline_src[:6000]
    ex, c1 = _generate(spec, client=client, model=model, n=n_example, template=_EXAMPLE_PROMPT)
    props, c2 = _generate(spec, client=client, model=model, n=n_property, template=_PROP_PROMPT)
    cost = c1 + c2
    raw: list[tuple[str, str]] = [("example", c) for c in ex] + [("property", c) for c in props]
    checks = [(k, s) for k, s in raw
              if _collects_cleanly(s, module_path=module_path, baseline_src=baseline_src,
                                   extra_files=extra_files, root=workspace_root)]
    # kind-aware baseline triage: 'pass' -> guard; 'assert' -> discriminating; 'error' -> DROP (the
    # check mis-uses the API — hallucinated function/wrong signature — so it fails gold too)
    kinds = (_run_check_kinds(baseline_src, checks, module_path=module_path,
                              extra_files=extra_files, root=workspace_root, tag="base")
             if checks else [])
    checks = [chk for chk, kk in zip(checks, kinds, strict=True) if kk != "error"]
    baseline_pass = [kk == "pass" for kk in kinds if kk != "error"]

    def n_disc() -> int:
        return sum(1 for p in baseline_pass if not p)

    # Otter fail-to-pass regen toward min_disc: a battery with only 1-2 discriminating checks is
    # fragile — a single wrong expectation dominates the gradient; volume dilutes wrong checks and
    # gives the audits something to keep (G1 finding: the harmful batteries were all tiny)
    for _ in range(max_regen_rounds):
        if n_disc() >= min_disc:
            break
        regen, c = _generate(spec, client=client, model=model, n=5, template=_REGEN_PROMPT, focus=focus)
        cost += c
        kept = _keep_by_baseline(regen, want_fail=True, module_path=module_path,
                                 baseline_src=baseline_src, extra_files=extra_files,
                                 root=workspace_root, kind="f2p")
        checks += kept
        baseline_pass += [False] * len(kept)

    # AssertFlip: pins must PASS on buggy; flips must FAIL on buggy (discriminating by construction)
    if n_disc() < min_disc + 1 and n_invert > 0:
        pins_raw, c = _generate(spec, client=client, model=model, n=n_invert, template=_PIN_PROMPT, focus=focus)
        cost += c
        pins = [s for _k, s in _keep_by_baseline(pins_raw, want_fail=False, module_path=module_path,
                                                 baseline_src=baseline_src, extra_files=extra_files,
                                                 root=workspace_root, kind="pin")]
        flipped, c = _flip_assertions(spec, pins, client=client, model=model)
        cost += c
        kept = _keep_by_baseline(flipped, want_fail=True, module_path=module_path,
                                 baseline_src=baseline_src, extra_files=extra_files,
                                 root=workspace_root, kind="flip")
        checks += kept
        baseline_pass += [False] * len(kept)

    # PBT phase (P12 W1): when EXAMPLE/flip tests still left the battery thin, let Hypothesis SEARCH the
    # inputs that break a metamorphic/invariant property. Admitted ONLY when the property is FALSIFIED on
    # the buggy baseline (proven discriminator) — properties that hold become guards. This is the lever
    # for the bugs whose triggering input the LLM can't guess by hand (P7's non-discriminating ~64%).
    if use_pbt and n_disc() < min_disc + 2:
        from acp.verification.property_checks import (  # lazy: property_checks imports from this module
            admit_discriminating,
            generate_properties,
            vet_properties,
        )
        props, c = generate_properties(spec, client=client, model=model, n_prop=n_property, focus=focus)
        cost += c
        pbt_disc, pbt_guard = admit_discriminating(
            props, baseline_src=baseline_src, module_path=module_path,
            extra_files=extra_files, root=workspace_root, tag="pbt")
        # property-specific entailment vet: drop over-specified PBT discriminators a CORRECT impl could
        # violate (the strutils harm — a discriminating-by-falsification check that also rejects gold)
        pbt_disc, _dropped, vc = vet_properties(spec, pbt_disc, client=client, model=model)
        cost += vc
        checks += pbt_disc + pbt_guard
        baseline_pass += [False] * len(pbt_disc) + [True] * len(pbt_guard)

    # entailment self-filter: drop discriminating checks whose expectations are guesses the spec
    # never states (G1 finding: ambiguous issues -> plausible-but-wrong exact values fail the true fix)
    disc_idx = [j for j, p in enumerate(baseline_pass) if not p]
    flagged, fcost = _entailment_filter(spec, checks, disc_idx, client=client, model=model)
    cost += fcost
    if flagged and len(flagged) < len(disc_idx):   # never drop the whole discriminating set
        checks = [chk for j, chk in enumerate(checks) if j not in flagged]
        baseline_pass = [p for j, p in enumerate(baseline_pass) if j not in flagged]
    if 0 < n_disc() <= 3:
        # small discriminating sets are fragile (one wrong expectation dominates the gradient):
        # a second independent audit; union of flags
        disc_idx = [j for j, p in enumerate(baseline_pass) if not p]
        flagged2, fcost2 = _entailment_filter(spec, checks, disc_idx, client=client, model=model)
        cost += fcost2
        if flagged2 and len(flagged2) < len(disc_idx):
            checks = [chk for j, chk in enumerate(checks) if j not in flagged2]
            baseline_pass = [p for j, p in enumerate(baseline_pass) if j not in flagged2]

    # validity floor 3: across five G1 runs every harmful battery (gold-rejecting) had disc<=2 while
    # useful ones landed at disc>=4 — tiny discriminating sets are coin-flips; declare them invalid
    # (safe: the router escalates) rather than risk a wrong gradient
    valid = n_disc() >= 3
    weights: list[float] = []
    mut_info: dict = {}
    if valid and checks:
        from acp.verification.battery_mutation import sensitivity_weights
        weights, mut_info = sensitivity_weights(baseline_src, checks, baseline_pass,
                                                module_path=module_path, extra_files=extra_files,
                                                root=workspace_root, spans=focus_spans, cap=mutant_cap)
    return RepairBattery(checks=checks, baseline_pass=baseline_pass, public_test=public_test,
                         module_path=module_path, extra_files=extra_files,
                         gen_cost_usd=round(cost, 6), model=model, valid=valid,
                         invalid_reason=("" if valid else "non_discriminating"),
                         check_weights=weights, mutation_info=mut_info)


def score_candidate(battery: RepairBattery, *, candidate_src: str, workspace_root: Path,
                    candidate_id: str, diff: str | None = None,
                    surviving_mask: list[bool] | None = None) -> BatteryScore:
    """Continuous value in [0,1] for one candidate. `surviving_mask` (Phase 1 consensus) optionally
    drops likely-bad checks; default keeps all. Public-test failure or adversarial-high => score 0."""
    adv_high = False
    if diff:
        from acp.schemas.workspace import DiffBundle
        adv_high = has_high_severity(scan_diff(DiffBundle(unified_diff=diff, changed_files=[])))
    public_pass = _public_passes(candidate_src, battery.public_test, module_path=battery.module_path,
                                 extra_files=battery.extra_files, root=workspace_root, tag=candidate_id)
    cand_pass = (_run_checks(candidate_src, battery.checks, module_path=battery.module_path,
                             extra_files=battery.extra_files, root=workspace_root, tag=candidate_id)
                 if battery.checks else [])
    results: list[CheckResult] = []
    d_surv = d_pass = g_surv = g_pass = 0
    dw_sum = dw_hit = gw_sum = gw_hit = 0.0      # mutant-sensitivity-weighted tallies (v2)
    for j, (kind, _src) in enumerate(battery.checks):
        surviving = True if surviving_mask is None else surviving_mask[j]
        base_ok = battery.baseline_pass[j]
        role = "guard" if base_ok else "discriminating"
        passed = cand_pass[j]
        results.append(CheckResult(check_id=f"{role[:4]}_{j}", kind=kind, role=role, passed=passed,
                                   surviving=surviving,
                                   detail=("baseline+candidate both fail" if (role == "discriminating" and not passed)
                                           else "candidate broke a behaviour the buggy code kept" if (role == "guard" and not passed)
                                           else "ok")))
        if not surviving:
            continue
        w = battery.weight(j)
        if role == "discriminating":
            d_surv += 1
            d_pass += int(passed)
            dw_sum += w
            dw_hit += w * int(passed)
        else:
            g_surv += 1
            g_pass += int(passed)
            gw_sum += w
            gw_hit += w * int(passed)
    disc = (dw_hit / dw_sum) if dw_sum else 1.0
    guard = (gw_hit / gw_sum) if gw_sum else 1.0
    if adv_high or not public_pass:
        score = 0.0
    elif not battery.valid:
        # an invalid (non-discriminating) battery can never emit a vacuous 1.0 — cap at the public
        # contribution so the search degrades to public-test-driven and telemetry/routers escalate
        score = round(_W_PUBLIC * 1.0, 4)
    else:
        score = round(_W_DISCRIM * disc + _W_GUARD * guard + _W_PUBLIC * 1.0, 4)
    return BatteryScore(candidate_id=candidate_id, score=score, public_pass=public_pass,
                        adversarial_high=adv_high, n_discrim_surviving=d_surv, n_discrim_passed=d_pass,
                        n_guard_surviving=g_surv, n_guard_passed=g_pass, results=results,
                        disc_frac=round(disc, 4), guard_frac=round(guard, 4),
                        battery_valid=battery.valid)


def score_pool(battery: RepairBattery, candidates: list[dict], *, workspace_root: Path,
               consensus_floor: float = 0.5) -> dict[str, BatteryScore]:
    """Score several candidates and apply cross-candidate consensus to GUARD checks only (a guard
    check < `consensus_floor` of candidates pass is dropped as likely-wrong). Discriminating checks
    are exempt: most candidates are wrong fixes, so a buggy-like majority would vote out exactly the
    checks that detect the bug (Kimi-Dev W4 fix)."""
    raw = {c["id"]: _run_checks(c["src"], battery.checks, module_path=battery.module_path,
                                extra_files=battery.extra_files, root=workspace_root, tag=c["id"])
           for c in candidates} if battery.checks else {c["id"]: [] for c in candidates}
    n = len(battery.checks)
    ids = [c["id"] for c in candidates]
    floor = max(1, int(round(consensus_floor * len(ids))))
    mask = [(not battery.baseline_pass[j])             # discriminating: always survives consensus
            or sum(1 for cid in ids if raw[cid][j]) >= floor for j in range(n)]
    out: dict[str, BatteryScore] = {}
    for c in candidates:
        out[c["id"]] = score_candidate(battery, candidate_src=c["src"], workspace_root=workspace_root,
                                       candidate_id=c["id"], diff=c.get("diff"), surviving_mask=mask)
    return out
