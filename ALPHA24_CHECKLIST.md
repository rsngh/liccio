# Alpha 24 — 15-Area Checklist

Status: COMPLETE. All 3 tiers / 15 areas shipped with modules + unit tests + artifacts.
See `ALPHA24_REPORT.md`. Gate green; 84 artifacts valid.

## Modules (src)
- [x] area 1 `orchestration/advisor.py`
- [x] area 2 `agents/weak_model_candidates.py`
- [x] area 3 `routing/topology_controller.py`
- [x] area 4 `training/meta_harness.py`
- [x] area 5 `agents/task_synthesizer.py`
- [x] area 6 `context/strategy_optimizer.py`
- [x] area 7 `memory/lifecycle.py`
- [x] area 8 `orchestration/sdb.py`
- [x] area 9 `orchestration/abstention.py`
- [x] area 10 `training/workflow_distillation.py`
- [x] area 11 `training/heavy_skill.py`
- [x] area 12 `training/tool_format_dataset.py`
- [x] area 13 `training/variant_archive.py`
- [x] area 14 `orchestration/confidence_pruning.py`
- [x] area 15 `evaluation/research_benchmark.py`

## Live experiments (real OpenAI / vendor calls)
- [x] advisor escalation (advisor_bakeoff.json): handicapped exec 0.33→1.0 with advisor
- [x] best-of-k cost curve (best_of_k_cost_curve.json): k=1 Pareto-optimal
- [x] HeavySkill (heavyskill_bugfix.json): 40–80% verification pruning on engaged tasks

## Artifacts (84 valid; areas 1–15 each carry ≥1)
- [x] advisor_{policy,bakeoff,cost_quality_frontier}, weak_model_candidate_bakeoff,
      best_of_k_cost_curve, topology_{controller_search,ope,policy_canary},
      meta_harness_patch, harness_{regression_suite,canary}, synthetic via task_synthesizer,
      grep_vs_embedding_bakeoff, context_strategy_ope, context_reuse_frontier,
      memory_{aging_benchmark,lifecycle,poisoning}, abstention (orchestration),
      workflow_distillation_dataset, small_model_training_smoke, memorization_audit,
      heavyskill_bugfix, parallel_deliberation_skill, tool_format_dataset,
      harness_activation_training, agent_variant_archive, open_ended_harness_evolution,
      confidence_pruning, advisor_confidence_trigger, research_engineering_benchmark,
      nanogpt_style_agent_eval, algorithmic_progress_report

## Gate
- [x] ruff + mypy clean; alembic OK; `acp reports validate` all valid; full suite green
