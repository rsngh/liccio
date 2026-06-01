"""Code/document chunk types (charter §10.2)."""

from __future__ import annotations

from acp.schemas.context import ContextItem

CHUNK_KINDS = (
    "file_chunk",
    "symbol_chunk",
    "test_chunk",
    "doc_chunk",
    "instruction_chunk",
    "manifest_chunk",
    "recent_commit_chunk",
    "prior_run_summary_chunk",
)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate.

    Uses tiktoken when available, else a ~4-chars-per-token heuristic. Kept
    deterministic so context-pack hashes are reproducible.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001 - optional dep / network
        return max(1, len(text) // 4)


def make_chunk(
    *,
    kind: str,
    path: str,
    content: str,
    start_line: int | None = None,
    end_line: int | None = None,
    symbol_name: str | None = None,
    language: str | None = None,
    source: str = "indexer",
    repo_id: str = "",
    snapshot_id: str = "",
) -> ContextItem:
    meta: dict[str, str] = {}
    if language:
        meta["language"] = language
    if repo_id:
        meta["repo_id"] = repo_id
    if snapshot_id:
        meta["snapshot_id"] = snapshot_id
    return ContextItem(
        kind=kind,
        path=path,
        start_line=start_line,
        end_line=end_line,
        symbol_name=symbol_name,
        content=content,
        token_estimate=estimate_tokens(content),
        source=source,
        metadata=meta,
    )
