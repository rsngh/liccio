# agent-control-plane (`acp`)

An agentic software-engineering **control plane**. It routes coding tasks across
multiple coding agents and models, compiles repo-specific context, runs agents
in isolated workspaces, verifies outputs, collects traces, learns from objective
and human feedback, and improves routing decisions over time using contextual
bandits, supervised ML, weak supervision, and active learning.

The moat is the loop:

```text
task → context → route → attempt → verify → evaluate → human label → reward → learn → better routing
```

Every agent run becomes a reusable, fully-versioned, traceable training example.

## Status

Under active construction (see `IMPLEMENTATION_LOG.md` and `GOALS.md`). The
system is designed to run **end-to-end with no paid API keys** using fake/local
adapters; external SDKs and cloud services are optional.

## Quickstart

```bash
uv sync --all-extras        # build the isolated .venv (does not touch conda)
uv run acp --help
uv run acp version
uv run pytest tests/unit -q
```

## What works without API keys

- Fake and patch agent adapters, full orchestration loop, context compiler,
  verification, evaluation ladder, routing (heuristic + simulated bandit),
  human-review queue, traces, and the bugfix demo.

## What is optional

- Real Claude / OpenAI / Codex / OpenHands adapters (need keys / local servers).
- Postgres + pgvector, Qdrant, Docker/Kubernetes workspaces, Playwright UI
  checks, Braintrust / LangSmith / Phoenix exporters, heavy ML libraries.

## Architecture

See `ARCHITECTURE.md` and `docs/design/`.

## Testing

```bash
make test          # unit + integration + ruff + mypy
make test-e2e      # end-to-end
make coverage      # coverage report
```

## Security

All command execution is mediated by a redacting command runner with timeouts,
cwd containment, and output truncation. Secrets are never logged, traced, or
stored. High-risk tasks require human review by default. See `SECURITY.md`.
