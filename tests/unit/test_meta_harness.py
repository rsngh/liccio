"""Meta-Harness / harness optimization (Alpha 24 area 4)."""

from __future__ import annotations

from acp.training.meta_harness import (
    HarnessConfig,
    HarnessPatch,
    evaluate_patch,
    safety_gate,
    search_harness_patches,
)

TASKS = ["t1", "t2", "t3"]


def _eval(cfg: HarnessConfig, task: str) -> float:
    # a higher 'verbosity' helps t1/t2 but hurts t3 (a regression risk)
    v = cfg.params.get("verbosity", 0)
    base = {"t1": 0.5, "t2": 0.5, "t3": 0.9}[task]
    if task == "t3":
        return max(0.0, base - 0.1 * v)
    return min(1.0, base + 0.2 * v)


def test_eval_script_touching_patch_is_rejected() -> None:
    p = HarnessPatch({"verbosity": 1}, touches_eval_scripts=True)
    assert not safety_gate(p)[0]
    r = evaluate_patch(HarnessConfig({"verbosity": 0}), p, tasks=TASKS, task_eval_fn=_eval)
    assert not r.accepted and "eval scripts" in r.reject_reason


def test_gate_weakening_patch_is_rejected() -> None:
    p = HarnessPatch({"verbosity": 1}, weakens_gate=True)
    r = evaluate_patch(HarnessConfig({"verbosity": 0}), p, tasks=TASKS, task_eval_fn=_eval)
    assert not r.accepted and not r.safe


def test_patch_with_negative_transfer_is_rejected() -> None:
    # verbosity=3 helps t1/t2 a lot but regresses t3 below the bound
    p = HarnessPatch({"verbosity": 3})
    r = evaluate_patch(HarnessConfig({"verbosity": 0}), p, tasks=TASKS, task_eval_fn=_eval,
                       max_regression=0.05)
    assert r.improved and not r.regression_clean and not r.accepted
    assert r.worst_task_delta < 0


def test_improving_patch_within_bound_is_accepted() -> None:
    p = HarnessPatch({"verbosity": 1})  # small bump; t3 drops only 0.1 -> within 0.15 bound
    r = evaluate_patch(HarnessConfig({"verbosity": 0}), p, tasks=TASKS, task_eval_fn=_eval,
                       max_regression=0.15)
    assert r.accepted and r.patched_score > r.baseline_score


def test_search_picks_best_accepted_patch() -> None:
    patches = [HarnessPatch({"verbosity": 1}), HarnessPatch({"verbosity": 3}),
               HarnessPatch({"verbosity": 0})]
    out = search_harness_patches(HarnessConfig({"verbosity": 0}), patches, tasks=TASKS,
                                 task_eval_fn=_eval, max_regression=0.15)
    assert out["n_accepted"] >= 1 and out["best_patch"] == {"verbosity": 1}
