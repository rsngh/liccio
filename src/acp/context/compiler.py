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
        embedder=None,
        vector_store=None,
        settings=None,
    ) -> None:
        self.repo_path = repo_path
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.weights = weights
        self.prior_paths = prior_paths
        # When no embedder/store is supplied, select one from settings (degrades
        # to hashing + in-memory). Choices are recorded for the retrieval trace.
        # The vector store, if auto-selected, is (re)built per compile() so its
        # state never leaks across compilations of the same instance.
        self.settings = settings
        self.backend_notes: list[str] = []
        if embedder is None:
            from acp.context.factory import make_embedder

            ec = make_embedder(settings)
            embedder = ec.embedder
            self.backend_notes.append(f"embedder={ec.backend} ({ec.reason})")
        self.embedder = embedder
        self._auto_vector_store = vector_store is None
        self.vector_store = vector_store

    def compile(
        self,
        task: Task,
        strategy: str = "hybrid_keyword_embedding",
        token_budget: int = 80_000,
        top_k: int = 60,
    ) -> ContextPack:
        index = RepoIndexer(self.repo_path, self.repo_id, self.snapshot_id).index()
        query = self._build_query(task)

        # Build a fresh auto-selected store per compile so state never leaks
        # across compilations; an explicitly supplied store is used as given.
        compile_notes = list(self.backend_notes)
        vector_store = self.vector_store
        if self._auto_vector_store:
            from acp.context.factory import make_vector_store

            vc = make_vector_store(self.settings)
            vector_store = vc.store
            compile_notes.append(f"vector_store={vc.backend} ({vc.reason})")

        retriever = HybridRetriever(
            index.chunks, embedder=self.embedder, weights=self.weights,
            prior_paths=self.prior_paths, vector_store=vector_store,
            snapshot_id=self.snapshot_id,
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

        # repo_map strategy (Aider-style, research-backed): prepend a graph-ranked map of the
        # whole repo's key signatures so the model sees APIs from everywhere, then let normal
        # retrieval supply full bodies for depth. The map is a required item, capped to a slice
        # of the budget so it never crowds out the retrieved chunks.
        if strategy == "repo_map":
            from acp.context.repo_map import build_repo_map

            map_budget = max(256, min(token_budget // 4, 2048))
            rmap = build_repo_map(
                RepoIndexer(self.repo_path, self.repo_id, self.snapshot_id).collect_sources(),
                token_budget=map_budget,
            )
            if rmap.text:
                required.insert(1, make_chunk(
                    kind="repo_map_chunk", path="__repo_map__", content=rmap.text,
                    source="repo_map", repo_id=self.repo_id, snapshot_id=self.snapshot_id))

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
            notes=[*trace.notes, f"required={len(required)}", *compile_notes],
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
