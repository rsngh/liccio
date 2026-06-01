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
        from acp.routing.bandit import SimulatedBanditPolicy

        # One persistent policy so routing learns across runs in this process.
        self.policy = SimulatedBanditPolicy(seed=self.settings.random_seed, epsilon=0.15)
        self._runs: dict[str, WorkflowState] = {}
        self._runners: dict[str, WorkflowRunner] = {}
        # Restore learned arm stats from the DB so routing learns across restarts.
        self._load_policy_state()

    def _load_policy_state(self) -> None:
        from acp.schemas.learning import PolicyState

        with session_scope(self.sessions) as s:
            states = EntityStore(s).list_by(PolicyState, policy_version=self.policy.policy_version)
        if states:
            latest = max(states, key=lambda x: x.updated_at)
            self.policy.import_arms(latest.arms)

    def save_policy_state(self):
        from acp.schemas.learning import PolicyState

        state = PolicyState(policy_version=self.policy.policy_version,
                            arms=self.policy.export_arms())
        self._save(state)
        return state

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

    def _save_state(self, state: WorkflowState) -> None:
        from acp.db import models as m

        payload = state.model_dump(mode="json")
        with session_scope(self.sessions) as session:
            row = session.get(m.RunState, state.run_id)
            kwargs = {
                "id": state.run_id, "data": payload, "task_id": state.task_id,
                "status": payload["status"], "trace_id": state.trace_id,
            }
            if row is None:
                session.add(m.RunState(**kwargs))
            else:
                for k, v in kwargs.items():
                    setattr(row, k, v)

    def _load_state(self, run_id: str) -> WorkflowState | None:
        from acp.db import models as m

        with session_scope(self.sessions) as session:
            row = session.get(m.RunState, run_id)
            if row is None:
                return None
            return WorkflowState.model_validate(row.data)

    def _persist_run(self, state: WorkflowState, artifacts: RunArtifacts) -> None:
        self._save_state(state)
        to_save: list[Any] = []
        if artifacts.task:
            to_save.append(artifacts.task)
        if artifacts.snapshot:
            to_save.append(artifacts.snapshot)
        if artifacts.context_pack:
            to_save.append(artifacts.context_pack)
        if artifacts.plan:
            to_save.append(artifacts.plan)
        if artifacts.routing_decision:
            to_save.append(artifacts.routing_decision)
        to_save.extend(artifacts.attempts)
        to_save.extend(artifacts.diffs.values())
        to_save.extend(artifacts.command_runs)
        to_save.extend(artifacts.verification_runs)
        to_save.extend(artifacts.evidence)
        if artifacts.evaluation:
            to_save.append(artifacts.evaluation)
        if artifacts.weak_label:
            to_save.append(artifacts.weak_label)
        if artifacts.review_item:
            to_save.append(artifacts.review_item)
        if artifacts.reward:
            to_save.append(artifacts.reward)
        to_save.extend(artifacts.spans)
        to_save.extend(getattr(artifacts, "agent_traces", []))
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
            policy=self.policy,
        )
        state = asyncio.run(runner.run(task))
        self._runs[state.run_id] = state
        self._runners[state.run_id] = runner
        self._save(state_to_task_status(task, state))
        # Persist learned arm stats so the policy survives restarts (R2-J).
        self.save_policy_state()
        return state

    def get_run(self, run_id: str) -> WorkflowState | None:
        return self._runs.get(run_id) or self._load_state(run_id)

    def _rehydrate_runner(self, state: WorkflowState) -> WorkflowRunner:
        """Rebuild a runner that can resume from persisted state at ANY node.

        Reconstructs all artifacts the remaining nodes might need from the DB
        (recomputing cheap/pure ones like classification and verdicts), so a
        crashed run can resume after a restart regardless of where it stopped.
        """
        from acp.core.classifier import classify
        from acp.schemas.agent import AgentAttempt
        from acp.schemas.context import ContextPack
        from acp.schemas.evaluation import EvaluationResult
        from acp.schemas.repo import RepoSnapshot
        from acp.schemas.routing import RoutingDecision
        from acp.schemas.verification import Evidence, VerificationPlan
        from acp.schemas.workspace import DiffBundle
        from acp.verification.aggregate import EvidenceAggregator

        repo = self.get_repo(state.repo_id or "")
        if repo is None:
            raise KeyError(state.repo_id)
        runner = WorkflowRunner(
            repo, self.registry, Path(self.settings.workspace_dir),
            artifact_store=self.artifact_store, on_persist=self._persist_run,
            policy=self.policy,
        )
        task = self.get_task(state.task_id)
        if task is not None:
            runner.submit(task)
            runner.artifacts.task = task
            runner.artifacts.classification = classify(task)

        with session_scope(self.sessions) as session:
            es = EntityStore(session)
            a = runner.artifacts
            if state.snapshot_id:
                a.snapshot = es.get(RepoSnapshot, state.snapshot_id)
            if state.context_pack_id:
                a.context_pack = es.get(ContextPack, state.context_pack_id)
            if state.verification_plan_id:
                a.plan = es.get(VerificationPlan, state.verification_plan_id)
            if state.routing_decision_id:
                a.routing_decision = es.get(RoutingDecision, state.routing_decision_id)
            if state.evaluation_result_id:
                a.evaluation = es.get(EvaluationResult, state.evaluation_result_id)
            a.attempts = es.list_by(AgentAttempt, task_id=state.task_id)
            attempt_ids = {att.id for att in a.attempts}
            for d in es.list_by(DiffBundle):
                if d.attempt_id in attempt_ids:
                    a.diffs[d.attempt_id] = d
            # group evidence by attempt + recompute verdicts (AggregateVerdict
            # is not persisted, but it is a pure function of evidence + diff).
            agg = EvidenceAggregator()
            tt = a.classification.task_type if a.classification else None
            for att in a.attempts:
                evs = [e for e in es.list_by(Evidence, task_id=state.task_id)
                       if e.attempt_id == att.id]
                a.evidence_by_attempt[att.id] = evs
                diff = a.diffs.get(att.id)
                from acp.evaluation.objective import diff_touches_tests

                a.verdicts[att.id] = agg.aggregate(
                    evs, diff=diff, task_type=tt,
                    diff_touches_tests=diff_touches_tests(diff),
                )
        return runner

    def resume_run(self, run_id: str, label: HumanLabel | None = None) -> WorkflowState:
        runner = self._runners.get(run_id)
        state = self._runs.get(run_id) or self._load_state(run_id)
        if state is None:
            raise KeyError(run_id)
        if runner is None:
            runner = self._rehydrate_runner(state)
        new_state = asyncio.run(runner.resume(state, label))
        self._runs[run_id] = new_state
        self._save_state(new_state)
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
        item = self.resolve_review(review_id)
        # Resume the paused run (rehydrating cross-process if needed).
        if item and item.run_id:
            self.resume_run(item.run_id, label)
        return label

    def resolve_review(self, review_id: str) -> HumanReviewItem | None:
        with session_scope(self.sessions) as s:
            item = EntityStore(s).get(HumanReviewItem, review_id)
            if item:
                item.status = "resolved"
                EntityStore(s).save(item)
        return item

    # ---- run inspection (round-1 §7) -------------------------------------

    def _children(self, run_id: str) -> dict[str, list]:
        state = self.get_run(run_id)
        if state is None:
            raise KeyError(run_id)
        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            return {k: list(v) for k, v in es.all_for_task(state.task_id).items()}

    def run_diff(self, run_id: str) -> list[dict]:
        from acp.schemas.workspace import DiffBundle

        with session_scope(self.sessions) as s:
            state = self.get_run(run_id)
            if state is None:
                raise KeyError(run_id)
            rows = [
                d for d in EntityStore(s).list_by(DiffBundle)
                if d.attempt_id in set(state.attempt_ids)
            ]
        return [d.model_dump(mode="json") for d in rows]

    def run_evidence(self, run_id: str) -> list[dict]:
        from acp.schemas.verification import Evidence

        return [e.model_dump(mode="json")
                for e in self._children(run_id).get(Evidence.__name__, [])]

    def run_evaluation(self, run_id: str) -> dict | None:
        from acp.schemas.evaluation import EvaluationResult

        evals = self._children(run_id).get(EvaluationResult.__name__, [])
        return evals[-1].model_dump(mode="json") if evals else None

    def full_run_graph(self, run_id: str) -> dict:
        """Reconstruct the entire run graph from storage (round-1 §A.1, D1B2).

        Relies only on the DB + artifact store — not the in-memory _runs/_runners.
        """
        from acp.schemas.agent import AgentAttempt
        from acp.schemas.context import ContextPack
        from acp.schemas.evaluation import EvaluationResult, WeakLabel
        from acp.schemas.human_review import HumanLabel, HumanReviewItem
        from acp.schemas.learning import PostMergeOutcome, RewardEvent
        from acp.schemas.repo import RepoSnapshot
        from acp.schemas.routing import RoutingDecision
        from acp.schemas.trace import AgentTrace, AuditEvent, SpanRecord
        from acp.schemas.verification import Evidence, VerificationPlan, VerificationRun
        from acp.schemas.workspace import CommandRunRecord, DiffBundle

        state = self.get_run(run_id)
        if state is None:
            raise KeyError(run_id)
        tid = state.task_id

        def dump(objs):
            return [o.model_dump(mode="json") for o in objs]

        with session_scope(self.sessions) as s:
            es = EntityStore(s)

            def one(cls, entity_id):
                obj = es.get(cls, entity_id) if entity_id else None
                return obj.model_dump(mode="json") if obj else None

            task = es.get(Task, tid)
            attempt_ids = set(state.attempt_ids)
            diffs = [d for d in es.list_by(DiffBundle) if d.attempt_id in attempt_ids]
            cmds = [c for c in es.list_by(CommandRunRecord) if c.trace_id == state.trace_id]
            graph = {
                "state": state.model_dump(mode="json"),
                "task": task.model_dump(mode="json") if task else None,
                "snapshot": one(RepoSnapshot, state.snapshot_id),
                "context_pack": one(ContextPack, state.context_pack_id),
                "verification_plan": one(VerificationPlan, state.verification_plan_id),
                "routing_decision": one(RoutingDecision, state.routing_decision_id),
                "attempts": dump(es.list_by(AgentAttempt, task_id=tid)),
                "diffs": dump(diffs),
                "command_runs": dump(cmds),
                "verification_runs": dump(es.list_by(VerificationRun, task_id=tid)),
                "evidence": dump(es.list_by(Evidence, task_id=tid)),
                "evaluation": one(EvaluationResult, state.evaluation_result_id),
                "weak_labels": dump(es.list_by(WeakLabel, task_id=tid)),
                "review_items": dump(es.list_by(HumanReviewItem, task_id=tid)),
                "human_labels": dump(es.list_by(HumanLabel, task_id=tid)),
                "reward_events": dump(es.list_by(RewardEvent, task_id=tid)),
                "post_merge_outcomes": dump(es.list_by(PostMergeOutcome, task_id=tid)),
                "spans": dump(es.list_by(SpanRecord, trace_id=state.trace_id)),
                "audit_events": dump(es.list_by(AuditEvent, trace_id=state.trace_id)),
                "agent_traces": dump(es.list_by(AgentTrace, task_id=tid)),
            }
        # Validate through the RunGraph schema so the shape is guaranteed.
        from acp.schemas.graph import RunGraph

        return RunGraph.model_validate(graph).model_dump(mode="json")

    def run_trace(self, run_id: str) -> dict:
        state = self.get_run(run_id)
        if state is None:
            raise KeyError(run_id)
        return {
            "run_id": run_id, "trace_id": state.trace_id,
            "completed_nodes": state.completed_nodes,
            "current_node": state.current_node, "status": state.status,
            "entities": {k: len(v) for k, v in self._children(run_id).items()},
        }

    def cancel_run(self, run_id: str) -> WorkflowState:
        state = self.get_run(run_id)
        if state is None:
            raise KeyError(run_id)
        from acp.core.enums import RunStatus

        state.status = RunStatus.CANCELLED
        self._save_state(state)
        self._runs[run_id] = state
        return state

    # ---- policies ---------------------------------------------------------

    def list_policies(self) -> list[PolicyVersion]:
        with session_scope(self.sessions) as s:
            return EntityStore(s).list_by(PolicyVersion)

    def create_policy(self, name: str, version: str, kind: str = "heuristic") -> PolicyVersion:
        p = PolicyVersion(name=name, version=version, kind=kind)
        self._save(p)
        return p

    def _registry(self):
        from acp.routing.registry import PolicyRegistry

        reg = PolicyRegistry()
        for p in self.list_policies():
            reg.register(p)
        return reg

    def promote_policy(self, policy_id: str, traffic_fraction: float = 1.0) -> PolicyVersion:
        reg = self._registry()
        promoted = reg.promote(policy_id, traffic_fraction=traffic_fraction)
        self._save(*reg.all())
        self._audit("policy_promotion", target=policy_id,
                    detail={"traffic": traffic_fraction})
        return promoted

    def rollback_policy(self, to_policy_id: str) -> PolicyVersion:
        reg = self._registry()
        champ = reg.rollback(to_policy_id)
        self._save(*reg.all())
        self._audit("policy_rollback", target=to_policy_id)
        return champ

    def train_policy(self, name: str = "bandit") -> PolicyVersion:
        """Snapshot the live bandit policy as a versioned PolicyVersion + metrics."""
        from acp.schemas.learning import RewardEvent

        arms = {ctx: {k: {"n": s.n, "mean": round(s.mean, 4)} for k, s in a.items()}
                for ctx, a in getattr(self.policy, "arms", {}).items()}
        with session_scope(self.sessions) as s:
            rewards = EntityStore(s).list_by(RewardEvent)
        n = len(rewards)
        metrics = {
            "reward_events": n,
            "reward_mean": round(sum(r.reward for r in rewards) / n, 4) if n else 0.0,
            "success_rate": round(sum(1 for r in rewards if r.reward > 0) / n, 4) if n else 0.0,
        }
        p = PolicyVersion(name=name, version=f"t{len(self.list_policies()) + 1}",
                          kind="bandit", params={"arms": arms}, metadata={"metrics": metrics})
        self._save(p)
        return p

    def drift_report(self, window: int = 10, drop_threshold: float = 0.3) -> dict:
        """Flag reward drift: compare the recent window mean vs the prior baseline."""
        from acp.schemas.learning import RewardEvent

        with session_scope(self.sessions) as s:
            rewards = sorted(EntityStore(s).list_by(RewardEvent),
                             key=lambda r: r.created_at)
        vals = [r.reward for r in rewards]
        report = {"n": len(vals), "drift_detected": False, "baseline_mean": 0.0,
                  "recent_mean": 0.0, "drop": 0.0}
        if len(vals) >= 2 * window:
            baseline = vals[-2 * window:-window]
            recent = vals[-window:]
            b = sum(baseline) / len(baseline)
            r = sum(recent) / len(recent)
            report.update(baseline_mean=round(b, 4), recent_mean=round(r, 4),
                          drop=round(b - r, 4),
                          drift_detected=(b - r) > drop_threshold * abs(b) if b else False)
        self._persist_eval("drift", report, report, config={"window": window})
        return report

    def agents_health(self) -> list[dict]:
        """Health + harness classification for every registered adapter (D2B6)."""
        import asyncio

        healths = asyncio.run(self.registry.healthcheck_all())
        out = []
        for name in self.registry.names():
            adapter = self.registry.get(name)
            h = healths.get(name)
            kind = adapter.kind if isinstance(adapter.kind, str) else adapter.kind.value
            out.append({
                "name": name, "kind": kind,
                "available": h.available if h else False,
                "detail": h.detail if h else "",
                "is_harness": getattr(adapter, "is_harness", False),
            })
        return out

    def agent_health(self, name: str) -> dict | None:
        return next((a for a in self.agents_health() if a["name"] == name), None)

    def off_policy_report(self) -> dict:
        """IPS/SNIPS + per-action stats over persisted decisions+rewards (D2B1)."""
        from acp.schemas.learning import RewardEvent
        from acp.schemas.routing import RoutingDecision

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            decisions = es.list_by(RoutingDecision)
            rewards = es.list_by(RewardEvent)
        reward_by_dec = {r.routing_decision_id: r.reward
                         for r in rewards if r.routing_decision_id}
        per_action: dict[str, list[float]] = {}
        ips_num = weight_sum = 0.0
        n = missing = 0
        covered = 0
        for d in decisions:
            if d.id not in reward_by_dec:
                continue
            reward = reward_by_dec[d.id]
            per_action.setdefault(d.action.key(), []).append(reward)
            p = d.action_probability
            if p is None or p <= 0:
                missing += 1
                continue
            covered += 1
            target_p = 1.0 / max(1, len(d.candidate_actions))
            w = target_p / p
            ips_num += w * reward
            weight_sum += w
            n += 1
        return {
            "n_decisions_with_reward": n,
            "missing_propensity": missing,
            "ips": round(ips_num / n, 6) if n else 0.0,
            "snips": round(ips_num / weight_sum, 6) if weight_sum else 0.0,
            "mean_reward_by_action": {
                k: round(sum(v) / len(v), 4) for k, v in per_action.items()
            },
            "propensity_coverage": round(covered / max(1, len(decisions)), 4),
        }

    def _audit(self, event_type: str, target: str | None = None, detail: dict | None = None):
        from acp.schemas.trace import AuditEvent

        self._save(AuditEvent(event_type=event_type, target=target, detail=detail or {}))

    # ---- persisted eval reports (round-2 Block F) ------------------------

    def _persist_eval(self, kind: str, summary: dict, report: dict,
                      cases: list[dict] | None = None, markdown: str = "",
                      config: dict | None = None):
        from acp.core.time import utcnow
        from acp.schemas.eval import EvalCase, EvalReport, EvalRun

        run = EvalRun(kind=kind, summary=summary, config=config or {}, finished_at=utcnow())
        to_save: list = [run, EvalReport(eval_run_id=run.id, content=report, markdown=markdown)]
        for c in cases or []:
            to_save.append(EvalCase(eval_run_id=run.id, name=str(c.get("name", "case")),
                                    metrics=c))
        self._save(*to_save)
        return run

    def run_context_benchmark(self, files: int = 100):
        import tempfile

        from acp.evaluation.retrieval_benchmark import (
            generate_synthetic_repo,
            report_to_markdown,
            run_benchmark,
        )

        repo = Path(tempfile.mkdtemp()) / "syn"
        gold = generate_synthetic_repo(repo, n_files=files)
        rep = run_benchmark(repo, gold)
        d = rep.to_dict()
        summary = {k: v for k, v in d.items() if k != "per_task"}
        return self._persist_eval("context_benchmark", summary, d,
                                  cases=d["per_task"], markdown=report_to_markdown(rep),
                                  config={"files": files})

    def run_bakeoff_eval(self, seeds: int = 2):
        import tempfile

        from acp.cli.demos import make_demo_repo
        from acp.core.config import ACPSettings
        from acp.evaluation.bakeoff import BakeoffConfig, bakeoff_to_markdown, run_bakeoff

        tmp = Path(tempfile.mkdtemp())
        sub = AppService(ACPSettings(
            database_url=f"sqlite+aiosqlite:///{tmp / 'b.db'}",
            artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
        ))
        repo = sub.create_repo("bakeoff", make_demo_repo(tmp / "repo"), default_branch="master")
        rep = run_bakeoff(sub, repo.id, BakeoffConfig(seeds=list(range(1, seeds + 1))))
        cases = [{**c, "name": f"{c['task_class']}/{c['strategy']}/s{c['seed']}"}
                 for c in rep["cells"]]
        return self._persist_eval("bakeoff", rep["summary"], rep, cases=cases,
                                  markdown=bakeoff_to_markdown(rep), config=rep["config"])

    def run_soak_eval(self, iterations: int = 15, task_mix: str = "bugfix"):
        import tempfile

        from acp.cli.demos import make_demo_repo
        from acp.core.config import ACPSettings
        from acp.evaluation.soak import run_soak, soak_to_markdown

        tmp = Path(tempfile.mkdtemp())
        sub = AppService(ACPSettings(
            database_url=f"sqlite+aiosqlite:///{tmp / 's.db'}",
            artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
        ))
        repo = sub.create_repo("soak", make_demo_repo(tmp / "repo"), default_branch="master")
        rep = run_soak(sub, repo.id, iterations=iterations, task_mix=task_mix.split(","))
        return self._persist_eval("soak", rep.get("thresholds", {}), rep,
                                  markdown=soak_to_markdown(rep),
                                  config={"iterations": iterations, "task_mix": task_mix})

    def list_eval_runs(self) -> list[dict]:
        from acp.schemas.eval import EvalRun

        with session_scope(self.sessions) as s:
            return [r.model_dump(mode="json") for r in EntityStore(s).list_by(EvalRun)]

    def get_eval_run(self, eval_run_id: str) -> dict | None:
        from acp.schemas.eval import EvalRun

        with session_scope(self.sessions) as s:
            r = EntityStore(s).get(EvalRun, eval_run_id)
            return r.model_dump(mode="json") if r else None

    def get_eval_report(self, eval_run_id: str) -> dict | None:
        from acp.schemas.eval import EvalReport

        with session_scope(self.sessions) as s:
            reports = EntityStore(s).list_by(EvalReport, eval_run_id=eval_run_id)
        return reports[0].model_dump(mode="json") if reports else None

    # ---- post-merge outcome loop (round-1 §9) ----------------------------

    def ingest_outcome(
        self,
        task_id: str,
        attempt_id: str | None,
        *,
        merged: bool = False,
        reverted: bool = False,
        incident_link: str | None = None,
        review_rounds: int = 0,
    ):
        """Record a post-merge outcome and mature the reward accordingly.

        A revert/incident emits a downward (matured) RewardEvent so the learning
        loop reflects real-world results, not just pre-merge verification.
        """
        from acp.core.time import utcnow
        from acp.schemas.evaluation import EvaluationResult
        from acp.schemas.learning import PostMergeOutcome

        outcome = PostMergeOutcome(
            task_id=task_id, attempt_id=attempt_id, merged=merged, reverted=reverted,
            incident_link=incident_link, review_rounds=review_rounds,
            merge_time=utcnow() if merged else None,
            revert_time=utcnow() if reverted else None,
        )
        self._save(outcome)

        if reverted or incident_link:
            from acp.routing.reward import compute_reward
            from acp.schemas.agent import AgentAttempt

            with session_scope(self.sessions) as s:
                es = EntityStore(s)
                attempts = es.list_by(AgentAttempt, task_id=task_id)
                evals = es.list_by(EvaluationResult, task_id=task_id)
            attempt = next(
                (a for a in attempts if a.id == attempt_id),
                attempts[0] if attempts else None,
            )
            evaluation = evals[-1] if evals else None
            if attempt is not None and evaluation is not None:
                matured = compute_reward(
                    evaluation, attempt, task_success=False,
                    reverted_or_incident=True, label_source="post_merge",
                )
                matured.matured_at = utcnow()
                self._save(matured)
                self._audit("post_merge_incident", target=task_id,
                            detail={"reverted": reverted, "incident": bool(incident_link)})
        return outcome


def state_to_task_status(task: Task, state: WorkflowState) -> Task:
    task.status = state.status if isinstance(state.status, str) else state.status.value
    return task
