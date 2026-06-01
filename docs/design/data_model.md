# Data model

22 entity tables (charter §8.1) persisted via `EntityStore`: one queryable row
(id + indexed FKs/status/trace_id + created_at) plus a JSON `data` column holding
the full Pydantic payload (lossless round-trip). Large blobs are stored in the
content-addressed `ArtifactStore` and referenced by URI. Query helpers:
`all_for_task(task_id)` and `all_for_trace(trace_id)`.
