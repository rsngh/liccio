# Context compiler design

Pipeline: `RepoIndexer` → chunks (file/symbol/test/doc/instruction/manifest) →
`HybridRetriever` (BM25-or-overlap keyword + hashing-embedding vector + path/
symbol/test/prior-run boosts, configurable weights) → `ContextBudgeter`
(required-first, fingerprint dedupe, per-file + max-file caps, never exceeds the
token budget, emits a decision trace) → immutable `ContextPack` with a
deterministic `content_hash` over content-bearing fields only.

Strategies (§10.3): keyword_only, embedding_only, hybrid_keyword_embedding,
symbol_graph, test_focused, bug_reproduction, architecture, recent_changes,
prior_failures, minimal, max_context. Tree-sitter / sentence-transformers /
pgvector / Qdrant are optional; deterministic fallbacks keep hashes reproducible.
