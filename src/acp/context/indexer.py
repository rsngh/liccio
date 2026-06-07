"""Repository indexer (charter §10.1).

Walks a repo (or workspace) and produces context chunks: files, symbols, tests,
docs, instructions (AGENTS.md), manifests, and recent-commit summaries. Binary
and obviously-secret files are skipped. Large files are split into windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from acp.context.chunks import make_chunk
from acp.context.parsers import detect_language, parse_symbols
from acp.schemas.context import ContextItem

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".acp", "dist", "build", ".mypy_cache"}
DOC_NAMES = {"readme.md", "readme.rst", "readme.txt"}
INSTRUCTION_NAMES = {"agents.md", "claude.md", "contributing.md", ".cursorrules"}
MANIFEST_NAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "cargo.toml",
    "go.mod",
}
MAX_FILE_BYTES = 200_000
FILE_WINDOW_LINES = 200
SECRET_HINT_NAMES = {".env", "id_rsa", "credentials"}


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:1024]


def _is_test_path(path: str) -> bool:
    low = path.lower()
    return (
        "/test" in low
        or low.startswith("test")
        or "/tests/" in low
        or low.endswith("_test.py")
        or "test_" in Path(low).name
        or ".test." in low
        or ".spec." in low
    )


@dataclass
class RepoIndex:
    chunks: list[ContextItem] = field(default_factory=list)
    language_summary: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    has_instructions: bool = False
    instruction_text: str = ""


class RepoIndexer:
    def __init__(
        self,
        repo_path: str | Path,
        repo_id: str = "",
        snapshot_id: str = "",
        max_file_bytes: int = MAX_FILE_BYTES,
        window_lines: int = FILE_WINDOW_LINES,
    ) -> None:
        self.root = Path(repo_path)
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.max_file_bytes = max_file_bytes
        self.window_lines = window_lines

    def _iter_files(self):
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.relative_to(self.root).parts):
                continue
            yield p

    def _file_chunks(self, rel: str, text: str, language: str | None) -> list[ContextItem]:
        lines = text.splitlines()
        if _is_test_path(rel):
            base_kind = "test_chunk"
        elif rel.lower().endswith((".md", ".rst")):
            base_kind = "doc_chunk"
        else:
            base_kind = "file_chunk"
        chunks: list[ContextItem] = []
        if len(lines) <= self.window_lines:
            chunks.append(
                make_chunk(
                    kind=base_kind, path=rel, content=text, start_line=1,
                    end_line=max(1, len(lines)), language=language,
                    repo_id=self.repo_id, snapshot_id=self.snapshot_id,
                )
            )
        else:
            for start in range(0, len(lines), self.window_lines):
                window = lines[start : start + self.window_lines]
                chunks.append(
                    make_chunk(
                        kind=base_kind, path=rel, content="\n".join(window),
                        start_line=start + 1, end_line=start + len(window),
                        language=language, repo_id=self.repo_id, snapshot_id=self.snapshot_id,
                    )
                )
        # symbol chunks
        for sym in parse_symbols(rel, text):
            seg = "\n".join(lines[sym.start_line - 1 : sym.end_line])
            if seg.strip():
                chunks.append(
                    make_chunk(
                        kind="symbol_chunk", path=rel, content=seg,
                        start_line=sym.start_line, end_line=sym.end_line,
                        symbol_name=sym.name, language=language,
                        repo_id=self.repo_id, snapshot_id=self.snapshot_id,
                    )
                )
        return chunks

    def collect_sources(self) -> dict[str, str]:
        """Return ``{rel_path: source}`` for code files (for the graph-ranked repo map).

        Mirrors :meth:`index`'s file-walk + guards (skip dirs, secrets, binaries, oversized)
        so the repo map sees exactly the files the indexer would, never divergent.
        """
        sources: dict[str, str] = {}
        for p in self._iter_files():
            rel = p.relative_to(self.root).as_posix()
            name = p.name.lower()
            if name in SECRET_HINT_NAMES or name.startswith(".env"):
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            if len(raw) > self.max_file_bytes or _is_binary(raw):
                continue
            if detect_language(rel) is None:
                continue  # only code files carry symbols worth mapping
            sources[rel] = raw.decode("utf-8", errors="replace")
        return sources

    def index(self) -> RepoIndex:
        idx = RepoIndex()
        for p in self._iter_files():
            rel = p.relative_to(self.root).as_posix()
            name = p.name.lower()
            if name in SECRET_HINT_NAMES or name.startswith(".env"):
                continue  # never index secret files
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            if len(raw) > self.max_file_bytes or _is_binary(raw):
                idx.files.append(rel)
                continue
            text = raw.decode("utf-8", errors="replace")
            language = detect_language(rel)
            idx.files.append(rel)
            if language:
                idx.language_summary[language] = idx.language_summary.get(language, 0) + 1

            if name in INSTRUCTION_NAMES:
                idx.has_instructions = True
                idx.instruction_text = text
                idx.chunks.append(
                    make_chunk(kind="instruction_chunk", path=rel, content=text,
                               language=language, repo_id=self.repo_id,
                               snapshot_id=self.snapshot_id)
                )
                continue
            if name in MANIFEST_NAMES:
                idx.chunks.append(
                    make_chunk(kind="manifest_chunk", path=rel, content=text,
                               language=language, repo_id=self.repo_id,
                               snapshot_id=self.snapshot_id)
                )
                continue
            if name in DOC_NAMES:
                idx.chunks.append(
                    make_chunk(kind="doc_chunk", path=rel, content=text,
                               language=language, repo_id=self.repo_id,
                               snapshot_id=self.snapshot_id)
                )
                continue
            idx.chunks.extend(self._file_chunks(rel, text, language))

        idx.language_summary = dict(
            sorted(idx.language_summary.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        return idx
