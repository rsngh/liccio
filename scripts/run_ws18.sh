#!/usr/bin/env bash
# WS18 — Docker live-security gate. Exits non-zero if the gate fails.
set -euo pipefail
docker info >/dev/null
uv run acp eval docker-security-live
uv run acp reports validate
echo "WS18 docker live-security: see evals/reports/docker_security_live.json"
