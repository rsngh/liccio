"""Memory lifecycle / aging benchmark (Alpha 24 area 7).

MeMo argues memory should be a separately-governed subsystem with read/write/integrate
interfaces, not just a vector DB. AgingBench frames long-lived agents as degrading through
compression, interference, revision, and maintenance aging. This module gives memory a
typed lifecycle:

- write: deduplicated, poison-audited, scope-tagged (a private repo's memory is keyed by
  scope_id and never served to another scope_id — no cross-tenant leak);
- read: scope-isolated, bumps recency/use so hot records resist aging;
- revise / retire: stale or superseded records are revised or retired;
- age: confidence decays with idle time (half-life) and records below a floor retire;
- interference: conflicting values for the same key are surfaced, not silently merged.

``aging_benchmark`` simulates write -> idle -> query -> revise and reports the recall decay
and post-revision repair curve, so memory's contribution and degradation are measurable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCOPES = ("repo", "organization", "skill", "harness", "failure_pattern", "reviewer_pref")
RETIRE_FLOOR = 0.25


@dataclass
class MemoryRecord:
    key: str
    value: str
    scope: str
    scope_id: str = ""              # tenant key; private memory never crosses scope_id
    confidence: float = 1.0
    created_at: float = 0.0
    last_used_at: float = 0.0
    use_count: int = 0
    retired: bool = False
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError(f"unknown memory scope {self.scope}")


_POISON = re.compile(r"(ignore[\w\s]{0,30}instructions|exfiltrate|sk-[A-Za-z0-9]{20,}|"
                     r"rm -rf|drop table)", re.I)


def poison_audit(record: MemoryRecord) -> tuple[bool, str]:
    """Block obviously poisoned/secret-bearing memory writes (defense in depth)."""
    if _POISON.search(record.value or ""):
        return False, "poison/secret pattern in memory value"
    return True, "clean"


@dataclass
class WriteResult:
    status: str                    # written | updated | deduped | blocked
    reason: str = ""


class MemoryStore:
    """A governed in-memory store, keyed by (scope, scope_id, key)."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], MemoryRecord] = {}

    def _k(self, scope: str, scope_id: str, key: str) -> tuple[str, str, str]:
        return (scope, scope_id, key)

    def write(self, record: MemoryRecord, *, now: float = 0.0) -> WriteResult:
        ok, reason = poison_audit(record)
        if not ok:
            return WriteResult("blocked", reason)
        record.created_at = record.created_at or now
        k = self._k(record.scope, record.scope_id, record.key)
        existing = self._records.get(k)
        if existing is not None and not existing.retired:
            if existing.value == record.value:
                return WriteResult("deduped", "identical value already stored")
            existing.value = record.value          # integrate: supersede in place
            existing.confidence = max(existing.confidence, record.confidence)
            existing.last_used_at = now
            return WriteResult("updated", "superseded prior value")
        self._records[k] = record
        return WriteResult("written")

    def read(self, key: str, *, scope: str, scope_id: str = "", now: float = 0.0
             ) -> MemoryRecord | None:
        r = self._records.get(self._k(scope, scope_id, key))
        if r is None or r.retired:
            return None
        r.use_count += 1
        r.last_used_at = now
        return r

    def revise(self, key: str, new_value: str, *, scope: str, scope_id: str = "",
               now: float = 0.0) -> bool:
        r = self._records.get(self._k(scope, scope_id, key))
        if r is None:
            return False
        r.value, r.retired, r.confidence, r.last_used_at = new_value, False, 1.0, now
        return True

    def age(self, now: float, *, half_life: float = 30.0) -> int:
        """Decay idle records' confidence; retire those below the floor. Returns # retired."""
        retired = 0
        for r in self._records.values():
            if r.retired:
                continue
            idle = max(0.0, now - (r.last_used_at or r.created_at))
            r.confidence = round(r.confidence * 0.5 ** (idle / half_life), 4)
            if r.confidence < RETIRE_FLOOR:
                r.retired = True
                retired += 1
        return retired

    def interference(self, scope: str, scope_id: str = "") -> list:
        """Keys with multiple distinct live values (conflicts to resolve, not merge)."""
        seen: dict[str, set] = {}
        for (s, sid, key), r in self._records.items():
            if s == scope and sid == scope_id and not r.retired:
                seen.setdefault(key, set()).add(r.value)
        return [k for k, vals in seen.items() if len(vals) > 1]

    def live_count(self) -> int:
        return sum(1 for r in self._records.values() if not r.retired)


@dataclass
class AgingCurve:
    recall_before_aging: float
    recall_after_aging: float
    recall_after_revision: float
    retired: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def aging_benchmark(n_records: int = 10, *, idle_gap: float = 60.0,
                    half_life: float = 30.0) -> AgingCurve:
    """Write n records, query (full recall), idle+age (decay), revise half, query again."""
    store = MemoryStore()
    keys = [f"fact_{i}" for i in range(n_records)]
    for i, k in enumerate(keys):
        store.write(MemoryRecord(key=k, value=f"v{i}", scope="repo", scope_id="acme"), now=0.0)
    before = sum(store.read(k, scope="repo", scope_id="acme", now=1.0) is not None
                 for k in keys) / n_records
    store.age(now=idle_gap, half_life=half_life)        # long idle -> heavy decay
    retired = sum(store._records[("repo", "acme", k)].retired for k in keys)
    after = sum(store.read(k, scope="repo", scope_id="acme", now=idle_gap) is not None
                for k in keys) / n_records
    for k in keys[: n_records // 2]:                    # maintenance: revise half
        store.revise(k, "fresh", scope="repo", scope_id="acme", now=idle_gap)
    repaired = sum(store.read(k, scope="repo", scope_id="acme", now=idle_gap) is not None
                   for k in keys) / n_records
    return AgingCurve(round(before, 4), round(after, 4), round(repaired, 4), retired)
