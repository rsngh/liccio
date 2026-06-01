# Alpha 5 Report — production-grade empirical routing lab

> `CURRENT_STATUS.md` is the source of truth for status/coverage; the
> round-by-round history is in `HISTORY.md`; the merge gate is
> `ALPHA5_CHECKLIST.md`. Status vocabulary: `docs/status_schema.md`.

## What Alpha 5 adds over Alpha 4

Alpha 4 proved two true harnesses + normalized traces. Alpha 5 makes the lab
**repeatable and decision-useful**:

1. **Dataset-driven, multi-task bakeoffs (v2).** A no-patch dataset spanning
   bugfix / test-generation / feature / refactor / security / migration, run
   across adapters with repetitions and rich per-cell metrics, aggregated by
   adapter / task type / risk.
2. **Routing learns from traces, not just rewards.** Per (adapter, task_type)
   history features feed the bandit; replaying a bakeoff changes the preferred
   harness per task class.
3. **Delayed outcomes matter.** A post-merge simulator injects
   revert/incident/latency-regression outcomes that can downgrade a day-0
   favourite — routing reflects reality, not just first impressions.
4. **Every evaluator is calibrated.** Per-evaluator accuracy / precision /
   recall / Brier / ECE / correlation, with a recommended human-review
   threshold and an explicit false-auto-approve risk.
5. **Hard safety + cost limits.** Budget hard-stops bound every harness loop;
   the sandbox red-team lab shows the local backend is unsafe for true
   harnesses (use Docker).
6. **Reviewable, redacted live evidence.** A committed redacted artifact shows
   OpenAI and Claude harnesses solving the same no-patch task — no secrets,
   prompts, diffs, or provider IDs.

## Live evidence (real run)

From `reports/live/live_openai_claude_bakeoff.json` (redacted):

| adapter | solved | verification | tool_calls | tokens | cost (USD) | latency (s) |
| --- | --- | --- | --- | --- | --- | --- |
| openai_harness | yes | pass | 3 | 1897 | 0.0015 | 10.1 |
| claude_harness | yes | pass | 4 | 6406 | 0.0164 | 7.6 |

Both true harnesses solved the same divide-by-zero task with no supplied patch.

## Calibration snapshot

From `evals/reports/calibration_v2.json` (operating threshold 0.5): the
adversarial detector is best-calibrated (Brier ≈ 0.04, false-auto-approve 0.0);
the objective signal is fooled by hardcoded/test-deletion fixes
(false-auto-approve ≈ 0.64); a naive always-pass signal is worst (≈ 0.67) — so
the human-review gate should not trust the objective signal alone.

## Artifacts

`evals/reports/`: `multi_harness_v2.json`, `router_replay.json`,
`calibration_v2.json`, `sandbox_redteam.json`, `postmerge_sim.json`,
`docker_security.json` (+ the Alpha-4 set). `reports/`: `pytest.txt`,
`coverage.txt`, `live/`. Regenerate with `make alpha4-artifacts alpha5-artifacts`.

## Honest limitations

- **Vendor harnesses** (Claude Agent SDK / OpenHands / Codex CLI wrappers) are
  not implemented; the two true harnesses are ACP-native (`docs/status_schema.md`).
- **Docker live evidence** is skipped in environments without a Docker daemon
  (explicit skip, not silent).
- The post-merge outcomes and calibration scenario set are **synthetic** (a lab),
  designed to exercise the learning + calibration loops deterministically.
- pgvector real wiring requires a DSN; `require_real=True` refuses to silently
  fall back to memory.
