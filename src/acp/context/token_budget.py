"""Token budgeting for context packs (charter §10.4).

Selects the highest-value chunks within a token budget, always including required
items (instructions, task spec, AGENTS.md), enforcing per-file diversity, deduping
identical chunks, and emitting a trace explaining inclusions/exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.context.chunks import estimate_tokens
from acp.schemas.context import ContextItem


@dataclass
class BudgetResult:
    selected: list[ContextItem]
    dropped: list[ContextItem]
    token_estimate: int
    decisions: list[dict] = field(default_factory=list)


class ContextBudgeter:
    def __init__(
        self,
        token_budget: int,
        max_items_per_file: int = 3,
        max_total_files: int = 40,
    ) -> None:
        self.token_budget = token_budget
        self.max_items_per_file = max_items_per_file
        self.max_total_files = max_total_files

    def select(
        self,
        candidates: list[ContextItem],
        required: list[ContextItem] | None = None,
    ) -> BudgetResult:
        required = required or []
        selected: list[ContextItem] = []
        dropped: list[ContextItem] = []
        decisions: list[dict] = []
        used_tokens = 0
        seen_fingerprints: set[str] = set()
        per_file: dict[str, int] = {}
        files_seen: set[str] = set()

        def _try_add(item: ContextItem, *, forced: bool) -> bool:
            nonlocal used_tokens
            fp = item.fingerprint()
            if fp in seen_fingerprints:
                decisions.append({"path": item.path, "action": "drop", "reason": "duplicate"})
                return False
            tokens = item.token_estimate or estimate_tokens(item.content)
            if not forced:
                if per_file.get(item.path, 0) >= self.max_items_per_file:
                    decisions.append(
                        {"path": item.path, "action": "drop", "reason": "per_file_cap"}
                    )
                    return False
                if item.path not in files_seen and len(files_seen) >= self.max_total_files:
                    decisions.append(
                        {"path": item.path, "action": "drop", "reason": "max_files"}
                    )
                    return False
                if used_tokens + tokens > self.token_budget:
                    decisions.append(
                        {"path": item.path, "action": "drop", "reason": "budget_exceeded"}
                    )
                    return False
            seen_fingerprints.add(fp)
            per_file[item.path] = per_file.get(item.path, 0) + 1
            files_seen.add(item.path)
            used_tokens += tokens
            selected.append(item)
            decisions.append(
                {"path": item.path, "action": "include",
                 "reason": "required" if forced else "scored", "tokens": tokens}
            )
            return True

        # Required items always included (counted against budget but never dropped).
        for item in required:
            _try_add(item, forced=True)

        # Then greedily add candidates by their existing score order.
        for item in candidates:
            if not _try_add(item, forced=False) and item not in selected:
                dropped.append(item)

        return BudgetResult(
            selected=selected,
            dropped=dropped,
            token_estimate=used_tokens,
            decisions=decisions,
        )
