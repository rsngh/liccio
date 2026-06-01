"""ArtifactStore tests (charter §8.3)."""

from __future__ import annotations

import pytest

from acp.core.artifacts import LocalArtifactStore, truncate_with_artifact
from acp.core.errors import ArtifactError


def test_put_get_roundtrip(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = store.put_text("hello world")
    assert ref.sha256
    assert store.get_bytes(ref) == b"hello world"


def test_path_traversal_rejected(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = store.put_text("x")
    ref.uri = "artifact://../../etc/passwd"
    with pytest.raises(ArtifactError):
        store.get_bytes(ref)


def test_checksum_verified(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = store.put_text("data")
    ref.sha256 = "0" * 64  # corrupt expected hash
    with pytest.raises(ArtifactError):
        store.get_bytes(ref)


def test_large_output_truncated_and_artifacted(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    big = "A" * 5000
    summary, ref = truncate_with_artifact(store, big, max_chars=1000)
    assert ref is not None
    assert len(summary) < len(big)
    assert "truncated" in summary
    assert store.get_text(ref) == big


def test_small_output_not_artifacted(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    summary, ref = truncate_with_artifact(store, "short", max_chars=1000)
    assert ref is None
    assert summary == "short"


def test_content_addressed_dedupe(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    a = store.put_text("same")
    b = store.put_text("same")
    assert a.uri == b.uri
