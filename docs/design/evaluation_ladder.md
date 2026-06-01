# Evaluation ladder

1. Objective evaluator (`ObjectiveEvaluator`): 8 scores from verification verdict
   + diff (spec_compliance, test_adequacy, regression/security risk, review_burden,
   maintainability, confidence, requires_human_review).
2. Weak supervision: 15 labeling functions → confidence-weighted probabilistic
   `WeakLabel`.
3. LLM judges: `LLMJudge` protocol + 5 fake deterministic judges; strict-JSON
   parse with retry for real judges.
4. Human review queue: reasons, labels, resolve; pauses the workflow.
5. Active learning: weighted priority (uncertainty/disagreement/risk/novelty/
   cost_surprise/VOI) + audit-sample override selects items for labeling.
