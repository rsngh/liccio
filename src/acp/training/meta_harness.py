"""Meta-Harness / harness optimization (Alpha 24 area 4).

Meta-Harness searches over harness CODE/config using source, scores, and execution traces;
Life-Harness turns failures into reusable runtime interventions without touching weights.
ACP applies this to its own harness knobs (prompt assembly, tool schema, trace
summarization, verification policy, retry/timeout) — proposing a patch, scoring it on a
per-task suite, and accepting it only if it improves the mean WITHOUT regressing any task
(bounded negative transfer) AND passes hard safety gates.

Safety gates (a patch failing any is rejected, never applied):
- no patch may touch eval scripts;
- no patch may weaken the measurement/verification gate;
- the patch must improve mean score and keep negative transfer within a bound;
- accepted patches are canary-gated before deployment (recorded here, enforced elsewhere).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class HarnessConfig:
    params: dict = field(default_factory=dict)

    def with_patch(self, changes: dict) -> HarnessConfig:
        merged = dict(self.params)
        merged.update(changes)
        return HarnessConfig(params=merged)


@dataclass
class HarnessPatch:
    changes: dict
    rationale: str = ""
    touches_eval_scripts: bool = False
    weakens_gate: bool = False


def safety_gate(patch: HarnessPatch) -> tuple[bool, str]:
    if patch.touches_eval_scripts:
        return False, "patch touches eval scripts"
    if patch.weakens_gate:
        return False, "patch weakens measurement/verification gate"
    return True, "safe"


# task_eval_fn(config, task) -> score in [0, 1]
TaskEvalFn = Callable[[HarnessConfig, str], float]


@dataclass
class HarnessPatchResult:
    accepted: bool
    safe: bool
    improved: bool
    regression_clean: bool          # no task regressed beyond the bound
    baseline_score: float
    patched_score: float
    worst_task_delta: float
    per_task: dict = field(default_factory=dict)
    reject_reason: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def evaluate_patch(config: HarnessConfig, patch: HarnessPatch, *, tasks: list,
                   task_eval_fn: TaskEvalFn, max_regression: float = 0.0
                   ) -> HarnessPatchResult:
    """Score a patch per-task; accept only if safe, improving, and regression-bounded."""
    safe, reason = safety_gate(patch)
    patched = config.with_patch(patch.changes)
    base = {t: task_eval_fn(config, t) for t in tasks}
    new = {t: task_eval_fn(patched, t) for t in tasks}
    base_mean = round(sum(base.values()) / len(tasks), 4) if tasks else 0.0
    new_mean = round(sum(new.values()) / len(tasks), 4) if tasks else 0.0
    deltas = {t: round(new[t] - base[t], 4) for t in tasks}
    worst = min(deltas.values()) if deltas else 0.0
    improved = new_mean > base_mean + 1e-9
    regression_clean = worst >= -max_regression - 1e-9   # negative-transfer bound
    accepted = bool(safe and improved and regression_clean)
    return HarnessPatchResult(
        accepted=accepted, safe=safe, improved=improved, regression_clean=regression_clean,
        baseline_score=base_mean, patched_score=new_mean, worst_task_delta=round(worst, 4),
        per_task={t: {"base": round(base[t], 4), "patched": round(new[t], 4),
                      "delta": deltas[t]} for t in tasks},
        reject_reason=(None if accepted else
                       (reason if not safe else
                        ("no improvement" if not improved else "negative transfer"))))


def search_harness_patches(config: HarnessConfig, patches: list, *, tasks: list,
                           task_eval_fn: TaskEvalFn, max_regression: float = 0.05
                           ) -> dict:
    """Evaluate candidate patches; return the best ACCEPTED one (or None) + all results."""
    results = [(p, evaluate_patch(config, p, tasks=tasks, task_eval_fn=task_eval_fn,
                                  max_regression=max_regression)) for p in patches]
    accepted = [(p, r) for p, r in results if r.accepted]
    best = max(accepted, key=lambda pr: pr[1].patched_score) if accepted else None
    return {"best_patch": (None if best is None else best[0].changes),
            "best_result": (None if best is None else best[1].to_dict()),
            "n_candidates": len(patches), "n_accepted": len(accepted),
            "all": [{"changes": p.changes, **r.to_dict()} for p, r in results]}
