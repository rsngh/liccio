"""Durable workflow runner (charter §17).

Executes the task -> context -> route -> attempt -> verify -> evaluate ->
(human) -> reward loop. Nodes are idempotent and recorded in
``state.completed_nodes`` so a run can resume from persisted state. Human review
pauses the run (WAITING_FOR_HUMAN); ``resume`` continues after a label.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from git import Repo

from acp.agents.base import AgentAdapter
from acp.agents.registry import AgentRegistry
from acp.core.classifier import classify
from acp.core.enums import RiskLevel, RunStatus
from acp.evaluation.objective import ObjectiveEvaluator, diff_touches_tests
from acp.orchestration.state import WorkflowState
from acp.routing.heuristic import HeuristicRouter
from acp.routing.reward import compute_reward
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextPack
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.human_review import HumanLabel, HumanReviewItem
from acp.schemas.learning import RewardEvent
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.routing import RoutingDecision
from acp.schemas.task import Task, TaskClassification
from acp.schemas.verification import Evidence, VerificationPlan, VerificationRun
from acp.schemas.workspace import DiffBundle, WorkspacePolicy
from acp.verification.aggregate import AggregateVerdict, EvidenceAggregator
from acp.verification.plan import build_plan
from acp.verification.service import VerificationService
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.local import LocalWorkspaceManager

NODE_ORDER = [
    "ingest_task",
    "classify_task",
    "create_repo_snapshot",
    "compile_context",
    "generate_verification_plan",
    "route_task",
    "launch_agent_attempts",
    "capture_diff",
    "run_verification",
    "aggregate_evidence",
    "evaluate_attempt",
    "maybe_human_review",
    "compute_reward",
    "update_policy",
    "finalize_run",
]


@dataclass
class RunArtifacts:
    """Side outputs of a run, kept for inspection/persistence."""

    task: Task | None = None
    classification: TaskClassification | None = None
    snapshot: RepoSnapshot | None = None
    context_pack: ContextPack | None = None
    plan: VerificationPlan | None = None
    routing_decision: RoutingDecision | None = None
    attempts: list[AgentAttempt] = field(default_factory=list)
    diffs: dict[str, DiffBundle] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    verification_runs: list[VerificationRun] = field(default_factory=list)
    evidence_by_attempt: dict[str, list[Evidence]] = field(default_factory=dict)
    verdicts: dict[str, AggregateVerdict] = field(default_factory=dict)
    evaluation: EvaluationResult | None = None
    review_item: HumanReviewItem | None = None
    reward: RewardEvent | None = None
    policy_decision: object | None = None


class WorkflowRunner:
    def __init__(
        self,
        repo: Repository,
        registry: AgentRegistry,
        workspace_root: Path | str,
        artifact_store=None,
        on_persist=None,
        max_node_attempts: int = 2,
        policy=None,
    ) -> None:
        self.repo = repo
        self.registry = registry
        self.policy = policy  # optional RoutingPolicy (bandit/supervised); else heuristic
        self.workspace_mgr = LocalWorkspaceManager(workspace_root)
        # Contain all verification commands within the workspace root and scrub
        # secrets from their environment (round-1 §3 sandbox hardening).
        self.command_runner = CommandRunner(
            artifact_store=artifact_store,
            allowed_root=self.workspace_mgr.root,
            scrub_secrets=True,
        )
        self.evaluator = ObjectiveEvaluator()
        self.aggregator = EvidenceAggregator()
        self.on_persist = on_persist
        self.max_node_attempts = max_node_attempts
        self.artifacts = RunArtifacts()
        self._tasks: dict[str, Task] = {}

    # ---- public API -------------------------------------------------------

    def submit(self, task: Task) -> Task:
        self._tasks[task.id] = task
        return task

    async def run(self, task: Task) -> WorkflowState:
        self._tasks[task.id] = task
        state = WorkflowState(task_id=task.id, repo_id=self.repo.id)
        state.status = RunStatus.RUNNING
        return await self._drive(state)

    async def resume(
        self, state: WorkflowState, human_label: HumanLabel | None = None
    ) -> WorkflowState:
        if human_label is not None:
            state.scratch["human_label"] = human_label.model_dump(mode="json")
        state.status = RunStatus.RUNNING
        return await self._drive(state)

    def cancel(self, state: WorkflowState) -> WorkflowState:
        state.status = RunStatus.CANCELLED
        self._persist(state)
        return state

    # ---- engine -----------------------------------------------------------

    async def _drive(self, state: WorkflowState) -> WorkflowState:
        start = NODE_ORDER.index(state.current_node) if state.current_node in NODE_ORDER else 0
        for node in NODE_ORDER[start:]:
            if state.status in (RunStatus.FAILED, RunStatus.CANCELLED):
                break
            if node in state.completed_nodes:
                continue
            state.current_node = node
            state.node_attempts[node] = state.node_attempts.get(node, 0) + 1
            try:
                handler = getattr(self, f"_node_{node}")
                paused = await handler(state)
                state.completed_nodes.append(node)
                self._persist(state)
                if paused:
                    return state
            except Exception as exc:  # noqa: BLE001 - record and fail the run
                state.error = f"{node}: {exc}"
                state.status = RunStatus.FAILED
                self._persist(state)
                return state
        if state.status == RunStatus.RUNNING:
            state.status = RunStatus.SUCCEEDED
        self._persist(state)
        return state

    def _persist(self, state: WorkflowState) -> None:
        from acp.core.time import utcnow

        state.updated_at = utcnow()
        if self.on_persist is not None:
            self.on_persist(state, self.artifacts)

    def _task(self, state: WorkflowState) -> Task:
        return self._tasks[state.task_id]

    # ---- nodes ------------------------------------------------------------

    async def _node_ingest_task(self, state: WorkflowState) -> bool:
        self.artifacts.task = self._task(state)
        return False

    async def _node_classify_task(self, state: WorkflowState) -> bool:
        cls = classify(self._task(state))
        self.artifacts.classification = cls
        state.scratch["risk_level"] = cls.risk_level
        return False

    async def _node_create_repo_snapshot(self, state: WorkflowState) -> bool:
        base = Repo(self._repo_path()).head.commit.hexsha
        snap = RepoSnapshot(repo_id=self.repo.id, base_commit=base)
        state.snapshot_id = snap.id
        state.scratch["base_commit"] = base
        self.artifacts.snapshot = snap
        return False

    def _repo_path(self) -> str:
        if not self.repo.local_path:
            raise ValueError(f"repo {self.repo.id} has no local_path")
        return self.repo.local_path

    async def _node_compile_context(self, state: WorkflowState) -> bool:
        from acp.context.compiler import ContextCompiler

        compiler = ContextCompiler(self._repo_path(), self.repo.id, state.snapshot_id or "snap")
        pack = compiler.compile(self._task(state), token_budget=20_000)
        self.artifacts.context_pack = pack
        state.context_pack_id = pack.id
        return False

    async def _node_generate_verification_plan(self, state: WorkflowState) -> bool:
        plan = build_plan(self._task(state), self._repo_path(), self.artifacts.classification)
        self.artifacts.plan = plan
        state.verification_plan_id = plan.id
        return False

    async def _node_route_task(self, state: WorkflowState) -> bool:
        available = await self.registry.available()
        cls = self.artifacts.classification
        # Heuristic gives the action shape (strategy/verification/human flags).
        base = HeuristicRouter(available_agents=available).decide(self._task(state), cls)

        if self.policy is None:
            decision = base
        else:
            from acp.core.enums import RiskLevel
            from acp.routing.constraints import apply_constraints
            from acp.routing.features import RoutingFeatureExtractor

            risk = cls.risk_level if cls else self._task(state).risk_level
            risk = RiskLevel(risk) if isinstance(risk, str) else risk
            # One candidate per available agent, sharing the heuristic action shape.
            candidates = []
            seen = set()
            for name in available:
                adapter = self.registry.get(name)
                cand = base.action.model_copy(
                    update={"agent_kind": adapter.kind, "agent_name": name}
                )
                if cand.key() not in seen:
                    seen.add(cand.key())
                    candidates.append(cand)
            candidates, applied = apply_constraints(
                candidates, risk, set(available),
                max_cost_usd=base.action.max_cost_usd,
            )
            features = RoutingFeatureExtractor().extract(self._task(state), cls)
            pdec = self.policy.choose_action(dict(features), candidates)
            self.artifacts.policy_decision = pdec
            decision = RoutingDecision(
                task_id=state.task_id,
                snapshot_id=state.snapshot_id,
                policy_version=getattr(self.policy, "policy_version", "policy"),
                action=pdec.action,
                action_probability=pdec.action_probability,
                candidate_actions=candidates,
                model_scores=pdec.candidate_scores,
                exploration_mode=pdec.exploration_mode,
                exploration_reason=pdec.exploration_reason,
                constraints_applied=applied,
            )
        self.artifacts.routing_decision = decision
        state.routing_decision_id = decision.id
        return False

    async def _node_launch_agent_attempts(self, state: WorkflowState) -> bool:
        decision = self.artifacts.routing_decision
        assert decision is not None
        assert self.artifacts.snapshot is not None
        assert self.artifacts.context_pack is not None
        agents = self._agents_for(decision)
        snap = self.artifacts.snapshot
        pack = self.artifacts.context_pack
        budget = Budget(
            max_cost_usd=decision.action.max_cost_usd,
            max_wall_time_s=decision.action.max_wall_time_s,
            token_budget=decision.action.context_token_budget,
        )
        for adapter in agents:
            ws = self.workspace_mgr.create(self.repo, snap, WorkspacePolicy())
            attempt = AgentAttempt(
                task_id=state.task_id,
                routing_decision_id=decision.id,
                workspace_id=ws.spec.id,
                agent_kind=adapter.kind,
                agent_name=adapter.name,
                trace_id=state.trace_id,
            )
            result = await adapter.execute(self._task(state), pack, ws, budget)
            attempt.status = result.status
            attempt.estimated_cost_usd = result.estimated_cost_usd
            attempt.input_token_count = result.input_token_count
            attempt.output_token_count = result.output_token_count
            attempt.total_token_count = result.input_token_count + result.output_token_count
            attempt.wall_time_s = result.wall_time_s
            attempt.error = result.error
            self.artifacts.attempts.append(attempt)
            state.attempt_ids.append(attempt.id)
            state.scratch.setdefault("workspaces", {})[attempt.id] = str(ws.path)
        return False

    def _agents_for(self, decision: RoutingDecision) -> list[AgentAdapter]:
        names = [decision.action.agent_name]
        if decision.action.fallback_policy:
            names.append(decision.action.fallback_policy)
        out: list[AgentAdapter] = []
        for n in names:
            try:
                out.append(self.registry.get(n))
            except KeyError:
                continue
        return out

    async def _node_capture_diff(self, state: WorkflowState) -> bool:
        workspaces = state.scratch.get("workspaces", {})
        base = state.scratch["base_commit"]
        for attempt in self.artifacts.attempts:
            ws_path = workspaces.get(attempt.id)
            if not ws_path:
                continue
            from acp.workspaces.diff import DiffCapturer

            bundle = DiffCapturer(ws_path, base).build_bundle(attempt_id=attempt.id)
            self.artifacts.diffs[attempt.id] = bundle
            attempt.diff_bundle_id = bundle.id
        return False

    async def _node_run_verification(self, state: WorkflowState) -> bool:
        plan = self.artifacts.plan
        assert plan is not None
        workspaces = state.scratch.get("workspaces", {})
        svc = VerificationService(self.command_runner)
        per_attempt: dict[str, list[Evidence]] = {}
        for attempt in self.artifacts.attempts:
            ws_path = workspaces.get(attempt.id)
            if not ws_path or attempt.status not in (RunStatus.SUCCEEDED,):
                per_attempt[attempt.id] = []
                continue
            vrun, evidence = svc.run_plan(plan, ws_path, attempt_id=attempt.id)
            per_attempt[attempt.id] = evidence
            self.artifacts.verification_runs.append(vrun)
            self.artifacts.evidence.extend(evidence)
            state.evidence_ids.extend(e.id for e in evidence)
        state.scratch["evidence_by_attempt"] = {
            aid: [e.id for e in evs] for aid, evs in per_attempt.items()
        }
        self.artifacts.evidence_by_attempt = per_attempt
        return False

    async def _node_aggregate_evidence(self, state: WorkflowState) -> bool:
        per_attempt = self.artifacts.evidence_by_attempt
        verdicts = {}
        for attempt in self.artifacts.attempts:
            diff = self.artifacts.diffs.get(attempt.id)
            verdict = self.aggregator.aggregate(
                per_attempt.get(attempt.id, []),
                diff=diff,
                task_type=(self.artifacts.classification.task_type
                           if self.artifacts.classification else None),
                diff_touches_tests=diff_touches_tests(diff),
            )
            verdicts[attempt.id] = verdict
        self.artifacts.verdicts = verdicts
        return False

    async def _node_evaluate_attempt(self, state: WorkflowState) -> bool:
        verdicts = self.artifacts.verdicts
        risk = state.scratch.get("risk_level")
        # Select best attempt: prefer succeeded + passed verification, then reward proxy.
        best = None
        best_score = -1e9
        for attempt in self.artifacts.attempts:
            verdict = verdicts[attempt.id]
            score = (
                (2.0 if attempt.status == RunStatus.SUCCEEDED else 0.0)
                + (1.0 if verdict.passed else 0.0)
                - verdict.review_burden
                - verdict.security_risk
            )
            if score > best_score:
                best_score, best = score, attempt
        assert best is not None
        state.selected_attempt_id = best.id
        verdict = verdicts[best.id]
        evaluation = self.evaluator.evaluate(
            self._task(state), best.id, verdict,
            self.artifacts.diffs.get(best.id),
            evidence_ids=state.scratch.get("evidence_by_attempt", {}).get(best.id, []),
            risk_level=risk,
        )
        self.artifacts.evaluation = evaluation
        state.evaluation_result_id = evaluation.id
        # Persist facts the reward/finalize nodes need so a cross-process resume
        # (rehydrated runner) does not depend on the in-memory verdicts dict.
        state.scratch["selected_passed"] = verdict.passed
        state.scratch["selected_status"] = (
            best.status.value if hasattr(best.status, "value") else best.status
        )
        return False

    async def _node_maybe_human_review(self, state: WorkflowState) -> bool:
        evaluation = self.artifacts.evaluation
        assert evaluation is not None
        selected = next(
            (a for a in self.artifacts.attempts if a.id == state.selected_attempt_id), None
        )
        # A hard agent failure fails fast; human review is for succeeded-but-
        # uncertain/sensitive results.
        if selected is None or selected.status != RunStatus.SUCCEEDED:
            return False
        if not evaluation.requires_human_review:
            return False
        if "human_label" in state.scratch:
            return False  # already labeled -> proceed
        item = HumanReviewItem(
            task_id=state.task_id,
            attempt_id=state.selected_attempt_id,
            run_id=state.run_id,
            reason="; ".join(evaluation.reasons) or "policy requires review",
            priority=1.0,
        )
        self.artifacts.review_item = item
        state.human_review_item_id = item.id
        state.status = RunStatus.WAITING_FOR_HUMAN
        # Roll back so this node re-runs on resume.
        state.completed_nodes = [n for n in state.completed_nodes if n != "maybe_human_review"]
        return True

    async def _node_compute_reward(self, state: WorkflowState) -> bool:
        evaluation = self.artifacts.evaluation
        assert evaluation is not None
        attempt = next(
            (a for a in self.artifacts.attempts if a.id == state.selected_attempt_id), None
        )
        assert attempt is not None
        # Prefer the live verdict; fall back to scratch (cross-process resume).
        verdict = self.artifacts.verdicts.get(attempt.id)
        if verdict is not None:
            passed = verdict.passed and attempt.status == RunStatus.SUCCEEDED
        else:
            passed = bool(state.scratch.get("selected_passed")) and (
                state.scratch.get("selected_status") == RunStatus.SUCCEEDED.value
            )
        human = state.scratch.get("human_label")
        task_success = passed
        if human is not None:
            task_success = human.get("verdict") == "pass"
        reward = compute_reward(
            evaluation, attempt, task_success=task_success,
            label_source="human" if human else "objective",
        )
        self.artifacts.reward = reward
        state.reward_event_id = reward.id
        return False

    async def _node_update_policy(self, state: WorkflowState) -> bool:
        # Feed the reward back to a learnable policy (bandit/supervised).
        pdec = self.artifacts.policy_decision
        reward = self.artifacts.reward
        if self.policy is not None and pdec is not None and reward is not None:
            observe = getattr(self.policy, "observe_reward", None)
            if callable(observe):
                observe(pdec, reward)
                state.scratch["policy_updated"] = True
                return False
        state.scratch["policy_updated"] = bool(self.policy is not None)
        return False

    async def _node_finalize_run(self, state: WorkflowState) -> bool:
        attempt = next(
            (a for a in self.artifacts.attempts if a.id == state.selected_attempt_id), None
        )
        human = state.scratch.get("human_label")
        if human is not None and human.get("verdict") == "fail":
            state.status = RunStatus.FAILED
            state.error = "human rejected"
        elif attempt is None or attempt.status not in (RunStatus.SUCCEEDED,):
            state.status = RunStatus.FAILED
        else:
            state.status = RunStatus.SUCCEEDED
        return False


def run_sync(runner: WorkflowRunner, task: Task) -> WorkflowState:
    return asyncio.run(runner.run(task))


_ = RiskLevel  # referenced for type clarity
