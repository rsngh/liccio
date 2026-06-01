# Adding an agent adapter

Implement the `AgentAdapter` protocol (`acp.agents.base`): `name`, `kind`, and
async `healthcheck`/`plan`/`execute`/`review`. Lazy-import any SDK and return an
unavailable `AgentHealth` when missing so project import never fails. Register it
with `AgentRegistry.register(...)` (or extend `build_default_registry`). `execute`
returns an `AgentAttemptResult` with a `DiffBundleRef`.
