# Security

## Threat model

`acp` runs untrusted, model-generated code and instructions. Primary risks:
secret exfiltration, workspace escape, unintended network access, destructive
commands, and prompt-injected attempts to disable verification or auto-approve
unsafe changes.

## Controls

### Mediated command execution
All subprocesses go through `acp.workspaces.command_runner.CommandRunner`:
- working-directory containment (commands cannot run outside the allowed root),
- timeouts with process-group termination,
- output truncation with full output stored as an artifact,
- exit-code + resource capture,
- secret redaction over all stdout/stderr.

### Workspace isolation
Each run gets its own git worktree on a fresh branch at the snapshot commit.
Docker/Kubernetes backends (optional) add container isolation behind the same
`WorkspaceManager` protocol.

### Secret handling
- API keys are held as `pydantic.SecretStr`; never appear in `repr`/logs/dumps.
- A `Redactor` masks sensitive env keys (TOKEN/KEY/SECRET/PASSWORD/CREDENTIAL…)
  and common token shapes (`sk-…`, `sk-ant-…`, `ghp_…`, AWS keys, PEM blocks).
- Redaction runs in the logging processor, span exporter, and command output.
- The repo indexer skips `.env`, `id_rsa`, `credentials`, and binary files.

### Network controls
Network is denied by default (`ACP_ALLOW_NETWORK_BY_DEFAULT=false`). Enabling it
for a task records an audit event.

### Governance
`acp.core.policies.PolicyEngine` enforces: no auto-merge by default, high/critical
risk cannot auto-finalize (human review required), experimental policies cannot
auto-approve, budget ceilings. Every override/approval/network-enablement creates
an `AuditEvent`.

## Red-team coverage

`tests/long/test_security_redteam.py` asserts the controls against malicious
tasks: workspace escape blocked, env/printed secrets redacted, network denied,
auto-merge disabled, high-risk gated, secret files never indexed.

## Known limitations

- Local `CommandRunner` enforces cwd containment and redaction but does not
  sandbox syscalls/network at the OS level — use the Docker/K8s backend for
  hard isolation in production.
- Cross-process resume from persisted `WorkflowState` is a follow-up; the run
  registry is in-process today (entities are persisted).
