# Project history — agent-control-plane (`acp`)

Archive of the round-by-round build narrative. **`CURRENT_STATUS.md` is the
source of truth** for current status; `ALPHA4_CHECKLIST.md` and `FINAL_REPORT.md`
cover the latest state. Historical numbers below may lag and are retained only
for provenance.

## Rounds

- **Round 0 (`GOALS0.md`) — Alpha 0.** Greenfield build of the full control-plane
  loop on fake/patch adapters: schemas + DB + artifacts, workspace + mediated
  command runner, context compiler, verification ladder, 16-node durable
  `WorkflowRunner`, heuristic + simulated-bandit routing, evaluation ladder +
  HITL, API + CLI, long evals. No paid keys required.

- **Round 1 (`GOALS1.md`) — Alpha 1.** Hardening: richer provenance + full
  run-graph reconstruction, off-policy evaluation, durable crash-resume,
  bakeoff/soak/retriever-stress/red-team eval scripts.

- **Round 2 (`GOALS2.md`) — Alpha 2.** First true OpenAI tool-loop harness
  (`OpenAIHarnessAdapter`), normalized `AgentTrace`, Docker workspace + command
  runner, Qdrant real engine, persisted bandit state surviving restart.

- **Round 3 (`GOALS3.md`) — Alpha 3.** Execution-backend policy (Docker-required
  for harnesses), evaluator calibration vs human + post-merge labels, post-merge
  outcome replay → matured rewards → bandit update, multi-adapter trace bakeoff,
  no-patch bakeoff, parity + persisted bandit Monte Carlo.

- **Round 4 (`GOALS.md`) — Alpha 4: multi-harness empirical router.** Second
  true harness (`ClaudeHarnessAdapter`), governance enforced in orchestration,
  mandatory `AgentTrace` invariant, live Docker evidence pack, multi-harness
  no-patch bakeoff, router learns from bakeoffs, calibrated evaluator loop with
  human-review threshold. See `ALPHA4_CHECKLIST.md`.

## Stale historical notes

Earlier `FINAL_REPORT.md` revisions described the agent harnesses as "simple
model adapters, not full tool-loop harnesses" and quoted fixed test counts
(e.g. 151 / 179 / 222 / 305). Those statements were accurate at their round and
are superseded: two true tool-loop harnesses now exist, and the live test count
is recorded in `reports/pytest.txt`.
