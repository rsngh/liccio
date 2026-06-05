# Docker live-security gate (WS18)

Verifies the `DockerWorkspaceManager` enforces real OS-level sandbox isolation.

## Run

```bash
docker info                              # confirm the daemon is up
uv run pytest -m live_docker -q          # the docker-marked tests (opt-in)
uv run acp eval docker-security-live     # the enforceable gate -> JSON report
uv run acp reports validate              # confirms the artifact is fresh + valid
uv run acp health --mode production      # docker_live_security_passed must be true
```

## What it checks (9 checks, all must pass)

`no_network`, `non_root`, `memory_cap`, `pid_cap`, `timeout`, `workspace_containment`,
`secret_scrub`, `massive_stdout`, `cleanup`.

Artifact: `evals/reports/docker_security_live.json` (`passed: true`).

## Contention hardening (WS3)

Each container gets a unique `acp-run-<uuid>` name + `acp.managed=true` label;
`DockerWorkspaceManager.prune_acp_resources()` removes only ACP-labeled stragglers; the
gate retries once on a transient daemon error. Run serially with `-n 1` if needed.
