# Vendor-native harness live gate (WS19)

Drives the installed vendor coding harnesses (Codex, Claude Code, OpenHands) on a no-patch
fix-the-failing-test task and verifies the result.

## Run

```bash
codex --version && claude --version && openhands --version   # availability
uv run acp eval vendor-harness-live          # run the gate -> JSON report
uv run pytest tests/live -m live_vendor -q   # the live_vendor test (opt-in)
uv run acp reports validate                  # artifact fresh + valid
uv run acp health --mode production          # vendor_harness_live_passed must be true
```

## What it does

- Detects each harness version; unavailable harnesses are **skipped, not failed**.
- For codex_cli + claude_code: runs the smoke fixture, captures diff + AgentTrace metadata
  + an enforced 240s timeout + a secret scan, and classifies the result into an
  `AttemptOutcome` (a timeout is infra/inconclusive, not a capability failure).
- OpenHands is health-checked (capability level reported, no overclaiming).

Artifact: `evals/reports/vendor_harness_live.json` (`available: true`, `passed: true`,
`n_solved >= 1`).

Note: `tests/live` is ignored by default (`addopts --ignore=tests/live`); run live markers
with the path, e.g. `uv run pytest tests/live -m live_vendor -q`.
