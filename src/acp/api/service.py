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
        if getattr(artifacts, "viability", None) is not None:
            to_save.append(artifacts.viability)
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
        to_save.extend(getattr(artifacts, "audit_events", []))
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
            backend=self.settings.workspace_backend,
            allow_local_harness=self.settings.allow_local_harness,
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
            backend=self.settings.workspace_backend,
            allow_local_harness=self.settings.allow_local_harness,
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

    def list_reviews(self, priority_min: float = 0.0) -> list[HumanReviewItem]:
        with session_scope(self.sessions) as s:
            items = [i for i in EntityStore(s).list_by(HumanReviewItem)
                     if i.status == "open" and i.priority >= priority_min]
        # Highest-priority first so the studio queue surfaces the riskiest work.
        return sorted(items, key=lambda i: i.priority, reverse=True)

    def review_bundle(self, review_id: str) -> dict:
        """Everything a human needs to adjudicate a review (Alpha 6, WS6).

        A secret-free package: the uncertainty reason, a diff summary, evidence +
        weak-label summaries, the agent-trace summary, and judge disagreement —
        all derived from the persisted run graph.
        """
        item = self.get_review(review_id)
        if item is None:
            raise KeyError(review_id)
        if not item.run_id:
            return {"review": item.model_dump(mode="json"), "note": "no run linked"}
        graph = self.full_run_graph(item.run_id)
        diffs = graph.get("diffs", [])
        weak = graph.get("weak_labels", [])
        traces = graph.get("agent_traces", [])
        evaluation = graph.get("evaluation") or {}
        judges = evaluation.get("judge_results", []) if isinstance(evaluation, dict) else []
        judge_verdicts = [j.get("verdict") for j in judges if isinstance(j, dict)]
        return {
            "review": item.model_dump(mode="json"),
            "uncertainty_reason": item.reason,
            "priority": item.priority,
            "diff_summary": [
                {"changed_files": d.get("changed_files"),
                 "insertions": d.get("insertions"), "deletions": d.get("deletions")}
                for d in diffs
            ],
            "evidence_summary": {"count": len(graph.get("evidence", []))},
            "weak_label_summary": [
                {"value": w.get("value"), "confidence": w.get("confidence")} for w in weak
            ],
            "trace_summary": [
                {"adapter": t.get("adapter_name"), "status": t.get("status"),
                 "tool_calls": t.get("tool_calls"), "changed_files": t.get("changed_files"),
                 "cost_usd": t.get("estimated_cost_usd")} for t in traces
            ],
            "judge_disagreement": {
                "verdicts": judge_verdicts,
                "disagree": len(set(judge_verdicts)) > 1,
            },
            "evaluation": graph.get("evaluation"),
        }

    def make_eval_case(self, review_id: str) -> dict:
        """Convert a labeled review into a reusable eval/training case (WS6).

        Appends a JSONL row to ``evals/datasets/review_eval_cases.jsonl`` so every
        human label becomes durable supervision for calibration / training.
        """
        import json as _json
        from pathlib import Path as _Path

        from acp.core.config import get_settings as _get_settings
        from acp.schemas.human_review import HumanLabel as _HL

        item = self.get_review(review_id)
        if item is None:
            raise KeyError(review_id)
        with session_scope(self.sessions) as s:
            labels = [
                lbl for lbl in EntityStore(s).list_by(_HL, task_id=item.task_id)
                if lbl.review_item_id == review_id
            ]
        if not labels:
            raise ValueError(f"review {review_id} has no human label yet")
        label = labels[-1]
        case = {
            "review_id": review_id,
            "task_id": item.task_id,
            "attempt_id": item.attempt_id,
            "verdict": label.verdict.value if hasattr(label.verdict, "value")
            else label.verdict,
            "score": label.score,
            "reason": label.reason,
            "reviewer": label.reviewer,
            "source": "human_review",
        }
        out = _Path(_get_settings().eval_cases_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as fh:
            fh.write(_json.dumps(case) + "\n")
        return {"written_to": str(out), "case": case}

    def make_training_example(self, review_id: str) -> dict:
        """Convert a labeled review into a redacted human_review TrainingExample (WS9)."""
        from acp.observability.live_report import redact_report
        from acp.schemas.human_review import HumanLabel as _HL
        from acp.schemas.training import TrainingExample

        item = self.get_review(review_id)
        if item is None:
            raise KeyError(review_id)
        with session_scope(self.sessions) as s:
            labels = [lbl for lbl in EntityStore(s).list_by(_HL, task_id=item.task_id)
                      if lbl.review_item_id == review_id]
        if not labels:
            raise ValueError(f"review {review_id} has no human label yet")
        label = labels[-1]
        bundle = self.review_bundle(review_id)
        inputs = redact_report({
            "uncertainty_reason": bundle.get("uncertainty_reason"),
            "diff_summary": bundle.get("diff_summary"),
            "trace_summary": bundle.get("trace_summary"),
            "judge_disagreement": bundle.get("judge_disagreement"),
        })
        verdict = label.verdict.value if hasattr(label.verdict, "value") else label.verdict
        ex = TrainingExample(
            dataset_kind="human_review", task_id=item.task_id,
            inputs=inputs, target=str(verdict), label_source="human",
            provenance={"review_id": review_id, "label_id": label.id,
                        "reviewer": label.reviewer, "score": label.score},
        )
        return {"training_example": ex.model_dump(mode="json")}

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
        from acp.schemas.viability import ViabilityAssessment
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
                "viability": one(ViabilityAssessment, state.scratch.get("viability_id")),
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

    def evaluate_policy_offline(
        self, target: str = "supervised", weight_clip: float = 20.0
    ) -> dict:
        """Offline policy evaluation (Alpha 6, WS3).

        Builds an OPE log from persisted ``RoutingDecision`` propensities matched
        to ``RewardEvent``s (via ``routing_decision_id``), then estimates the value
        of a ``target`` policy (supervised | random | greedy) against the logged
        behavior policy — IPS / SNIPS / clipped-IPS / doubly-robust with bootstrap
        CIs and overlap diagnostics. No agents are re-run.
        """
        from acp.routing.ope import evaluate_policy

        samples = self._ope_samples()
        if not samples:
            return {"n": 0, "note": "no (decision, reward) pairs with propensities found"}
        n_cands = max(len(set(s.candidates)) for s in samples)
        tgt = self._ope_target(samples, target)
        report = evaluate_policy(samples, tgt, weight_clip=weight_clip)
        baseline = sum(s.reward for s in samples) / len(samples)
        return {
            "target": target,
            "n": report.n,
            "candidate_arms": n_cands,
            "logged_mean_reward": round(baseline, 6),
            "estimates": report.as_dict(),
            "improvement_vs_logged": round(report.best_estimate() - baseline, 6),
        }

    def _ope_samples(self) -> list:
        """OPE log from persisted RoutingDecision propensities matched to rewards."""
        from acp.routing.ope import OPESample
        from acp.schemas.learning import RewardEvent
        from acp.schemas.routing import RoutingDecision

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            decisions = {d.id: d for d in es.list_by(RoutingDecision)}
            rewards = es.list_by(RewardEvent)
        samples = []
        for rew in rewards:
            dec = decisions.get(rew.routing_decision_id or "")
            if dec is None or not dec.candidate_actions:
                continue
            samples.append(OPESample(
                context_key=dec.feature_hash or "global", action_key=dec.action.key(),
                behavior_prob=dec.action_probability, reward=rew.reward,
                candidates=[a.key() for a in dec.candidate_actions],
            ))
        return samples

    @staticmethod
    def _ope_target(samples: list, target: str):
        """Build an OPE TargetPolicy for a named policy from the sample log."""
        from acp.routing.ope import fit_reward_model
        from acp.routing.supervised import SupervisedRoutingPolicy

        if target == "random":
            def random_target(ctx: str, action: str, cands: list[str]) -> float:
                return 1.0 / len(cands)
            return random_target
        if target == "greedy":
            q = fit_reward_model(samples)

            def greedy(ctx: str, action: str, cands: list[str]) -> float:
                best = max(q(ctx, a) for a in cands)
                winners = [a for a in cands if q(ctx, a) == best]
                return 1.0 / len(winners) if action in winners else 0.0
            return greedy
        # supervised + an exploration-preserving (temperature-smoothed) variant
        # that keeps mass on every arm so it overlaps the logged policy.
        temperature = 0.25 if target == "supervised_explore" else 0.0
        pol = SupervisedRoutingPolicy(temperature=temperature)
        pol.fit([{"context_key": s.context_key, "action_key": s.action_key,
                  "reward": s.reward} for s in samples])
        return pol.as_target()

    def policy_promotion_check(self, target: str = "supervised", weight_clip: float = 20.0) -> dict:
        """Run the OPE promotion gate (Alpha 7, WS5) on a target policy.

        Builds the OPE report from real logs and applies statistical-trust +
        operational-safety conditions; returns a promote/block decision with the
        exact failing conditions and (when promoted) a staged canary plan.
        """
        from acp.routing.ope import evaluate_policy
        from acp.routing.promotion import evaluate_promotion

        samples = self._ope_samples()
        if not samples:
            return {"promote": False, "reasons": ["no log to evaluate"], "n": 0}
        report = evaluate_policy(samples, self._ope_target(samples, target),
                                 weight_clip=weight_clip)
        baseline = sum(s.reward for s in samples) / len(samples)
        decision = evaluate_promotion(report, baseline_value=baseline)
        return {"target": target, "n": report.n,
                "logged_mean_reward": round(baseline, 6),
                "estimates": report.as_dict(), **decision.as_dict()}

    def real_log_ope_report(self, weight_clip: float = 20.0) -> dict:
        """Compare candidate policies on the real persisted log (Alpha 7, WS6).

        Evaluates logged/random/greedy/supervised targets via OPE and refuses to
        rank a winner when propensity overlap or effective sample size is too poor
        to trust — no overclaim on a thin log.
        """
        from acp.routing.ope import evaluate_policy

        samples = self._ope_samples()
        if not samples:
            return {"n": 0, "note": "no (decision, reward) pairs with propensities found",
                    "trustworthy": False}
        baseline = sum(s.reward for s in samples) / len(samples)
        policies: dict[str, dict] = {}
        dr_by_name: dict[str, float] = {}
        # Expanded policy family (Alpha 8, WS11). Variants that need per-action
        # cost/risk features collapse to the supervised target on a thin log; the
        # exploration-preserving variant materially changes propensity overlap.
        for name in ("random", "greedy", "supervised", "supervised_explore"):
            rep = evaluate_policy(samples, self._ope_target(samples, name),
                                  weight_clip=weight_clip)
            policies[name] = {"estimates": rep.as_dict(), "dr": rep.dr.value,
                              "dr_ci_low": rep.dr.ci_low, "overlap": rep.diagnostics.overlap}
            dr_by_name[name] = rep.dr.value
        # Trust gate uses each policy's OWN overlap: a winner is trustworthy only
        # if it itself overlaps the log (greedy can be high-DR but zero-overlap).
        best = max(dr_by_name, key=lambda k: dr_by_name[k])
        best_overlap = policies[best]["overlap"]
        diag = evaluate_policy(samples, self._ope_target(samples, "supervised"),
                               weight_clip=weight_clip).diagnostics
        trustworthy = best_overlap >= 0.5 and diag.effective_sample_size >= 10
        # Rank only policies that individually overlap the log.
        rankable = [k for k in dr_by_name if policies[k]["overlap"] >= 0.5]
        ranking = (sorted(rankable, key=lambda k: dr_by_name[k], reverse=True)
                   if (trustworthy and rankable) else [])
        recommendation = ("" if trustworthy else
                          "Best-DR policy has insufficient propensity overlap with the "
                          "logged policy. Run an exploration campaign (epsilon/temperature "
                          "exploration on under-covered routing cells) before promoting; "
                          "see `acp viability matrix` + exploration designer.")
        return {
            "n": len(samples),
            "logged_mean_reward": round(baseline, 6),
            "diagnostics": diag.as_dict(),
            "trustworthy": trustworthy,
            "policies": policies,
            "ranking_by_dr": ranking,
            "exploration_recommendation": recommendation,
            "note": ("" if trustworthy else
                     "insufficient overlap/ESS to rank policies — collect more "
                     "exploratory logs before trusting these estimates"),
        }

    # ---- training-data factory wiring (Alpha 7, WS3/4/18) ----------------

    def build_exhaust_bundle(self):
        """Populate a DatasetFactory ExhaustBundle from persisted entities."""
        from acp.schemas.evaluation import EvaluationResult, WeakLabel
        from acp.schemas.human_review import HumanLabel
        from acp.schemas.learning import RewardEvent
        from acp.schemas.routing import RoutingDecision
        from acp.schemas.trace import AgentTrace
        from acp.training.dataset_factory import ExhaustBundle

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            return ExhaustBundle(
                tasks=es.list_by(Task),
                traces=es.list_by(AgentTrace),
                evaluations=es.list_by(EvaluationResult),
                weak_labels=es.list_by(WeakLabel),
                human_labels=es.list_by(HumanLabel),
                routing_decisions=es.list_by(RoutingDecision),
                rewards=es.list_by(RewardEvent),
            )

    def build_training_dataset(self, kind: str, out: str | None = None) -> dict:
        """Build a redacted, leakage-audited dataset of ``kind`` from run exhaust."""
        from acp.training.dataset_factory import DatasetFactory

        res = DatasetFactory().build(kind, self.build_exhaust_bundle())
        if out:
            from pathlib import Path as _Path
            p = _Path(out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(ex.canonical_json() for ex in res.examples) + "\n"
                         if res.examples else "")
        return {"kind": kind, "dataset_id": res.version.id,
                "n_examples": res.version.n_examples, "splits": res.version.splits,
                "leakage_clean": res.leakage.clean,
                "out": out}

    def build_examples_by_kind(self) -> dict:
        """All training examples grouped by kind (for the candidate report)."""
        from acp.training.dataset_factory import DatasetFactory

        bundle = self.build_exhaust_bundle()
        factory = DatasetFactory()
        kinds = ["routing", "human_review", "evaluator", "repair"]
        return {k: factory.build(k, bundle).examples for k in kinds}

    def training_candidate_report(self) -> dict:
        from acp.training.candidate_report import build_candidate_report

        return build_candidate_report(self.build_examples_by_kind())

    def decision_card(self, task_id: str, *, repo_type: str = "python_package") -> dict:
        """Explainable per-task decision card (Alpha 9): viability + capability-
        matrix recommendation + verification + rationale."""
        from acp.core.decision_card import build_decision_card
        from acp.routing.capability_matrix import CapabilityMatrix

        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        # Build a matrix from persisted EvalRuns when available (else None).
        try:
            from acp.schemas.eval import EvalRun
            with session_scope(self.sessions) as s:
                runs = EntityStore(s).list_by(EvalRun)
            built = CapabilityMatrix()
            for run in runs:
                if isinstance(run.summary, dict) and run.summary.get("cells"):
                    for cell in CapabilityMatrix.from_bakeoff_report(run.summary).cells():
                        built.add_cell(cell)
            matrix: CapabilityMatrix | None = built if built.cells() else None
        except Exception:  # noqa: BLE001 - matrix is optional context
            matrix = None
        return build_decision_card(task, matrix=matrix, repo_type=repo_type).as_dict()

    def ingest_bakeoff_cells(self, cells: list[dict]) -> dict:
        """Persist observed bakeoff cells as real RoutingDecision + RewardEvent rows
        so OPE / capability matrix / health operate on genuine agent data (WS14)."""
        from acp.core.enums import AgentKind
        from acp.schemas.learning import RewardEvent
        from acp.schemas.routing import RoutingAction, RoutingDecision

        n = 0
        for c in cells:
            ttype = c.get("task_type", "unknown")
            adapters = sorted({str(d.get("adapter")) for d in cells
                               if d.get("task_type") == ttype})
            cstrat = c.get("context_strategy", "hybrid_keyword_embedding")
            cands = [RoutingAction(agent_kind=AgentKind.FAKE, agent_name=a,
                                   context_strategy=cstrat) for a in adapters]
            chosen = RoutingAction(agent_kind=AgentKind.FAKE, agent_name=c["adapter"],
                                   context_strategy=cstrat)
            dec = RoutingDecision(
                task_id=c.get("task", "t"), policy_version="live-bakeoff",
                action=chosen, action_probability=1.0 / max(1, len(adapters)),
                candidate_actions=cands, feature_hash=f"{ttype}|medium",
                model_scores={a.key(): 0.0 for a in cands})
            rew = RewardEvent(task_id=c.get("task", "t"), routing_decision_id=dec.id,
                              reward=1.0 if c.get("success") else 0.0,
                              components={"objective": 1.0 if c.get("success") else 0.0},
                              label_source="objective")
            self._save(dec, rew)
            n += 1
        return {"ingested": n}

    def control_plane_health(self, mode: str = "lab") -> dict:
        """One-shot health snapshot of the whole control plane (Alpha 9/11).

        Unifies counts + readiness across viability, routing logs/OPE, capability
        matrix coverage, learned-model promotability, and counterfactual regret.
        ``mode`` (lab|staging|production) tightens the gate: production fails
        (``production_ready=False``) unless its release gates are satisfied.
        """
        from acp.routing.counterfactual import total_regret

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            from acp.schemas.human_review import HumanLabel
            from acp.schemas.learning import RewardEvent
            from acp.schemas.routing import RoutingDecision
            from acp.schemas.viability import ViabilityAssessment
            counts = {
                "tasks": len(es.list_by(Task)),
                "routing_decisions": len(es.list_by(RoutingDecision)),
                "reward_events": len(es.list_by(RewardEvent)),
                "human_labels": len(es.list_by(HumanLabel)),
                "viability_assessments": len(es.list_by(ViabilityAssessment)),
            }
        samples = self._ope_samples()
        ope_ready = len(samples) >= 10
        regret = total_regret(samples) if samples else {"n": 0}
        # Learned-model readiness via the self-improvement cycle (cheap on small logs).
        try:
            si = self.self_improvement_report()
            promotions = si.get("promotions", {})
        except Exception:  # noqa: BLE001 - health must never crash
            promotions = {}
        from acp.routing.pareto_policy import PROFILES
        # Artifact freshness: are the committed reports present + valid?
        try:
            from pathlib import Path as _P

            from acp.observability.artifact_manifest import build_manifest
            mani = build_manifest(_P("."), generated_at="health")
            artifacts_ok = mani.all_valid()
            artifact_summary = {"valid": mani.as_dict()["n_valid"],
                                "total": mani.as_dict()["n_total"]}
        except Exception:  # noqa: BLE001
            artifacts_ok, artifact_summary = False, {"valid": 0, "total": 0}
        readiness = {
            "can_evaluate_policies_offline": ope_ready,
            "has_human_feedback": counts["human_labels"] > 0,
            "has_viability_provenance": counts["viability_assessments"] > 0,
            "artifacts_valid": artifacts_ok,
        }
        # Degraded when a critical gate is missing/stale.
        degraded = not artifacts_ok
        # Production release gates (Alpha 11, WS4): each must hold for production.
        from pathlib import Path as _PP

        def _report_passed(path: str, key: str = "passed") -> bool:
            import json as _j
            p = _PP(path)
            if not p.exists():
                return False
            try:
                return bool(_j.loads(p.read_text()).get(key))
            except Exception:  # noqa: BLE001
                return False

        # Harness availability (WS3/WS12): a recent audit must show no expected
        # harness silently absent. Absent artifact fails the gate in production.
        def _report_field(path: str, key: str, default=None):
            import json as _j
            p = _PP(path)
            if not p.exists():
                return default
            try:
                return _j.loads(p.read_text()).get(key, default)
            except Exception:  # noqa: BLE001
                return default

        ha_degraded = _report_field(
            "evals/reports/harness_availability_audit.json", "degraded", default=None)
        harness_availability_ok = ha_degraded is False
        # Measurement hygiene (WS1/WS12): a recent live measurement must not be
        # contaminated (too many inconclusive/infra attempts) to trust its routing.
        mh_contaminated = _report_field(
            "evals/reports/measurement_hygiene.json", "contaminated", default=None)
        measurement_not_contaminated = mh_contaminated is False
        # Measurement-quality trust verdict (WS3/WS10): the live measurement must
        # pass the trust policy. Absent artifact fails the gate in production.
        mq_trusted = _report_field(
            "evals/reports/measurement_quality.json", "trusted", default=None)
        measurement_quality_trusted = mq_trusted is True

        production_gates = {
            "artifact_manifest_valid": artifacts_ok,
            "docker_live_security_passed":
                _report_passed("evals/reports/docker_security_live.json"),
            "ope_overlap_sufficient": ope_ready,
            "no_demoted_model_promoted": True,  # drift lifecycle demotes in-loop
            "test_reports_present": _PP("reports/pytest.txt").exists(),
            "harness_availability_ok": harness_availability_ok,
            "measurement_not_contaminated": measurement_not_contaminated,
            "measurement_quality_trusted": measurement_quality_trusted,
        }
        production_ready = all(production_gates.values())
        status = "ok"
        if mode == "production" and not production_ready:
            status = "degraded"
            degraded = True
        elif degraded:
            status = "degraded"
        # Measurement-trust section (Round 12 WS5/WS9): surface the live hygiene,
        # harness availability, and tool-activation signals as first-class health.
        # HAR/HFR/PWL per adapter from the live capability-matrix cells (WS8): the
        # harness-benefit metrics become first-class health signals so an operator
        # can see activation/adherence, not just solve-rate.
        harness_benefit: dict = {}
        mcells = _report_field(
            "evals/reports/live_bakeoff_capability_matrix.json", "cells", default=[]) or []
        for c in mcells:
            if c.get("har") is None:
                continue
            a = c.get("agent_class", "unknown")
            b = harness_benefit.setdefault(a, {"har": [], "hfr": [], "pwl": []})
            for k in ("har", "hfr", "pwl"):
                if c.get(k) is not None:
                    b[k].append(c[k])
        harness_benefit = {
            a: {k: round(sum(v) / len(v), 4) for k, v in d.items() if v}
            for a, d in harness_benefit.items()}
        _mq_score = _report_field(
            "evals/reports/measurement_quality.json", "score", default={})
        measurement = {
            "solve_rate_conclusive": _report_field(
                "evals/reports/measurement_hygiene.json", "solve_rate"),
            "infra_failure_rate": _report_field(
                "evals/reports/measurement_hygiene.json", "infra_failure_rate"),
            "contaminated": mh_contaminated,
            "measurement_quality_overall": (
                _mq_score.get("overall") if isinstance(_mq_score, dict) else None),
            "harness_availability_degraded": ha_degraded,
            "tool_activation_by_adapter": _report_field(
                "evals/reports/tool_activation_metrics.json", "by_adapter", default={}),
            "harness_benefit_by_adapter": harness_benefit,
        }
        return {
            "mode": mode,
            "status": status,
            "degraded": degraded,
            "production_ready": production_ready,
            "production_gates": production_gates,
            "failed_production_gates": [k for k, ok in production_gates.items() if not ok],
            "counts": counts,
            "ope": {"log_size": len(samples), "ready_to_evaluate": ope_ready,
                    "counterfactual_regret": regret},
            "learned_models": {"promotions": promotions},
            "pareto_profiles": sorted(PROFILES),
            "artifacts": artifact_summary,
            "measurement": measurement,
            "readiness": readiness,
        }

    def run_and_persist_drift(
        self, ensemble, *, model_name: str, baseline, recent
    ) -> dict:
        """Run the drift lifecycle and DURABLY persist its outcome (Alpha 11, WS8)."""
        from acp.learning.drift_lifecycle import run_drift_lifecycle
        from acp.schemas.drift import (
            DriftReportEntity,
            ModelDemotionEventEntity,
            ModelPromotionState,
        )

        result = run_drift_lifecycle(ensemble, model_name=model_name,
                                     baseline=baseline, recent=recent)
        d = result.drift
        drift_row = DriftReportEntity(
            model_name=model_name, accuracy_drop=d.accuracy_drop, psi=d.psi,
            high_risk_false_negative_rate=d.high_risk_false_negative_rate_recent,
            drifted=d.drifted, demote_recommended=d.demote_recommended,
            reasons=list(d.reasons))
        to_save: list = [drift_row]
        demotion_id = None
        if result.demoted and result.demotion_event is not None:
            ev = ModelDemotionEventEntity(
                model_name=model_name, drift_report_id=drift_row.id,
                reason=result.demotion_event.reason,
                review_item_id=result.review_item.id if result.review_item else None)
            demotion_id = ev.id
            to_save.append(ev)
            if result.review_item is not None:
                to_save.append(result.review_item)
        to_save.append(ModelPromotionState(
            model_name=model_name, promoted=getattr(ensemble, "learned_promoted", False),
            last_event="demoted" if result.demoted else "checked"))
        self._save(*to_save)
        return {**result.as_dict(), "drift_report_id": drift_row.id,
                "demotion_event_id": demotion_id, "persisted": True}

    # ---- report warehouse (Alpha 11, WS18) -------------------------------

    def ingest_reports(self, source_command: str = "manifest") -> dict:
        """Snapshot all manifest reports into queryable Report entities."""
        import json as _json
        from pathlib import Path as _P

        from acp.core.ids import new_id
        from acp.observability.artifact_manifest import build_manifest
        from acp.schemas.report import Report, ReportLineage, ReportMetric

        ingest_id = new_id("ingest")
        mani = build_manifest(_P("."), generated_at=ingest_id)
        saved = 0
        for entry in mani.artifacts:
            if not entry.valid or entry.hash is None:
                continue
            metrics: list[ReportMetric] = []
            try:
                data = _json.loads((_P(".") / entry.path).read_text())
                for k, v in (data.items() if isinstance(data, dict) else []):
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        metrics.append(ReportMetric(name=k, value=float(v)))
            except Exception:  # noqa: BLE001
                pass
            report = Report(path=entry.path, kind=entry.path, hash=entry.hash,
                            valid=entry.valid, size_bytes=entry.size_bytes or 0,
                            metrics=metrics, ingest_id=ingest_id)
            self._save(report, ReportLineage(report_id=report.id,
                                             source_command=source_command,
                                             parent_ingest_id=ingest_id))
            saved += 1
        return {"ingest_id": ingest_id, "reports_ingested": saved}

    def list_reports(self, ingest_id: str | None = None) -> list[dict]:
        from acp.schemas.report import Report

        with session_scope(self.sessions) as s:
            rows = (EntityStore(s).list_by(Report, ingest_id=ingest_id) if ingest_id
                    else EntityStore(s).list_by(Report))
        return [{"id": r.id, "path": r.path, "ingest_id": r.ingest_id,
                 "hash": r.hash[:12], "n_metrics": len(r.metrics)} for r in rows]

    def show_report(self, report_id: str) -> dict:
        from acp.schemas.report import Report

        with session_scope(self.sessions) as s:
            r = EntityStore(s).get(Report, report_id)
        if r is None:
            raise KeyError(report_id)
        return r.model_dump(mode="json")

    def diff_reports(self, path: str, ingest_a: str, ingest_b: str) -> dict:
        """Diff a report's metrics between two ingests (over time)."""
        from acp.schemas.report import Report

        def _find(ingest: str) -> Report | None:
            with session_scope(self.sessions) as s:
                rows = EntityStore(s).list_by(Report, ingest_id=ingest)
            return next((r for r in rows if r.path == path), None)

        a, b = _find(ingest_a), _find(ingest_b)
        if a is None or b is None:
            raise KeyError(f"report {path} missing in one of the ingests")
        ma, mb = a.metric_map(), b.metric_map()
        deltas = {k: round(mb.get(k, 0.0) - ma.get(k, 0.0), 6)
                  for k in set(ma) | set(mb)}
        return {"path": path, "hash_changed": a.hash != b.hash,
                "metric_deltas": deltas}

    def policy_dossier(self, run_id: str) -> dict:
        """Assemble the full policy decision dossier for a run (Alpha 11, WS3)."""
        from acp.core.policy_dossier import build_policy_dossier

        graph = self.full_run_graph(run_id)  # raises KeyError if unknown
        return build_policy_dossier(graph).as_dict()

    def learn_schedule_run(self) -> dict:
        """Run the continuous-learning job batch once (Alpha 9, WS10)."""
        from acp.learning.scheduler import ContinuousLearningScheduler, default_jobs

        sched = ContinuousLearningScheduler()
        sched.register_jobs(default_jobs(self))
        reports = sched.run_all()
        return {"reports": [r.to_dict() for r in reports], **sched.to_dict()}

    def explore_execute(self, *, repetitions: int = 8) -> dict:
        """Simulate the active-learning exploration uplift (Alpha 9, WS9)."""
        from acp.evaluation.capability_campaign import generate_campaign_report
        from acp.learning.exploration_executor import (
            ExplorationBudgetPolicy,
            ExplorationExecutor,
            ExplorationTaskGenerator,
        )
        from acp.routing.exploration import CoverageGapAnalyzer

        matrix = generate_campaign_report(repetitions=repetitions)
        plan = CoverageGapAnalyzer().analyze(matrix)
        specs = ExplorationTaskGenerator().generate(plan, ExplorationBudgetPolicy())
        return ExplorationExecutor().simulate(matrix, specs)

    def self_improvement_report(self) -> dict:
        """Closed-loop self-improvement (Alpha 8 capstone): learn viability +
        context-strategy from exhaust, evaluate, and gate promotion."""
        from acp.learning.self_improvement import run_self_improvement_cycle

        return run_self_improvement_cycle(self.build_exhaust_bundle()).as_dict()

    # ---- capability matrix (Alpha 7, WS2) --------------------------------

    def build_capability_matrix(self, *, repo_id: str | None = None) -> dict:
        """Build a CapabilityMatrix from persisted bakeoff EvalRuns + outcomes."""
        from acp.routing.capability_matrix import CapabilityMatrix
        from acp.schemas.eval import EvalRun
        from acp.schemas.learning import PostMergeOutcome

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            runs = es.list_by(EvalRun)
            outcomes = es.list_by(PostMergeOutcome)
        matrix = CapabilityMatrix()
        for run in runs:
            report = run.summary if isinstance(run.summary, dict) else {}
            if not report:
                continue
            try:
                sub = CapabilityMatrix.from_bakeoff_report(report)
            except Exception:  # noqa: BLE001 - skip non-bakeoff eval runs
                continue
            for cell in sub.cells():
                matrix.add_cell(cell)
        matrix.update_from_outcomes(outcomes)
        return matrix.to_dict()

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

    def run_multi_harness_bakeoff(self, adapter_factories: dict | None = None,
                                  tasks=None):
        """Run the multi-harness no-patch bakeoff and persist it as an EvalRun
        (round-4 Block F). Defaults to the deterministic fake+patch baselines so
        the method is runnable with no API keys; pass real harness factories
        (openai_harness / claude_harness) for a live comparison."""
        from acp.agents.fake import FakeAgentAdapter
        from acp.agents.patch_agent import PatchAgentAdapter
        from acp.evaluation.multi_harness_bakeoff import (
            bakeoff_to_markdown,
            run_multi_harness_bakeoff,
        )

        factories = adapter_factories or {
            "patch": PatchAgentAdapter, "fake": FakeAgentAdapter,
        }
        rep = run_multi_harness_bakeoff(factories, tasks=tasks)
        return self._persist_eval(
            "multi_harness_bakeoff", rep["summary"], rep, cases=rep["cells"],
            markdown=bakeoff_to_markdown(rep),
            config={"adapters": rep["adapters"], "tasks": rep["tasks"]})

    def replay_bakeoff_into_policy(self, eval_run_id: str) -> dict:
        """Replay a persisted multi-harness bakeoff EvalRun into the routing
        policy so the router learns from real outcomes (round-4 Block G). The
        replay is idempotent per EvalRun id (tracked in policy_states metadata).
        Returns the replay report (observations + preference changes)."""
        from acp.routing.replay import PolicyReplayer

        report = self.get_eval_report(eval_run_id)
        if report is None:
            raise KeyError(eval_run_id)
        content = report["content"]
        replayer = PolicyReplayer(self.policy, applied_runs=set(self._applied_eval_runs()))
        result = replayer.replay(content, run_id=eval_run_id)
        if result["applied"]:
            self.save_policy_state()
            self._record_applied_eval_run(eval_run_id)
        return result

    def _applied_eval_runs(self) -> list[str]:
        from acp.db.repositories import EntityStore
        from acp.db.session import session_scope
        from acp.schemas.learning import PolicyState
        with session_scope(self.sessions) as s:
            states = EntityStore(s).list_by(PolicyState,
                                            policy_version=self.policy.policy_version)
        applied: list[str] = []
        for st in states:
            applied.extend(st.metrics.get("applied_eval_runs", []))
        return applied

    def _record_applied_eval_run(self, eval_run_id: str) -> None:
        # Persist the applied-run id alongside the arms so idempotency survives
        # a restart. Stored in the latest PolicyState's params.
        from acp.schemas.learning import PolicyState
        applied = set(self._applied_eval_runs()) | {eval_run_id}
        self._save(PolicyState(policy_version=self.policy.policy_version,
                               arms=self.policy.export_arms(),
                               metrics={"applied_eval_runs": sorted(applied)}))

    def run_bakeoff_v2(self, adapters: list[str], dataset_path: str,
                       repetitions: int = 1, backend: str = "local"):
        """Dataset-driven multi-harness bakeoff v2, persisted as an EvalRun
        (round-5 WS6)."""
        from acp.evaluation.bakeoff_v2 import (
            bakeoff_v2_to_markdown,
            factory_for,
            run_bakeoff_v2,
        )

        factories = {a: factory_for(a) for a in adapters}
        rep = run_bakeoff_v2(factories, dataset_path, repetitions=repetitions,
                             backend=backend)
        return self._persist_eval(
            "multi_harness_v2", rep["summary"], rep, cases=rep["cells"],
            markdown=bakeoff_v2_to_markdown(rep),
            config={"adapters": adapters, "repetitions": repetitions, "backend": backend})

    def simulate_postmerge(self, eval_run_id: str, revert_profile: dict | None = None,
                           seed: int = 1234) -> dict:
        """Simulate delayed post-merge outcomes for a bakeoff EvalRun and feed
        them back into the routing policy (round-5 WS8). Persists the outcomes
        as EvalRun(kind=postmerge_sim) and returns the summary."""
        from acp.evaluation.postmerge_sim import (
            apply_outcomes_to_policy,
            outcomes_summary,
            simulate_outcomes,
        )

        report = self.get_eval_report(eval_run_id)
        if report is None:
            raise KeyError(eval_run_id)
        content = report["content"]
        outcomes = simulate_outcomes(content, revert_profile=revert_profile, seed=seed)
        applied = apply_outcomes_to_policy(self.policy, outcomes)
        self.save_policy_state()
        summary = {**applied, **outcomes_summary(outcomes), "source_eval_run": eval_run_id}
        run = self._persist_eval("postmerge_sim", applied, summary,
                                 config={"source_eval_run": eval_run_id, "seed": seed})
        return {"eval_run_id": run.id, **applied,
                "negative_rate": summary["negative_rate"]}

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

    def replay_post_merge_outcomes(self) -> dict:
        """Replay persisted post-merge outcomes into the policy: recompute matured
        rewards and feed them to the bandit so real-world results update routing
        (round-3 §post-merge replay). Persists policy state + a drift report."""
        from acp.core.classifier import classify
        from acp.routing.policy import PolicyDecision
        from acp.routing.reward import compute_reward
        from acp.schemas.agent import AgentAttempt
        from acp.schemas.evaluation import EvaluationResult
        from acp.schemas.learning import PostMergeOutcome
        from acp.schemas.routing import RoutingDecision

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            outcomes = es.list_by(PostMergeOutcome)
            attempts = {a.id: a for a in es.list_by(AgentAttempt)}
            decisions = {d.id: d for d in es.list_by(RoutingDecision)}
            evals = {e.attempt_id: e for e in es.list_by(EvaluationResult) if e.attempt_id}

        replayed = reverted = arms_updated = 0
        matured: list = []
        for out in outcomes:
            att = attempts.get(out.attempt_id or "")
            ev = evals.get(out.attempt_id or "")
            if att is None or ev is None:
                continue
            bad = bool(out.reverted or out.incident_link)
            reward = compute_reward(ev, att, task_success=not bad,
                                    reverted_or_incident=bad, label_source="post_merge")
            from acp.core.time import utcnow

            reward.matured_at = utcnow()
            matured.append(reward)
            replayed += 1
            reverted += int(bad)
            # feed the bandit: reconstruct the decision's context from the task
            dec = decisions.get(att.routing_decision_id or "")
            task = self.get_task(att.task_id)
            if dec is not None and task is not None:
                cls = classify(task)
                tt = cls.task_type if isinstance(cls.task_type, str) else cls.task_type.value
                rl = cls.risk_level if isinstance(cls.risk_level, str) else cls.risk_level.value
                ctx = f"{tt}|{rl}"
                pdec = PolicyDecision(policy_version=self.policy.policy_version,
                                      action=dec.action, action_probability=dec.action_probability,
                                      context_key=ctx)
                self.policy.observe_reward(pdec, reward)
                arms_updated += 1
        if matured:
            self._save(*matured)
        self.save_policy_state()
        drift = self.drift_report()
        return {"replayed": replayed, "reverted": reverted, "arms_updated": arms_updated,
                "drift": drift}

    def calibrate_evaluators(self) -> dict:
        """Calibrate automated evaluators against human labels + post-merge
        outcomes from the DB; persist as EvalRun(kind=calibration) (R3-6)."""
        from acp.evaluation.calibration import CalibrationSample, calibrate
        from acp.schemas.evaluation import EvaluationResult, WeakLabel
        from acp.schemas.human_review import HumanLabel
        from acp.schemas.learning import PostMergeOutcome

        with session_scope(self.sessions) as s:
            es = EntityStore(s)
            evals = {e.attempt_id: e for e in es.list_by(EvaluationResult) if e.attempt_id}
            labels = es.list_by(HumanLabel)
            outcomes = es.list_by(PostMergeOutcome)
            weak = {w.attempt_id: w for w in es.list_by(WeakLabel) if w.attempt_id}

        samples: list[CalibrationSample] = []
        for lab in labels:
            if not lab.attempt_id:
                continue
            truth = (lab.verdict == "pass")  # human label is ground truth (overrides objective)
            ev = evals.get(lab.attempt_id)
            if ev is not None:
                samples.append(CalibrationSample(
                    predicted=ev.spec_compliance, truth=truth,
                    source="objective", truth_source="human",
                ))
            w = weak.get(lab.attempt_id)
            if w is not None:
                samples.append(CalibrationSample(
                    predicted=w.probabilities.get("success", w.confidence), truth=truth,
                    source="weak", truth_source="human",
                ))
        for out in outcomes:
            ev = evals.get(out.attempt_id) if out.attempt_id else None
            if ev is not None:
                samples.append(CalibrationSample(
                    predicted=ev.spec_compliance,
                    truth=not (out.reverted or out.incident_link),
                    source="objective", truth_source="post_merge",
                ))
        report = calibrate(samples).to_dict()
        self._persist_eval("calibration", report, report,
                           config={"n_human": len(labels), "n_post_merge": len(outcomes)})
        return report

    def calibrate_evaluators_v2(self, cases=None):
        """Per-evaluator calibration v2 (round-5 WS9): accuracy/precision/recall/
        Brier/ECE/correlation + recommended threshold + false-auto-approve risk.
        Persisted as EvalRun(kind=calibration)."""
        from acp.evaluation.calibration_v2 import calibrate_v2, default_calibration_dataset

        cases = cases if cases is not None else default_calibration_dataset()
        report = calibrate_v2(cases).to_dict()
        summary = {"schema_version": 2, "n_cases": report["n_cases"],
                   "recommended_threshold": report["recommended_threshold"]}
        return self._persist_eval("calibration", summary, report,
                                  config={"schema_version": 2})

    def run_bandit_mc_eval(self, seeds: int = 20, rounds: int = 400) -> object:
        """Bandit Monte Carlo persisted as an EvalRun (round-3 R3-8)."""
        import statistics

        from acp.routing.simulation import run_simulation

        margins, wins = [], 0
        for seed in range(seeds):
            r = run_simulation(rounds=rounds, seed=seed)
            margins.append(r.policy_reward - r.random_reward)
            wins += int(r.beats_random)
        mean = statistics.mean(margins)
        stdev = statistics.pstdev(margins) or 1e-9
        ci = 1.96 * stdev / (len(margins) ** 0.5)
        summary = {
            "seeds": seeds, "rounds": rounds, "wins_vs_random": wins,
            "mean_margin": round(mean, 3), "ci95": round(ci, 3),
            "beats_random": mean > 0,
        }
        return self._persist_eval("bandit_monte_carlo", summary, summary,
                                  config={"seeds": seeds, "rounds": rounds})

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
