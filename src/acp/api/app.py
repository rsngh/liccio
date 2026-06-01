"""FastAPI application (charter §18)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from acp.api.service import AppService
from acp.schemas.human_review import HumanLabel
from acp.version import __version__


class CreateRepoRequest(BaseModel):
    name: str
    local_path: str
    default_branch: str = "main"


class CreateTaskRequest(BaseModel):
    repo_id: str
    title: str
    body: str = ""
    acceptance_criteria: list[str] = []
    metadata: dict[str, Any] = {}


class LabelRequest(BaseModel):
    verdict: str = "pass"
    score: float = 0.8
    reason: str = ""
    reviewer: str = "api"


def create_app(service: AppService | None = None) -> FastAPI:
    svc = service or AppService()
    app = FastAPI(title="agent-control-plane", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": __version__}

    @app.post("/repos", status_code=201)
    def create_repo(req: CreateRepoRequest) -> dict:
        return svc.create_repo(req.name, req.local_path, req.default_branch).model_dump(mode="json")

    @app.get("/repos")
    def list_repos() -> list[dict]:
        return [r.model_dump(mode="json") for r in svc.list_repos()]

    @app.get("/repos/{repo_id}")
    def get_repo(repo_id: str) -> dict:
        repo = svc.get_repo(repo_id)
        if repo is None:
            raise HTTPException(404, "repo not found")
        return repo.model_dump(mode="json")

    @app.post("/tasks", status_code=201)
    def create_task(req: CreateTaskRequest) -> dict:
        task = svc.create_task(
            req.repo_id, req.title, req.body,
            acceptance_criteria=req.acceptance_criteria, metadata=req.metadata,
        )
        return task.model_dump(mode="json")

    @app.get("/tasks")
    def list_tasks() -> list[dict]:
        return [t.model_dump(mode="json") for t in svc.list_tasks()]

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict:
        task = svc.get_task(task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        return task.model_dump(mode="json")

    @app.post("/tasks/{task_id}/run")
    def run_task(task_id: str) -> dict:
        try:
            state = svc.run_task(task_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return state.model_dump(mode="json")

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        state = svc.get_run(run_id)
        if state is None:
            raise HTTPException(404, "run not found")
        return state.model_dump(mode="json")

    @app.get("/runs/{run_id}/state")
    def get_run_state(run_id: str) -> dict:
        state = svc.get_run(run_id)
        if state is None:
            raise HTTPException(404, "run not found")
        return {"run_id": run_id, "status": state.status, "current_node": state.current_node}

    @app.get("/runs/{run_id}/graph")
    def run_graph(run_id: str) -> dict:
        try:
            return svc.full_run_graph(run_id)
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.get("/runs/{run_id}/trace")
    def run_trace(run_id: str) -> dict:
        try:
            return svc.run_trace(run_id)
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.get("/runs/{run_id}/diff")
    def run_diff(run_id: str) -> list[dict]:
        try:
            return svc.run_diff(run_id)
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.get("/runs/{run_id}/evidence")
    def run_evidence(run_id: str) -> list[dict]:
        try:
            return svc.run_evidence(run_id)
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.get("/runs/{run_id}/evaluation")
    def run_evaluation(run_id: str) -> dict | None:
        try:
            return svc.run_evaluation(run_id)
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        try:
            return svc.cancel_run(run_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc

    @app.get("/reviews")
    def list_reviews() -> list[dict]:
        return [i.model_dump(mode="json") for i in svc.list_reviews()]

    @app.get("/reviews/{review_id}")
    def get_review(review_id: str) -> dict:
        item = svc.get_review(review_id)
        if item is None:
            raise HTTPException(404, "review not found")
        return item.model_dump(mode="json")

    @app.post("/reviews/{review_id}/labels")
    def label_review(review_id: str, req: LabelRequest) -> dict:
        item = svc.get_review(review_id)
        if item is None:
            raise HTTPException(404, "review not found")
        label = HumanLabel(
            review_item_id=review_id, task_id=item.task_id, attempt_id=item.attempt_id,
            verdict=req.verdict, score=req.score, reason=req.reason, reviewer=req.reviewer,
        )
        svc.label_review(review_id, label)
        return label.model_dump(mode="json")

    @app.post("/reviews/{review_id}/resolve")
    def resolve_review(review_id: str) -> dict:
        item = svc.resolve_review(review_id)
        if item is None:
            raise HTTPException(404, "review not found")
        return item.model_dump(mode="json")

    @app.get("/policies")
    def list_policies() -> list[dict]:
        return [p.model_dump(mode="json") for p in svc.list_policies()]

    @app.post("/policies/train")
    def train_policy() -> dict:
        return svc.train_policy().model_dump(mode="json")

    @app.post("/policies/{policy_id}/promote")
    def promote_policy(policy_id: str) -> dict:
        try:
            return svc.promote_policy(policy_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(404, "policy not found") from exc

    @app.post("/policies/{policy_id}/rollback")
    def rollback_policy(policy_id: str) -> dict:
        try:
            return svc.rollback_policy(policy_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(404, "policy not found") from exc

    return app
