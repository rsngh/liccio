# Adding an evaluator

- Weak signal: write a `LabelingFn` returning a `WeakSignal` and add it to the
  `WeakSupervisor.labeling_functions`.
- LLM judge: implement the `LLMJudge` protocol returning `LLMJudgeResult`; parse
  strict JSON via `parse_judge_json`.
- Objective metric: extend `ObjectiveEvaluator` / `EvidenceAggregator`.
