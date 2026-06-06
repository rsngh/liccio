"""Tests for the capability matrix (alpha-7 WS2)."""

from __future__ import annotations

import json

from acp.routing.capability_matrix import MIN_SAMPLE, CapabilityMatrix
from acp.schemas.learning import PostMergeOutcome


def _report() -> dict:
    """A synthetic bakeoff v2-shaped report.

    bugfix/medium: adapter_a has 6 runs (4 successes), adapter_b has 6 runs
    (1 success). feature/low: adapter_a has only 2 runs (low sample).
    """
    cells: list[dict] = []
    for i in range(6):
        cells.append({
            "task": "t1", "task_type": "bugfix", "risk": "medium",
            "adapter": "adapter_a", "success": i < 4,
            "cost_usd": 0.10, "latency_s": 2.0,
            "human_review_required": i == 0,
        })
    for i in range(6):
        cells.append({
            "task": "t1", "task_type": "bugfix", "risk": "medium",
            "adapter": "adapter_b", "success": i < 1,
            "cost_usd": 0.50, "latency_s": 5.0,
            "human_review_required": False,
        })
    for _i in range(2):
        cells.append({
            "task": "t2", "task_type": "feature", "risk": "low",
            "adapter": "adapter_a", "success": True,
            "cost_usd": 0.20, "latency_s": 3.0,
            "human_review_required": False,
        })
    return {"cells": cells}


def test_builds_and_aggregates() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report(), repo_type="python_lib")
    cells = {(c.task_type, c.agent_class): c for c in m.cells()}
    a = cells[("bugfix", "adapter_a")]
    assert a.sample_size == 6
    assert a.success_rate == round(4 / 6, 4)
    assert a.cost == 0.10
    assert a.latency == 2.0
    assert a.human_review_rate == round(1 / 6, 4)
    assert a.repo_type == "python_lib"
    assert a.sufficient_data is True


def test_low_sample_flagged() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    feature = next(c for c in m.cells() if c.task_type == "feature")
    assert feature.sample_size == 2 < MIN_SAMPLE
    assert feature.sufficient_data is False
    assert "low_sample" in feature.flags


def test_best_for_skips_low_sample() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    # bugfix/medium: adapter_a (4/6) beats adapter_b (1/6)
    best, reason = m.best_for("bugfix", "medium", "unknown")
    assert best is not None
    assert best.agent_class == "adapter_a"
    assert "confident" in reason
    # feature/low has only a low-sample cell -> refuse to recommend
    none, reason2 = m.best_for("feature", "low", "unknown")
    assert none is None
    assert "low_sample" in reason2


def test_update_from_outcomes_raises_failure_and_flips_best() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    a = next(c for c in m.cells() if c.agent_class == "adapter_a"
             and c.task_type == "bugfix")
    b = next(c for c in m.cells() if c.agent_class == "adapter_b"
             and c.task_type == "bugfix")
    # adapter_a was best by success. Now it reverts in the field a lot.
    a_outcomes = [PostMergeOutcome(task_id="t1", reverted=True) for _ in range(5)]
    b_outcomes = [PostMergeOutcome(task_id="t1", reverted=False) for _ in range(5)]
    n = m.update_from_outcomes(
        a_outcomes, task_keys={"t1": a.key()})
    m.update_from_outcomes(b_outcomes, task_keys={"t1": b.key()})
    assert n == 5
    assert a.post_merge_failure_rate == 1.0
    assert a.post_merge_sample_size == 5
    assert b.post_merge_failure_rate == 0.0
    # adapter_a's success (0.67) minus failure (1.0) = -0.33; adapter_b 0.167-0 > that
    best, _ = m.best_for("bugfix", "medium", "unknown")
    assert best is not None
    assert best.agent_class == "adapter_b"


def test_attach_ope_sets_column() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    a = next(c for c in m.cells() if c.agent_class == "adapter_a"
             and c.task_type == "bugfix")
    updated = m.attach_ope({"per_cell": {a.key_str(): {"estimate": 0.42}}})
    assert updated == 1
    assert a.ope_estimated_reward == 0.42
    # scalar form also works
    updated2 = m.attach_ope({a.key_str(): 0.9})
    assert updated2 == 1
    assert a.ope_estimated_reward == 0.9


def test_to_dict_json_serializable() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    m.update_from_outcomes([PostMergeOutcome(task_id="t1", reverted=True)])
    d = m.to_dict()
    s = json.dumps(d)  # must not raise
    assert d["min_sample"] == MIN_SAMPLE
    assert d["n_cells"] == len(m.cells())
    assert isinstance(json.loads(s)["cells"][0]["last_updated"], str)


def test_explain_ranks_cells() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    out = m.explain(("bugfix", "medium", "unknown"))
    assert out["n_cells"] == 2
    assert out["ranked"][0]["agent_class"] == "adapter_a"
    assert out["best"]["agent_class"] == "adapter_a"


def test_harness_benefit_metrics_populate_from_signals() -> None:
    # WS6: cells carrying harness signals -> HAR/HFR/PWL on the capability cell.
    from acp.routing.capability_matrix import CapabilityMatrix
    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
              "is_harness": True, "context_strategy": "hybrid_keyword_embedding",
              "success": i < 5, "cost_usd": 0.001, "latency_s": 3.0,
              "tool_calls": 2 if i < 5 else 0,  # one attempt didn't activate
              "file_reads": 1, "commands": 1} for i in range(6)]
    m = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    cell = m.cells()[0]
    assert cell.har == round(5 / 6, 4)          # 5/6 activated
    assert cell.pwl == 1.0                       # all activated attempts solved
    assert "har" in cell.to_dict()


def test_non_harness_cells_have_no_benefit_metrics() -> None:
    from acp.routing.capability_matrix import CapabilityMatrix
    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "fake",
              "is_harness": False, "context_strategy": "minimal",
              "success": False, "cost_usd": 0.0, "latency_s": 0.0} for _ in range(3)]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": cells}).cells()[0]
    assert cell.har is None and cell.hfr is None and cell.pwl is None


def _cell(adapter, succ, cost, lat, n=5):
    from acp.routing.capability_matrix import CapabilityCell
    c = CapabilityCell(task_type="bugfix", risk_level="medium", repo_type="python_package",
                       agent_class=adapter, context_strategy="hybrid", verification_policy="strict",
                       success_rate=succ, cost=cost, latency=lat, sample_size=n,
                       sufficient_data=True)
    return c


def test_score_cost_tiebreak_prefers_cheaper_on_equal_success() -> None:
    # Equal success -> cheaper+faster cell scores higher (cost-optimal route).
    from acp.routing.capability_matrix import CapabilityMatrix
    m = CapabilityMatrix()
    cheap = _cell("openai_harness", 1.0, 0.001, 5.0)
    pricey = _cell("claude_harness", 1.0, 0.0135, 7.0)
    assert m._score(cheap) > m._score(pricey)


def test_score_tiebreak_never_overrides_real_success_gap() -> None:
    # A genuine success gap (>= one sample) must dominate the cost tiebreak, even
    # when the better adapter is far more expensive.
    from acp.routing.capability_matrix import CapabilityMatrix
    m = CapabilityMatrix()
    capable_pricey = _cell("claude_harness", 1.0, 0.05, 18.0)
    cheap_worse = _cell("openai_harness", 0.2, 0.006, 23.0)
    assert m._score(capable_pricey) > m._score(cheap_worse)


def test_timed_out_rows_excluded_from_capability_metrics() -> None:
    # A wall-clock timeout is infra latency, not a solve failure: it must not drag
    # down success_rate. Here 2 real solves + 1 timeout -> success_rate 1.0, n=2.
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [
        {"task_type": "bugfix", "adapter": "openai_harness", "success": True,
         "status": "succeeded", "cost_usd": 0.001, "latency_s": 5.0},
        {"task_type": "bugfix", "adapter": "openai_harness", "success": True,
         "status": "succeeded", "cost_usd": 0.001, "latency_s": 6.0},
        {"task_type": "bugfix", "adapter": "openai_harness", "success": False,
         "status": "timed_out", "cost_usd": 0.0, "latency_s": 120.0},
    ]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.success_rate == 1.0
    assert cell.sample_size == 2  # the timeout is dropped, not counted as failure


def test_all_timeout_cell_is_low_sample_not_zero_success() -> None:
    # If every attempt timed out, the cell has no usable evidence -> sample_size 0
    # and not recommended, rather than a misleading success_rate 0.0.
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [{"task_type": "bugfix", "adapter": "openai_harness", "success": False,
             "status": "timed_out", "cost_usd": 0.0, "latency_s": 120.0} for _ in range(3)]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.sample_size == 0
    assert not cell.sufficient_data


def test_timeout_that_solved_is_kept_as_success() -> None:
    # The agent wrote a correct fix (verified) then a later call hung -> the work
    # was done; it must count as a success, not be dropped as inconclusive.
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [
        {"task_type": "bugfix", "adapter": "openai_harness", "success": True,
         "status": "timed_out", "timed_out": True, "tool_calls": 2,
         "cost_usd": 0.001, "latency_s": 63.0},
        {"task_type": "bugfix", "adapter": "openai_harness", "success": True,
         "status": "succeeded", "tool_calls": 2, "cost_usd": 0.001, "latency_s": 5.0},
    ]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.sample_size == 2 and cell.success_rate == 1.0


def test_timeout_with_activity_but_no_solve_counts_as_failure() -> None:
    # Did work (tool calls) but did not solve before timing out -> genuine
    # non-completion, kept as a failure (not excluded as infra).
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [
        {"task_type": "bugfix", "adapter": "openai_harness", "success": False,
         "status": "timed_out", "timed_out": True, "tool_calls": 4,
         "cost_usd": 0.001, "latency_s": 60.0},
        {"task_type": "bugfix", "adapter": "openai_harness", "success": True,
         "status": "succeeded", "tool_calls": 2, "cost_usd": 0.001, "latency_s": 5.0},
    ]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.sample_size == 2 and cell.success_rate == 0.5


def test_v2_measurement_quality_columns() -> None:
    # Conclusive vs inconclusive split + infra rate + cost-per-success (WS6 v2).
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [
        {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
         "success": True, "status": "succeeded", "tool_calls": 2, "cost_usd": 0.002},
        {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
         "success": False, "status": "failed", "tool_calls": 3, "cost_usd": 0.001},
        {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
         "success": False, "status": "timed_out", "timed_out": True, "tool_calls": 0,
         "error": "timed out", "cost_usd": 0.0},
    ]
    c = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert c.conclusive_sample_size == 2     # 1 success + 1 task_failure
    assert c.inconclusive_sample_size == 1   # the first-call hang
    assert c.infra_failure_rate == round(1 / 3, 4)
    # Total conclusive cost (0.002 + 0.001) per success (1) = realistic cost/success.
    assert c.cost_per_conclusive_success == 0.003
    assert c.success_rate == 0.5


def test_v3_columns_and_recommendation_stable_under_infra_noise() -> None:
    # WS4: injecting infra timeouts must not change the recommended adapter or its
    # conclusive success_rate (only measurement_quality_mean / infra rate move).
    from acp.routing.capability_matrix import CapabilityMatrix

    def rows(extra_infra):
        base = [{"task_type": "bugfix", "risk": "medium", "adapter": a,
                 "is_harness": True, "context_strategy": "hybrid", "success": s,
                 "status": "succeeded" if s else "failed", "tool_calls": 2,
                 "commands": 1, "file_reads": 1, "cost_usd": 0.001}
                for a, n_ok in (("openai_harness", 6), ("claude_harness", 6))
                for s in [True] * n_ok]
        base += [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
                  "is_harness": True, "context_strategy": "hybrid", "success": False,
                  "status": "timed_out", "timed_out": True, "tool_calls": 0,
                  "error": "timed out", "cost_usd": 0.0} for _ in range(extra_infra)]
        return base

    clean = CapabilityMatrix.from_bakeoff_report({"cells": rows(0)})
    noisy = CapabilityMatrix.from_bakeoff_report({"cells": rows(10)})
    bc, _ = clean.best_for("bugfix", "medium", "python_package")
    bn, _ = noisy.best_for("bugfix", "medium", "python_package")
    # Same recommendation + same conclusive success_rate despite 10 infra timeouts.
    oc = [c for c in clean.cells() if c.agent_class == "openai_harness"][0]
    on = [c for c in noisy.cells() if c.agent_class == "openai_harness"][0]
    assert oc.success_rate == on.success_rate == 1.0
    assert on.infra_failure_rate > 0 and on.measurement_quality_mean < oc.measurement_quality_mean


def test_low_measurement_quality_cell_is_not_recommended() -> None:
    # WS4 hardening: a confident cell whose measurement_quality_mean is below the
    # floor is not recommended even though its conclusive sample is sufficient.
    from acp.routing.capability_matrix import MIN_MEASUREMENT_QUALITY, CapabilityMatrix
    rows = [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
             "is_harness": True, "context_strategy": "hybrid", "success": True,
             "status": "succeeded", "tool_calls": 2, "commands": 1, "file_reads": 1,
             "cost_usd": 0.001} for _ in range(6)]
    m = CapabilityMatrix.from_bakeoff_report({"cells": rows})
    cell = m.cells()[0]
    assert cell.sufficient_data
    # Force a low measurement-quality score (a noisy run).
    cell.measurement_quality_mean = MIN_MEASUREMENT_QUALITY - 0.1
    best, reason = m.best_for(*m.cells()[0].task_key())
    assert best is None and "measurement_quality" in reason


def test_high_measurement_quality_cell_is_recommended() -> None:
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
             "is_harness": True, "context_strategy": "hybrid", "success": True,
             "status": "succeeded", "tool_calls": 2, "commands": 1, "file_reads": 1,
             "cost_usd": 0.001} for _ in range(6)]
    m = CapabilityMatrix.from_bakeoff_report({"cells": rows})
    best, reason = m.best_for(*m.cells()[0].task_key())
    assert best is not None and "trustworthy" in reason


def test_skill_aware_cell_attribution() -> None:
    # Round 16: cells carrying skill_id/version attribute evidence to the skill.
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [{"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
             "success": True, "status": "succeeded", "tool_calls": 2, "commands": 1,
             "file_reads": 1, "cost_usd": 0.001, "skill_id": "skill_abc",
             "skill_version": 2} for _ in range(5)]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.skill_id == "skill_abc" and cell.skill_version == 2


def test_no_skill_cell_has_none_attribution() -> None:
    from acp.routing.capability_matrix import CapabilityMatrix
    rows = [{"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
             "success": True, "status": "succeeded", "tool_calls": 2, "commands": 1,
             "file_reads": 1, "cost_usd": 0.001} for _ in range(5)]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": rows}).cells()[0]
    assert cell.skill_id is None and cell.skill_version is None


def test_cell_reports_wilson_ci_robust_at_small_n() -> None:
    # Statistical robustness (Alpha 25+): a 3/3 cell must report a WIDE interval, not 1.0,
    # so a lucky small sample is never mistaken for a well-sampled cell.
    from acp.routing.capability_matrix import CapabilityCell
    small = CapabilityCell("bugfix", "low", "x", "openai_harness", "hybrid", "standard",
                           success_rate=1.0, conclusive_sample_size=3, sample_size=3)
    small.recompute_flags()
    assert small.success_rate_ci_low < 0.5 and small.success_rate_ci_high == 1.0
    assert not small.sufficient_data
    big = CapabilityCell("bugfix", "low", "x", "openai_harness", "hybrid", "standard",
                         success_rate=0.95, conclusive_sample_size=200, sample_size=200)
    big.recompute_flags()
    assert big.success_rate_ci_high - big.success_rate_ci_low < 0.1   # tight at large n
    assert big.success_rate_ci_low > small.success_rate_ci_low        # better evidence
