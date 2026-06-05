#!/usr/bin/env bash
# WS19 — Vendor-native harness live gate. Skips harnesses that are not installed.
set -euo pipefail
for b in codex claude openhands; do command -v "$b" >/dev/null && "$b" --version || true; done
uv run acp eval vendor-harness-live
uv run acp reports validate
echo "WS19 vendor harness live: see evals/reports/vendor_harness_live.json"
