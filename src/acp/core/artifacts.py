"""Artifact storage (charter §8.3).

Large raw outputs (terminal transcripts, test output, patches, screenshots, LLM
raw responses, retrieval dumps) must NOT be stored inline in relational rows.
They go to an ArtifactStore which returns a content-addressed reference.

The local filesystem implementation:
- stores blobs under ``artifact_dir`` sharded by sha256 prefix,
- verifies sha256 on read,
- refuses path traversal (uri must resolve inside the root).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol, runtime_checkable

from acp.core.errors import ArtifactError
from acp.schemas.trace import ArtifactRef


@runtime_checkable
class ArtifactStore(Protocol):
    def put_bytes(self, data: bytes, *, content_type: str, suffix: str) -> ArtifactRef: ...

    def put_text(
        self, text: str, *, content_type: str = "text/plain", suffix: str = ".txt"
    ) -> ArtifactRef: ...

    def get_bytes(self, ref: ArtifactRef) -> bytes: ...


class LocalArtifactStore:
    """Content-addressed local filesystem artifact store."""

    SCHEME = "artifact://"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, sha: str, suffix: str) -> Path:
        # Shard by first 2 hex chars to avoid huge directories.
        shard = self.root / sha[:2]
        shard.mkdir(parents=True, exist_ok=True)
        return shard / f"{sha}{suffix}"

    def _resolve_uri(self, uri: str) -> Path:
        if not uri.startswith(self.SCHEME):
            raise ArtifactError(f"unrecognized artifact uri: {uri!r}")
        rel = uri[len(self.SCHEME) :]
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise ArtifactError(f"path traversal rejected: {uri!r}")
        path = (self.root / rel).resolve()
        # Containment: resolved path must live under root.
        if not str(path).startswith(str(self.root)):
            raise ArtifactError(f"artifact path escapes root: {uri!r}")
        return path

    def put_bytes(self, data: bytes, *, content_type: str, suffix: str) -> ArtifactRef:
        sha = hashlib.sha256(data).hexdigest()
        path = self._path_for(sha, suffix)
        if not path.exists():
            path.write_bytes(data)
        rel = path.relative_to(self.root).as_posix()
        return ArtifactRef(
            uri=f"{self.SCHEME}{rel}",
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha,
        )

    def put_text(
        self, text: str, *, content_type: str = "text/plain", suffix: str = ".txt"
    ) -> ArtifactRef:
        return self.put_bytes(text.encode("utf-8"), content_type=content_type, suffix=suffix)

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        path = self._resolve_uri(ref.uri)
        if not path.exists():
            raise ArtifactError(f"artifact not found: {ref.uri}")
        data = path.read_bytes()
        if ref.sha256:
            actual = hashlib.sha256(data).hexdigest()
            if actual != ref.sha256:
                raise ArtifactError(
                    f"artifact checksum mismatch for {ref.uri}: "
                    f"expected {ref.sha256[:12]}, got {actual[:12]}"
                )
        return data

    def get_text(self, ref: ArtifactRef) -> str:
        return self.get_bytes(ref).decode("utf-8")


def truncate_with_artifact(
    store: ArtifactStore,
    text: str,
    *,
    max_chars: int,
    suffix: str = ".log",
) -> tuple[str, ArtifactRef | None]:
    """Return a truncated summary plus a full-output artifact ref if needed.

    If ``text`` fits within ``max_chars`` it is returned unchanged with no
    artifact. Otherwise the full text is stored and a head+tail summary returned.
    """
    if len(text) <= max_chars:
        return text, None
    ref = store.put_text(text, suffix=suffix)
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    dropped = len(text) - max_chars
    summary = f"{head}\n...[truncated {dropped} chars; full output {ref.uri}]...\n{tail}"
    return summary, ref
