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

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from acp.verification.adversarial import has_high_severity, scan_diff
from acp.verification.independent_proof import _parse_check_array, _run_pytest, generate_checks


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

    @property
    def n_discriminating(self) -> int:
        return sum(1 for p in self.baseline_pass if not p)

    @property
    def n_guard(self) -> int:
        return sum(1 for p in self.baseline_pass if p)


_PROP_PROMPT = (
    "You are a senior test engineer writing PROPERTY-BASED / metamorphic tests. Given an issue spec "
    "and one public test (for the import), write {n} NEW pytest tests that assert INVARIANTS implied "
    "by the spec rather than single input/output pairs — e.g. idempotence (f(f(x))==f(x)), round-trip "
    "(decode(encode(x))==x), monotonicity, bounds/range, type-stability, or behaviour on empty / "
    "singleton / boundary inputs. Each test must be fully self-contained (include the import), must "
    "NOT reference any hidden/secret test, and must only use behaviour the spec guarantees.\n\n"
    "Return ONLY a JSON array of strings; each string is a complete test file (import + one "
    "`def test_...`).\n\nISSUE:\n{issue}\n\nEXISTING PUBLIC TEST (for the import):\n{public}\n"
)


def _generate_properties(spec: SpecLike, *, client, model: str = "claude-haiku-4-5", n: int = 4):
    """Property/metamorphic checks. Mirrors generate_checks but with the invariant-focused prompt."""
    if client is None or n <= 0:
        return [], 0.0
    prompt = _PROP_PROMPT.format(n=n, issue=spec.issue_text, public=spec.public_test)
    try:
        msg = client.messages.create(model=model, max_tokens=1500,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        checks = _parse_check_array(text)[:n]
        usage = getattr(msg, "usage", None)
        cost = round((getattr(usage, "input_tokens", 0) or 0) * 1.0 / 1e6
                     + (getattr(usage, "output_tokens", 0) or 0) * 5.0 / 1e6, 6)
        return checks, cost
    except Exception:  # noqa: BLE001 - generation is best-effort
        return [], 0.0


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
                extra_files: dict[str, str], root: Path, tag: str) -> list[bool]:
    """Build one workspace for `module_src`, run each check file, return per-check pass flags."""
    ws = _build_ws(root, module_path, module_src, extra_files, tag)
    out: list[bool] = []
    for i, (_kind, src) in enumerate(checks):
        name = f"test_battery_{i}.py"
        (ws / name).write_text(src)
        try:
            out.append(_run_pytest(ws, name))
        except Exception:  # noqa: BLE001 - malformed generated test counts as not-passed
            out.append(False)
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
    vector once (this defines the discriminating/guard split). Fair: spec + public test only."""
    gen = generate_checks(spec, client=client, n=n_example, model=model)
    props, prop_cost = _generate_properties(spec, client=client, n=n_property, model=model)
    checks: list[tuple[str, str]] = [("example", c) for c in gen.checks] + [("property", c) for c in props]
    baseline_pass = (_run_checks(baseline_src, checks, module_path=module_path, extra_files=extra_files,
                                 root=workspace_root, tag="base") if checks else [])
    return RepairBattery(checks=checks, baseline_pass=baseline_pass, public_test=public_test,
                         module_path=module_path, extra_files=extra_files,
                         gen_cost_usd=round(gen.cost_usd + prop_cost, 6), model=model)


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
        if role == "discriminating":
            d_surv += 1
            d_pass += int(passed)
        else:
            g_surv += 1
            g_pass += int(passed)
    if adv_high or not public_pass:
        score = 0.0
    else:
        disc = (d_pass / d_surv) if d_surv else 1.0
        guard = (g_pass / g_surv) if g_surv else 1.0
        score = round(_W_DISCRIM * disc + _W_GUARD * guard + _W_PUBLIC * 1.0, 4)
    return BatteryScore(candidate_id=candidate_id, score=score, public_pass=public_pass,
                        adversarial_high=adv_high, n_discrim_surviving=d_surv, n_discrim_passed=d_pass,
                        n_guard_surviving=g_surv, n_guard_passed=g_pass, results=results)


def score_pool(battery: RepairBattery, candidates: list[dict], *, workspace_root: Path,
               consensus_floor: float = 0.5) -> dict[str, BatteryScore]:
    """Score several candidates and apply cross-candidate consensus (a check < `consensus_floor` of
    candidates pass is dropped as likely-wrong — lifted from independent_proof.proxy_evaluate). Used
    by the search (Phase 1) where multiple candidates exist; hardens the signal against bad checks."""
    raw = {c["id"]: _run_checks(c["src"], battery.checks, module_path=battery.module_path,
                                extra_files=battery.extra_files, root=workspace_root, tag=c["id"])
           for c in candidates} if battery.checks else {c["id"]: [] for c in candidates}
    n = len(battery.checks)
    ids = [c["id"] for c in candidates]
    floor = max(1, int(round(consensus_floor * len(ids))))
    mask = [sum(1 for cid in ids if raw[cid][j]) >= floor for j in range(n)]
    out: dict[str, BatteryScore] = {}
    for c in candidates:
        out[c["id"]] = score_candidate(battery, candidate_src=c["src"], workspace_root=workspace_root,
                                       candidate_id=c["id"], diff=c.get("diff"), surviving_mask=mask)
    return out
