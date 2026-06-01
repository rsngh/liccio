# Subsystem status schema

Every subsystem in `CURRENT_STATUS.md` and `FINAL_REPORT.md` is classified with
exactly one of these status categories. This vocabulary is the single source of
truth for "how real is this?" so reviewers never have to guess.

| Status | Meaning |
| --- | --- |
| **real local** | Fully implemented and runs locally with no external service or key (e.g. the workflow runner, command runner, context compiler, SQLite persistence). |
| **real service-backed** | Fully implemented against a real external service when configured; fails loudly (not silently to memory) when the service is absent (e.g. pgvector with a DSN, Qdrant server URL, OTLP exporter). |
| **ACP true harness** | A real agentic tool-loop harness implemented inside ACP (`is_harness=True`): drives read/write/run tools, captures a normalized `AgentTrace`, enforces budgets. Today: `openai_harness`, `claude_harness`. |
| **vendor harness** | A wrapper around an external vendor coding-agent SDK/CLI (e.g. Claude Agent SDK, OpenHands, Codex CLI) run as a black box. Not yet implemented — distinct from an ACP true harness. |
| **simple model adapter** | A single-shot LLM adapter that emits a JSON edit (no tool loop). Cheap routing target. `is_harness=False` (e.g. `claude`, `codex`, `openhands`, `simple_llm`). |
| **fallback** | A degraded but functional implementation used when an optional dependency/service is missing (e.g. hashing-embedding vector store, in-memory artifact cache). Always logged as a fallback. |
| **stub** | Behind-protocol placeholder that reports `unavailable` / raises a clear error; no real behaviour yet (e.g. Kubernetes workspace backend, Braintrust/LangSmith export). |

## Rules

1. A subsystem labelled **real service-backed** must never silently fall back to
   an in-memory implementation — it must raise or report `unavailable`.
2. **ACP true harness** and **vendor harness** are different categories. Do not
   describe an ACP harness as a vendor SDK wrapper or vice-versa.
3. **simple model adapter** must never be described as a harness.
4. Status claims in docs must match code reality; `test_docs_consistency.py`
   enforces the load-bearing ones.
