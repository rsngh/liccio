# Alpha 12 report — harness quality + workflow-shape learning

Alpha 11 reached a production-readiness candidate. Alpha 12 deepens *decision
quality at the harness level*: it measures whether a harness actually engaged and
followed its protocol, governs persistent harness self-improvement, lets routing
learn the workflow *shape* (not just agent/model/context), and judges agent
trajectories relatively across many axes.

## Headline results

- **Harness behavior is measured, live** (`alpha12_harness_metrics.json`): on real
  openai+claude tool-loop runs over 2 no-patch tasks, HAR=HFR=PWL=1.0 — every
  harness attempt activated its loop, followed read→write→run, and solved. The
  metrics (`evaluation/harness_metrics.py`) generalize to by-model/by-task-type
  slices for the capability matrix.
- **Harness self-improvement is governed** (`training/harness_evolution.py`): a
  proposed prompt/config change cannot be promoted without a clean security scan,
  a passing regression + negative-transfer eval, an approving review, a rollback
  plan, and a canary that did not roll back — the audit trail is explicit.
- **Routing can learn workflow shape** (WS8): `RoutingAction.topology` +
  `TOPOLOGY_ACTIONS` (skip planner/reviewer, light/strict verifier, branch
  parallel, terminate, abstain). Arm keys stay backward-compatible (topology only
  extends the key when set), so prior OPE logs/arms still match, and a topology
  arm is OPE-learnable.
- **Trajectories are judged relatively** (WS9): two trajectories are compared on 8
  axes (goal, test adequacy, minimality, security, activation, adherence, recovery,
  cost) with a cross-judge audit and leave-one-axis-out reward sensitivity; the
  result converts to a preference pair for the preference learner.

## Honest limitations

- The harness-evolution pipeline governs updates but does not author prompt edits;
  the evolver that proposes diffs from execution evidence is the natural next step.
- Topology actions are representable and OPE-learnable, but the runner does not yet
  *execute* skip_planner/branch_parallel differently — wiring the workflow engine
  to honor topology flags is the follow-on.
- The relative trajectory judge is rule-based per axis; an LLM-judge variant behind
  the cross-judge audit is a future option.
