"""Context-pack compiler (charter §10.5).

Ties indexing -> retrieval -> budgeting into an immutable, hashable ContextPack.
Same (task, snapshot, strategy, budget, repo content) -> same content_hash.
"""

from __future__ import annotations

from pathlib import Path

from acp.context.chunks import make_chunk
from acp.context.indexer import RepoIndexer
from acp.context.retrieval import HybridRetriever
from acp.context.token_budget import ContextBudgeter
from acp.schemas.context import ContextItem, ContextPack, RetrievalTrace
from acp.schemas.task import Task


class ContextCompiler:
    def __init__(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str,
        weights: dict[str, float] | None = None,
        prior_paths: set[str] | None = None,
    ) -> None:
        self.repo_path = repo_path
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.weights = weights
        self.prior_paths = prior_paths

    def compile(
        self,
        task: Task,
        strategy: str = "hybrid_keyword_embedding",
        token_budget: int = 80_000,
        top_k: int = 60,
    ) -> ContextPack:
        index = RepoIndexer(self.repo_path, self.repo_id, self.snapshot_id).index()
        query = self._build_query(task)

        retriever = HybridRetriever(
            index.chunks, weights=self.weights, prior_paths=self.prior_paths
        )
        scored, trace = retriever.retrieve(query, strategy=strategy, top_k=top_k)
        candidates = [s.item for s in scored]

        # Required items: instruction chunks + manifests (always include if present).
        required: list[ContextItem] = [
            it for it in index.chunks if it.kind in ("instruction_chunk",)
        ]
        # The task spec itself, as a synthetic instruction chunk.
        spec_chunk = make_chunk(
            kind="instruction_chunk",
            path="__task_spec__",
            content=self._spec_text(task),
            source="task",
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
        )
        required.insert(0, spec_chunk)

        budgeter = ContextBudgeter(token_budget=token_budget)
        result = budgeter.select(candidates, required=required)

        merged_trace = RetrievalTrace(
            strategy=strategy,
            query_terms=trace.query_terms,
            weights=trace.weights,
            considered=trace.considered,
            selected=len(result.selected),
            dropped=len(result.dropped),
            decisions=result.decisions,
            notes=[*trace.notes, f"required={len(required)}"],
        )

        return ContextPack(
            repo_id=self.repo_id,
            task_id=task.id,
            snapshot_id=self.snapshot_id,
            strategy=strategy,
            token_budget=token_budget,
            token_estimate=result.token_estimate,
            items=result.selected,
            instructions=index.instruction_text,
            retrieval_trace=merged_trace,
        )

    @staticmethod
    def _build_query(task: Task) -> str:
        parts = [task.title, task.body, " ".join(task.acceptance_criteria), " ".join(task.labels)]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _spec_text(task: Task) -> str:
        lines = [f"# Task: {task.title}", "", task.body or ""]
        if task.acceptance_criteria:
            lines += ["", "## Acceptance criteria"]
            lines += [f"- {c}" for c in task.acceptance_criteria]
        if task.non_goals:
            lines += ["", "## Non-goals"]
            lines += [f"- {c}" for c in task.non_goals]
        return "\n".join(lines)
