"""Release-truth manifest: one source of truth for every cited count (Alpha 25).

The recurring product bug is report drift: CURRENT_STATUS.md citing a stale round, source
count, artifact count, or test count that disagrees with reality. This module computes the
canonical counts from their authoritative sources and checks that a status document agrees
with all of them — so `acp reports sync-status --strict` and a hard test can fail closed on
any disagreement. No count in any human-facing doc may diverge from the manifest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReleaseTruth:
    source_files: int
    artifacts: int
    tests_passed: int
    tests_skipped: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _count_source_files(root: Path) -> int:
    return len([p for p in (root / "src").rglob("*.py")
                if "__pycache__" not in p.parts])


def gather_truth(root: Path | str = ".") -> ReleaseTruth:
    """Compute canonical counts from their authoritative sources."""
    root = Path(root)
    from acp.observability.artifact_manifest import REPORT_SCHEMA_REGISTRY
    passed = skipped = 0
    pytxt = root / "reports" / "pytest.txt"
    if pytxt.exists():
        m = re.search(r"(\d+) passed, (\d+) skipped", pytxt.read_text())
        if m:
            passed, skipped = int(m.group(1)), int(m.group(2))
    return ReleaseTruth(source_files=_count_source_files(root),
                        artifacts=len(REPORT_SCHEMA_REGISTRY),
                        tests_passed=passed, tests_skipped=skipped)


def check_status_consistency(status_text: str, truth: ReleaseTruth) -> list[str]:
    """Return a list of disagreements between a status document and the canonical truth."""
    problems: list[str] = []
    # cited test count
    m = re.search(r"(\d+) passing, (\d+) skipped", status_text)
    if not m:
        problems.append("no 'N passing, M skipped' line in status")
    elif (int(m.group(1)), int(m.group(2))) != (truth.tests_passed, truth.tests_skipped):
        problems.append(
            f"test count {m.group(1)}/{m.group(2)} != truth "
            f"{truth.tests_passed}/{truth.tests_skipped}")
    # cited source-file count
    sm = re.search(r"(\d+) source files", status_text)
    if not sm:
        problems.append("no 'N source files' line in status")
    elif int(sm.group(1)) != truth.source_files:
        problems.append(f"source files {sm.group(1)} != truth {truth.source_files}")
    # cited artifact count
    am = re.search(r"(\d+) artifacts valid", status_text)
    if not am:
        problems.append("no 'N artifacts valid' line in status")
    elif int(am.group(1)) != truth.artifacts:
        problems.append(f"artifacts {am.group(1)} != truth {truth.artifacts}")
    return problems


def sync_status_text(status_text: str, truth: ReleaseTruth) -> str:
    """Rewrite every canonical count in a status document to match the truth."""
    t = re.sub(r"\d+ passing, \d+ skipped",
               f"{truth.tests_passed} passing, {truth.tests_skipped} skipped", status_text)
    t = re.sub(r"\d+ passed, \d+ skipped",
               f"{truth.tests_passed} passed, {truth.tests_skipped} skipped", t)
    t = re.sub(r"\d+ source files", f"{truth.source_files} source files", t)
    t = re.sub(r"\d+ artifacts valid", f"{truth.artifacts} artifacts valid", t)
    return t
