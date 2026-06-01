"""Application service: wires DB, agents, runner, review queue (charter §18/§19).

A single AppService backs both the FastAPI app and the CLI so behavior is
identical. Uses the sync EntityStore for persistence and runs the workflow with
the fake/patch adapters by default (no external APIs required).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from acp.agents.fake import FakeAgentAdapter
from acp.agents.patch_agent import PatchAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.core.artifacts import LocalArtifactStore
from acp.core.config import ACPSettings, get_settings
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.orchestration.runner import RunArtifacts, WorkflowRunner
from acp.orchestration.state import WorkflowState
from acp.schemas.human_review import HumanLabel, HumanReviewItem
from acp.schemas.learning import PolicyVersion
from acp.schemas.repo import Repository
from acp.schemas.task import Task


class AppService:
    def __init__(self, settings: ACPSettings | None = None, registry: AgentRegistry | None = None):
        self.settings = settings or get_settings()
        self.engine = make_engine(self.settings.database_url)
        create_all(self.engine)
        self.sessions = make_session_factory(self.engine)
        self.artifact_store = LocalArtifactStore(self.settings.artifact_dir)
        self.registry = registry or self._default_registry()
        self._runs: dict[str, WorkflowState] = {}
        self._runners: dict[str, WorkflowRunner] = {}

    @staticmethod
    def _default_registry() -> AgentRegistry:
        reg = AgentRegistry()
        reg.register(PatchAgentAdapter())
        reg.register(FakeAgentAdapter())
        return reg

    # ---- persistence helpers ---------------------------------------------

    def _save(self, *entities) -> None:
        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            for e in entities:
                es.save(e)

    def _persist_run(self, state: WorkflowState, artifacts: RunArtifacts) -> None:
        to_save: list[Any] = []
        if artifacts.context_pack:
            to_save.append(artifacts.context_pack)
        if artifacts.routing_decision:
            to_save.append(artifacts.routing_decision)
        to_save.extend(artifacts.attempts)
        to_save.extend(artifacts.diffs.values())
        to_save.extend(artifacts.evidence)
        if artifacts.evaluation:
            to_save.append(artifacts.evaluation)
        if artifacts.review_item:
            to_save.append(artifacts.review_item)
        if artifacts.reward:
            to_save.append(artifacts.reward)
        if to_save:
            self._save(*to_save)

    # ---- repos / tasks ----------------------------------------------------

    def create_repo(self, name: str, local_path: str, default_branch: str = "main") -> Repository:
        repo = Repository(name=name, local_path=local_path, default_branch=default_branch)
        self._save(repo)
        return repo

    def get_repo(self, repo_id: str) -> Repository | None:
        with session_scope(self.sessions) as s:
            return EntityStore(s).get(Repository, repo_id)

    def list_repos(self) -> list[Repository]:
        with session_scope(self.sessions) as s:
            return EntityStore(s).list_by(Repository)

    def create_task(self, repo_id: str, title: str, body: str = "", **kw) -> Task:
        task = Task(repo_id=repo_id, title=title, body=body, **kw)
        self._save(task)
        return task

    def get_task(self, task_id: str) -> Task | None:
        with session_scope(self.sessions) as s:
            return EntityStore(s).get(Task, task_id)

    def list_tasks(self) -> list[Task]:
        with session_scope(self.sessions) as s:
            return EntityStore(s).list_by(Task)

    # ---- runs -------------------------------------------------------------

    def run_task(self, task_id: str) -> WorkflowState:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        repo = self.get_repo(task.repo_id)
        if repo is None:
            raise KeyError(task.repo_id)
        runner = WorkflowRunner(
            repo, self.registry, Path(self.settings.workspace_dir),
            artifact_store=self.artifact_store, on_persist=self._persist_run,
        )
        state = asyncio.run(runner.run(task))
        self._runs[state.run_id] = state
        self._runners[state.run_id] = runner
        self._save(state_to_task_status(task, state))
        return state

    def get_run(self, run_id: str) -> WorkflowState | None:
        return self._runs.get(run_id)

    def resume_run(self, run_id: str, label: HumanLabel) -> WorkflowState:
        runner = self._runners[run_id]
        state = self._runs[run_id]
        new_state = asyncio.run(runner.resume(state, label))
        self._runs[run_id] = new_state
        return new_state

    # ---- reviews ----------------------------------------------------------

    def list_reviews(self) -> list[HumanReviewItem]:
        with session_scope(self.sessions) as s:
            return [i for i in EntityStore(s).list_by(HumanReviewItem) if i.status == "open"]

    def get_review(self, review_id: str) -> HumanReviewItem | None:
        with session_scope(self.sessions) as s:
            return EntityStore(s).get(HumanReviewItem, review_id)

    def label_review(self, review_id: str, label: HumanLabel) -> HumanLabel:
        self._save(label)
        # resolve the item + resume its run if known
        with session_scope(self.sessions) as s:
            item = EntityStore(s).get(HumanReviewItem, review_id)
            if item:
                item.status = "resolved"
                EntityStore(s).save(item)
        if item and item.run_id and item.run_id in self._runners:
            self.resume_run(item.run_id, label)
        return label

    # ---- policies ---------------------------------------------------------

    def list_policies(self) -> list[PolicyVersion]:
        with session_scope(self.sessions) as s:
            return EntityStore(s).list_by(PolicyVersion)

    def create_policy(self, name: str, version: str, kind: str = "heuristic") -> PolicyVersion:
        p = PolicyVersion(name=name, version=version, kind=kind)
        self._save(p)
        return p


def state_to_task_status(task: Task, state: WorkflowState) -> Task:
    task.status = state.status if isinstance(state.status, str) else state.status.value
    return task
