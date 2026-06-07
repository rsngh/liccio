"""Main Typer application wiring up all subcommands.

In Phase 0 most subcommands are placeholders that print structured info; later
phases fill in real behavior. The CLI must always import and ``--help`` cleanly
with no optional dependencies installed.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from acp.core.config import get_settings
from acp.version import __version__

app = typer.Typer(
    name="acp",
    help="agent-control-plane: route, run, verify, evaluate, and learn from coding agents.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the acp version."""
    console.print(f"acp {__version__}")


@app.command()
def config() -> None:
    """Print effective configuration (secrets redacted)."""
    settings = get_settings()
    console.print_json(data=settings.safe_dict())


@app.command()
def init() -> None:
    """Initialize local acp storage (DB + artifact/workspace dirs)."""
    from acp.api.service import AppService

    svc = AppService()
    svc.settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    svc.settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Initialized acp at db={svc.settings.database_url}")


demo_app = typer.Typer(help="No-API demos.")
app.add_typer(demo_app, name="demo")


@demo_app.command("quickstart")
def demo_quickstart() -> None:
    """Create local DB + fixture repo and run the bugfix loop end-to-end."""
    from acp.api.service import AppService
    from acp.cli.demos import run_bugfix_demo

    svc = AppService()
    result = run_bugfix_demo(svc, svc.settings.workspace_dir)
    console.print_json(data=result)


@demo_app.command("bugfix")
def demo_bugfix() -> None:
    """Run the divide-by-zero bugfix demo with the deterministic patch agent."""
    from acp.api.service import AppService
    from acp.cli.demos import run_bugfix_demo

    svc = AppService()
    result = run_bugfix_demo(svc, svc.settings.workspace_dir)
    console.print_json(data=result)
    console.print(f"[bold green]status: {result['status']}[/bold green]")


@demo_app.command("bandit")
def demo_bandit(rounds: int = 1000, seed: int = 1234) -> None:
    """Run the contextual-bandit simulation and show it beats random."""
    from acp.cli.demos import run_bandit_demo

    result = run_bandit_demo(rounds=rounds, seed=seed)
    console.print_json(data=result)


repo_app = typer.Typer(help="Repository management.")
app.add_typer(repo_app, name="repo")


@repo_app.command("add")
def repo_add(path: str, name: str = "repo", branch: str = "main") -> None:
    """Register a local git repository."""
    from acp.api.service import AppService

    repo = AppService().create_repo(name, path, default_branch=branch)
    console.print(f"repo {repo.id} -> {path}")


@repo_app.command("list")
def repo_list() -> None:
    from acp.api.service import AppService

    for r in AppService().list_repos():
        console.print(f"{r.id}  {r.name}  {r.local_path}")


@repo_app.command("index")
def repo_index(repo_id: str) -> None:
    """Index a registered repo and print a summary."""
    from acp.api.service import AppService
    from acp.context.indexer import RepoIndexer

    svc = AppService()
    repo = svc.get_repo(repo_id)
    if repo is None or not repo.local_path:
        console.print(f"repo {repo_id} not found")
        raise typer.Exit(1)
    idx = RepoIndexer(repo.local_path, repo.id, "snap").index()
    console.print_json(data={
        "files": len(idx.files), "chunks": len(idx.chunks),
        "languages": idx.language_summary, "has_instructions": idx.has_instructions,
    })


task_app = typer.Typer(help="Task management.")
app.add_typer(task_app, name="task")


@task_app.command("create")
def task_create(repo: str, title: str, body: str = "") -> None:
    """Create a task for a repo."""
    from acp.api.service import AppService

    t = AppService().create_task(repo, title, body)
    console.print(f"task {t.id}  type={t.task_type}  risk={t.risk_level}")


run_app = typer.Typer(help="Run management.")
app.add_typer(run_app, name="run")


@run_app.command("start")
def run_start(task_id: str) -> None:
    """Run the workflow for a task."""
    from acp.api.service import AppService

    state = AppService().run_task(task_id)
    console.print_json(data={"run_id": state.run_id, "status": state.status})


@run_app.command("status")
def run_status(run_id: str) -> None:
    """Show a persisted run's status summary."""
    from acp.api.service import AppService

    state = AppService().get_run(run_id)
    if state is None:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1)
    console.print_json(data={"run_id": run_id, "status": state.status,
                             "current_node": state.current_node})


@run_app.command("graph")
def run_graph_cmd(run_id: str, counts: bool = False) -> None:
    """Reconstruct the full run graph from storage (--counts for a summary)."""
    from acp.api.service import AppService

    try:
        graph = AppService().full_run_graph(run_id)
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None
    if counts:
        summary = {k: (len(v) if isinstance(v, list) else (1 if v else 0))
                   for k, v in graph.items()}
        console.print_json(data=summary)
    else:
        console.print_json(data=graph)


@run_app.command("trace")
def run_trace_cmd(run_id: str) -> None:
    """Show a run's trace/node summary."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().run_trace(run_id))
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None


@run_app.command("diff")
def run_diff_cmd(run_id: str) -> None:
    """Show changed files per attempt for a run."""
    from acp.api.service import AppService

    try:
        diffs = AppService().run_diff(run_id)
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None
    for d in diffs:
        console.print(f"{d['attempt_id']}: {d['changed_files']}")


@run_app.command("evidence")
def run_evidence_cmd(run_id: str) -> None:
    """Show verification evidence for a run."""
    from acp.api.service import AppService

    try:
        for e in AppService().run_evidence(run_id):
            console.print(f"{e['kind']}:{e['name']} -> {e['status']} ({e['summary']})")
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None


@run_app.command("evaluation")
def run_evaluation_cmd(run_id: str) -> None:
    """Show the evaluation scorecard for a run."""
    from acp.api.service import AppService

    try:
        ev = AppService().run_evaluation(run_id)
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None
    console.print_json(data=ev or {})


agents_app = typer.Typer(help="Agent adapters.")
app.add_typer(agents_app, name="agents")


@agents_app.command("list")
def agents_list() -> None:
    """List agent adapters with availability + harness classification."""
    from acp.api.service import AppService

    for a in AppService().agents_health():
        flag = "harness" if a["is_harness"] else "model"
        avail = "up" if a["available"] else "down"
        console.print(f"{a['name']:12} {avail:5} {flag:8} {a['detail']}")


@agents_app.command("health")
def agents_health(name: str) -> None:
    """Show one adapter's health."""
    from acp.api.service import AppService

    h = AppService().agent_health(name)
    if h is None:
        console.print(f"agent {name} not found")
        raise typer.Exit(1)
    console.print_json(data=h)


policy_app = typer.Typer(help="Policy management.")
app.add_typer(policy_app, name="policy")


@policy_app.command("list")
def policy_list() -> None:
    from acp.api.service import AppService

    for p in AppService().list_policies():
        console.print(f"{p.id}  {p.name}:{p.version}  status={p.status}")


@policy_app.command("train")
def policy_train() -> None:
    from acp.api.service import AppService

    p = AppService().train_policy()
    console.print(f"trained policy {p.id} ({p.version})")


@policy_app.command("replay-eval")
def policy_replay_eval(eval_run_id: str) -> None:
    """Replay a bakeoff EvalRun into the routing policy (round-5 WS7)."""
    from acp.api.service import AppService

    try:
        result = AppService().replay_bakeoff_into_policy(eval_run_id)
    except KeyError:
        console.print(f"eval run {eval_run_id} not found")
        raise typer.Exit(1) from None
    console.print_json(data=result)


@policy_app.command("evaluate-offline")
def policy_evaluate_offline(target: str = "supervised") -> None:
    """Offline policy evaluation (IPS/SNIPS/DR) of a target policy from logs."""
    from acp.api.service import AppService

    result = AppService().evaluate_policy_offline(target=target)
    console.print_json(data=result)


@policy_app.command("promotion-check")
def policy_promotion_check(target: str = "supervised") -> None:
    """OPE promotion gate: decide whether a target policy is safe to deploy."""
    from acp.api.service import AppService

    result = AppService().policy_promotion_check(target=target)
    console.print_json(data=result)


@policy_app.command("real-log-ope")
def policy_real_log_ope() -> None:
    """Compare candidate policies on the real persisted log (refuses overclaim)."""
    from acp.api.service import AppService

    result = AppService().real_log_ope_report()
    console.print_json(data=result)


@policy_app.command("dossier")
def policy_dossier(run_id: str) -> None:
    """Full policy decision dossier for a run (why this agent/context/cost/risk)."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().policy_dossier(run_id))
    except KeyError:
        console.print(f"run {run_id} not found")
        raise typer.Exit(1) from None


reports_app = typer.Typer(help="Artifact truth infrastructure (Alpha 8).")
app.add_typer(reports_app, name="reports")


@reports_app.command("claim-check")
def reports_claim_check(write: bool = True) -> None:
    """Verify every headline claim maps to fresh, uncontaminated evidence (Alpha 43 P13)."""
    import json as _json

    from acp.reports import check_all

    result = check_all(".")
    if write:
        out_p = Path("reports/claim_evidence_map.json")
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(_json.dumps(result, indent=2) + "\n")
    console.print_json(data=result)
    if not result["all_supported"]:
        raise typer.Exit(1)


@reports_app.command("manifest")
def reports_manifest(out: str = "evals/reports/artifact_manifest.json") -> None:
    """Build + write the artifact manifest over all committed reports."""
    import json as _json
    from pathlib import Path as _Path

    from acp.core.time import isoformat, utcnow
    from acp.observability.artifact_manifest import build_manifest

    manifest = build_manifest(_Path("."), generated_at=isoformat(utcnow()))
    _Path(out).parent.mkdir(parents=True, exist_ok=True)
    _Path(out).write_text(_json.dumps(manifest.as_dict(), indent=2) + "\n")
    console.print_json(data={"n_valid": manifest.as_dict()["n_valid"],
                             "n_total": manifest.as_dict()["n_total"]})


@reports_app.command("ingest")
def reports_ingest() -> None:
    """Snapshot all manifest reports into queryable Report entities."""
    from acp.api.service import AppService

    console.print_json(data=AppService().ingest_reports())


@reports_app.command("list")
def reports_list(ingest_id: str = "") -> None:
    """List ingested reports (optionally for one ingest)."""
    from acp.api.service import AppService

    console.print_json(data=AppService().list_reports(ingest_id or None))


@reports_app.command("show")
def reports_show(report_id: str) -> None:
    """Show one ingested report (hash, metrics, lineage)."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().show_report(report_id))
    except KeyError:
        console.print(f"report {report_id} not found")
        raise typer.Exit(1) from None


@reports_app.command("diff")
def reports_diff(path: str, ingest_a: str, ingest_b: str) -> None:
    """Diff a report's metrics between two ingests."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().diff_reports(path, ingest_a, ingest_b))
    except KeyError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None


@reports_app.command("sync-status")
def reports_sync_status(strict: bool = False) -> None:
    """Sync ALL canonical counts in CURRENT_STATUS.md to the release-truth manifest (Alpha 25).

    The single source of truth is computed from the authoritative sources (source-file
    count, artifact manifest, committed pytest report). This rewrites the test/source/
    artifact figures in CURRENT_STATUS so no count mismatch can survive CI. With
    ``--strict`` it does NOT rewrite; it fails (exit 1) if the document already disagrees —
    use it as the report-truth hard gate.
    """
    from pathlib import Path as _Path

    from acp.observability.release_truth import (
        check_status_consistency,
        gather_truth,
        sync_status_text,
    )

    status = _Path("CURRENT_STATUS.md")
    if not status.exists():
        console.print("[red]missing CURRENT_STATUS.md[/red]")
        raise typer.Exit(1)
    truth = gather_truth(".")
    text = status.read_text()
    if strict:
        problems = check_status_consistency(text, truth)
        if problems:
            console.print_json(data={"consistent": False, "problems": problems,
                                     "truth": truth.to_dict()})
            raise typer.Exit(1)
        console.print_json(data={"consistent": True, "truth": truth.to_dict()})
        return
    status.write_text(sync_status_text(text, truth))
    console.print_json(data={"synced": True, **truth.to_dict()})


@reports_app.command("validate")
def reports_validate() -> None:
    """Fail (exit 1) if any referenced report is missing/malformed/inconsistent."""
    from pathlib import Path as _Path

    from acp.core.time import isoformat, utcnow
    from acp.observability.artifact_manifest import build_manifest

    manifest = build_manifest(_Path("."), generated_at=isoformat(utcnow()))
    if not manifest.all_valid():
        for a in manifest.invalid():
            console.print(f"[red]INVALID[/red] {a.path}: {a.errors}")
        raise typer.Exit(1)
    console.print(f"[green]all {len(manifest.artifacts)} artifacts valid[/green]")


shadow_app = typer.Typer(help="Shadow/guarded decision inbox (Alpha 34 operator surface).")
app.add_typer(shadow_app, name="shadow")


@shadow_app.command("inbox")
def shadow_inbox() -> None:
    """Operator inbox: shadow-decision counts, acceptance rate, zero-write audit."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.orchestration.shadow_store import inbox_summary
    from acp.schemas.shadow_decision import ShadowDecisionRecord

    svc = AppService()
    with session_scope(svc.sessions) as s:
        rows = EntityStore(s).list_by(ShadowDecisionRecord)
        console.print_json(data=inbox_summary(rows))


@shadow_app.command("show")
def shadow_show(decision_id: str) -> None:
    """Show one shadow decision (recommendation + policy dossier + verdict)."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.schemas.shadow_decision import ShadowDecisionRecord

    svc = AppService()
    with session_scope(svc.sessions) as s:
        rec = EntityStore(s).get(ShadowDecisionRecord, decision_id)
    if rec is None:
        console.print(f"[yellow]no decision {decision_id}[/]")
        raise typer.Exit(1)
    console.print_json(data=rec.model_dump(mode="json"))


@shadow_app.command("label")
def shadow_label(decision_id: str, decision: str = "accept", choice: str = "",
                 outcome: str = "") -> None:
    """Label a decision accept|reject|override (override needs --choice); becomes training data."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.orchestration.shadow_store import record_human_feedback

    verdict = {"accept": "accepted", "reject": "rejected",
               "override": "overridden"}.get(decision, decision)
    svc = AppService()
    with session_scope(svc.sessions) as s:
        rec = record_human_feedback(EntityStore(s), decision_id, verdict=verdict,
                                    human_choice=choice or None, observed_outcome=outcome or None)
    if rec is None:
        console.print(f"[yellow]no decision {decision_id}[/]")
        raise typer.Exit(1)
    console.print_json(data={"labeled": decision_id, "verdict": verdict,
                             "human_choice": rec.human_choice})


skill_app = typer.Typer(help="Skill registry + SkillOpt optimization (Alpha 15).")
app.add_typer(skill_app, name="skill")


@skill_app.command("list")
def skill_list(status: str = "") -> None:
    """List skill documents (optionally by status)."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.training.skill_registry import list_skills

    svc = AppService()
    with session_scope(svc.sessions) as s:
        skills = list_skills(EntityStore(s), status=status or None)
        rows = [{"id": k.id, "name": k.name, "version": k.version,
                 "status": k.status, "scope": k.scope.key(),
                 "held_out_score": k.held_out_score, "tokens": k.token_estimate}
                for k in skills]
    console.print_json(data={"skills": rows, "n": len(rows)})


@skill_app.command("show")
def skill_show(skill_id: str) -> None:
    """Show a skill document's content + provenance."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.training.skill_registry import get_skill

    svc = AppService()
    with session_scope(svc.sessions) as s:
        skill = get_skill(EntityStore(s), skill_id)
    if skill is None:
        console.print(f"[red]no skill {skill_id}[/red]")
        raise typer.Exit(1)
    console.print_json(data=skill.model_dump(mode="json"))


@skill_app.command("dashboard")
def skill_dashboard_cmd() -> None:
    """Unified skill self-improvement dashboard: active skills + evolution timeline."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.training.skill_improvement import skill_dashboard

    svc = AppService()
    with session_scope(svc.sessions) as s:
        console.print_json(data=skill_dashboard(EntityStore(s)))


@skill_app.command("overview")
def skill_overview_cmd() -> None:
    """Self-improvement overview: active skills, learned models, and the prioritized
    next optimization targets across known task types."""
    from acp.api.service import AppService
    from acp.core.enums import TaskType
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.schemas.skill import SkillScope
    from acp.training.skill_overview import self_improvement_overview

    svc = AppService()
    scopes = [SkillScope(task_type=t.value).key() for t in TaskType if t != TaskType.UNKNOWN]
    learned: dict = {}
    try:
        learned = svc.self_improvement_report().get("promotions", {})
    except Exception:  # noqa: BLE001 - overview must not crash on thin logs
        learned = {}
    with session_scope(svc.sessions) as s:
        ov = self_improvement_overview(EntityStore(s), candidate_scopes=scopes,
                                       learned_models={"promotions": learned})
    console.print_json(data=ov)


@skill_app.command("optimize")
def skill_optimize(backend: str = "microsoft_skillopt", dry_run: bool = False) -> None:
    """Launch (or dry-run) a SkillOpt optimization. --dry-run reports backend
    availability + plan without running rollouts (WS3 acceptance)."""
    from acp.training.skillopt_backend import (
        ACPInternalSkillOptBackend,
        MicrosoftSkillOptBackend,
        get_backend,
    )

    ms = MicrosoftSkillOptBackend()
    resolved = get_backend(backend)
    status = {
        "requested_backend": backend,
        "microsoft_skillopt_available": ms.available(),
        "resolved_backend": resolved.name,
        "internal_backend_available": ACPInternalSkillOptBackend().available(),
        "dry_run": dry_run,
    }
    if dry_run:
        status["plan"] = (
            "build trusted dataset from conclusive traces -> propose bounded edits -> "
            "apply -> score on held-out rollouts -> gate -> deploy best if it improves")
        if backend.startswith("microsoft") and not ms.available():
            status["note"] = ("skillopt not installed; would fall back to acp_internal. "
                              "Install with `pip install skillopt`.")
        console.print_json(data=status)
        return
    status["note"] = ("live optimization runs via evals/scripts/run_skillopt_live.py "
                      "(needs OPENAI_API_KEY + bounded spend)")
    console.print_json(data=status)


@skill_app.command("diff")
def skill_diff(old_id: str, new_id: str) -> None:
    """Unified diff between two skill versions."""
    from acp.api.service import AppService
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.training.skill_registry import diff_skills, get_skill

    svc = AppService()
    with session_scope(svc.sessions) as s:
        es = EntityStore(s)
        old, new = get_skill(es, old_id), get_skill(es, new_id)
    if old is None or new is None:
        console.print("[red]unknown skill id[/red]")
        raise typer.Exit(1)
    console.print(diff_skills(old, new) or "(no content change)")


measure_app = typer.Typer(help="Measurement-trust layer (Round 12).")
app.add_typer(measure_app, name="measurement")


@measure_app.command("hygiene")
def measurement_hygiene(
    path: str = "reports/live/alpha11_live_bakeoff.json",
    harness_only: bool = True,
) -> None:
    """Classify a bakeoff/cells JSON file and print its measurement-hygiene report.

    Exits 1 if the measurement is contaminated (too much infra/inconclusive noise to
    trust the solve-rate) — a guard you can wire into CI before trusting routing.
    """
    import json as _json
    from pathlib import Path as _Path

    from acp.evaluation.measurement_hygiene import build_hygiene_report

    doc = _json.loads(_Path(path).read_text())
    cells = doc.get("cells", doc) if isinstance(doc, dict) else doc
    if harness_only:
        cells = [c for c in cells if c.get("is_harness")]
    rep = build_hygiene_report(cells)
    console.print_json(data=rep.model_dump(mode="json"))
    if rep.contaminated:
        raise typer.Exit(1)


dataset_app = typer.Typer(help="Training-data factory (Alpha 7).")
app.add_typer(dataset_app, name="dataset")


@dataset_app.command("build")
def dataset_build(kind: str, out: str = "") -> None:
    """Build a redacted, leakage-audited training dataset of --kind from exhaust."""
    from acp.api.service import AppService

    result = AppService().build_training_dataset(kind, out=out or None)
    console.print_json(data=result)


train_app = typer.Typer(help="Fine-tuning candidate analysis (Alpha 7).")
app.add_typer(train_app, name="train")


@train_app.command("candidate-report")
def train_candidate_report() -> None:
    """Report whether the run-exhaust corpus justifies a fine-tune."""
    from acp.api.service import AppService

    console.print_json(data=AppService().training_candidate_report())


@train_app.command("local-lora")
def train_local_lora(kind: str = "viability", dataset: str = "", smoke: bool = True) -> None:
    """Gated local LoRA smoke fine-tune (skips cleanly if training deps absent)."""
    from acp.training.local_lora import LocalLoRAConfig, run_local_lora

    cfg = LocalLoRAConfig(kind=kind, smoke=smoke)
    console.print_json(data=run_local_lora(cfg, dataset))


@app.command("health")
def health_snapshot(mode: str = "lab") -> None:
    """Control-plane health snapshot. --mode production exits nonzero unless the
    production release gates are satisfied."""
    from acp.api.service import AppService

    health = AppService().control_plane_health(mode=mode)
    console.print_json(data=health)
    if mode == "production" and not health.get("production_ready"):
        raise typer.Exit(1)


@app.command("evidence-gaps")
def evidence_gaps(mode: str = "production", budget: int = 0) -> None:
    """What evidence is missing + what ACP should test next (Alpha 32).

    Reads the control-plane health snapshot, reports prioritized evidence gaps, and a
    de-duplicated experiment plan. ``--budget N`` caps the plan to the top N experiments.
    """
    from acp.api.service import AppService
    from acp.observability.evidence_gap import analyze_evidence_gaps, plan_experiments

    health = AppService().control_plane_health(mode=mode)
    gaps = analyze_evidence_gaps(health)
    plan = plan_experiments(health, budget=(budget or None))
    console.print_json(data={"gaps": [g.to_dict() for g in gaps], **plan.to_dict()})


@train_app.command("schedule-run")
def train_schedule_run() -> None:
    """Run the continuous-learning job batch once (idempotent, fault-tolerant)."""
    from acp.api.service import AppService

    console.print_json(data=AppService().learn_schedule_run())


@train_app.command("explore-execute")
def train_explore_execute(repetitions: int = 8) -> None:
    """Simulate active-learning exploration uplift over capability-matrix gaps."""
    from acp.api.service import AppService

    console.print_json(data=AppService().explore_execute(repetitions=repetitions))


@train_app.command("self-improve")
def train_self_improve() -> None:
    """Closed-loop self-improvement: learn viability + context strategy from
    exhaust, evaluate, and gate promotion (capstone)."""
    from acp.api.service import AppService

    console.print_json(data=AppService().self_improvement_report())


@train_app.command("observability-health")
def train_observability_health() -> None:
    """Honest availability of optional observability exporters."""
    from acp.observability.export import optional_exporter_health

    console.print_json(data=optional_exporter_health())


viability_app = typer.Typer(help="Capability matrix / routing viability (Alpha 7).")
app.add_typer(viability_app, name="viability")


@viability_app.command("decision-card")
def viability_decision_card(task_id: str) -> None:
    """Explainable decision card for a task (viability + recommendation + why)."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().decision_card(task_id))
    except KeyError:
        console.print(f"task {task_id} not found")
        raise typer.Exit(1) from None


@viability_app.command("matrix")
def viability_matrix(repo: str = "") -> None:
    """Empirical capability matrix per routing tuple."""
    from acp.api.service import AppService

    console.print_json(data=AppService().build_capability_matrix(repo_id=repo or None))


reviews_app = typer.Typer(help="Human review queue.")
app.add_typer(reviews_app, name="reviews")


@reviews_app.command("list")
def reviews_list() -> None:
    """List open human-review items."""
    from acp.api.service import AppService

    svc = AppService()
    items = svc.list_reviews()
    for i in items:
        console.print(f"{i.id}  task={i.task_id}  reason={i.reason}")
    if not items:
        console.print("no open reviews")


@reviews_app.command("show")
def reviews_show(review_id: str) -> None:
    """Show a review item."""
    from acp.api.service import AppService

    item = AppService().get_review(review_id)
    if item is None:
        console.print(f"review {review_id} not found")
        raise typer.Exit(1)
    console.print_json(data=item.model_dump(mode="json"))


@reviews_app.command("bundle")
def reviews_bundle(review_id: str) -> None:
    """Full adjudication bundle (trace/diff/evidence/weak-label/judge disagreement)."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().review_bundle(review_id))
    except KeyError:
        console.print(f"review {review_id} not found")
        raise typer.Exit(1) from None


@reviews_app.command("make-eval-case")
def reviews_make_eval_case(review_id: str) -> None:
    """Convert a labeled review into a reusable eval/training case."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().make_eval_case(review_id))
    except (KeyError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None


@reviews_app.command("make-training-example")
def reviews_make_training_example(review_id: str) -> None:
    """Convert a labeled review into a redacted training example."""
    from acp.api.service import AppService

    try:
        console.print_json(data=AppService().make_training_example(review_id))
    except (KeyError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None


@reviews_app.command("label")
def reviews_label(
    review_id: str,
    verdict: str = "pass",
    score: float = 0.8,
    reason: str = "",
) -> None:
    """Label a review (pass|fail) — resumes the paused run."""
    from acp.api.service import AppService
    from acp.schemas.human_review import HumanLabel

    svc = AppService()
    item = svc.get_review(review_id)
    if item is None:
        console.print(f"review {review_id} not found")
        raise typer.Exit(1)
    label = HumanLabel(review_item_id=review_id, task_id=item.task_id,
                       attempt_id=item.attempt_id, verdict=verdict, score=score, reason=reason)
    svc.label_review(review_id, label)
    console.print(f"labeled {review_id} verdict={verdict}; run resumed")


eval_app = typer.Typer(help="Evaluation harnesses.")
app.add_typer(eval_app, name="eval")


@eval_app.command("context-benchmark")
def eval_context_benchmark(files: int = 100) -> None:
    """Run + persist the context retrieval benchmark."""
    from acp.api.service import AppService

    run = AppService().run_context_benchmark(files)
    console.print_json(data={"eval_run_id": run.id, **run.summary})


@eval_app.command("context-strategy-benchmark")
def eval_context_strategy_benchmark() -> None:
    """Sweep retrieval strategies across repos; report best strategy per repo."""
    from acp.evaluation.context_strategy_benchmark import run_context_strategy_benchmark

    report = run_context_strategy_benchmark()
    console.print_json(data=report.to_dict())


@eval_app.command("context-downstream-benchmark")
def eval_context_downstream_benchmark() -> None:
    """Score context strategies by DOWNSTREAM task success, not just recall."""
    from acp.evaluation.context_downstream_benchmark import (
        run_context_downstream_benchmark,
    )

    report = run_context_downstream_benchmark()
    console.print_json(data=report.to_dict())


@eval_app.command("evaluator-trust")
def eval_evaluator_trust() -> None:
    """Train the evaluator trust model; recommend risk-specific review thresholds."""
    from acp.evaluation.evaluator_trust import default_trust_dataset, evaluate_trust

    console.print_json(data=evaluate_trust(default_trust_dataset()))


@eval_app.command("repair-classifier")
def eval_repair_classifier() -> None:
    """Evaluate the repair-strategy classifier on the synthetic dataset."""
    from acp.evaluation.repair_classifier import (
        default_repair_dataset,
        evaluate_repair_classifier,
    )

    console.print_json(data=evaluate_repair_classifier(default_repair_dataset()))


@eval_app.command("capability-campaign")
def eval_capability_campaign(repetitions: int = 6) -> None:
    """Populate the capability matrix from a synthetic bakeoff campaign."""
    from acp.evaluation.capability_campaign import (
        campaign_summary,
        generate_campaign_report,
    )

    matrix = generate_campaign_report(repetitions=repetitions)
    console.print_json(data=campaign_summary(matrix))


@eval_app.command("scale-benchmark")
def eval_scale_benchmark() -> None:
    """Storage & scale benchmark: seed synthetic DBs at sizes N, time core ops."""
    from acp.evaluation.scale_benchmark import run_scale_benchmark

    console.print_json(data=run_scale_benchmark(sizes=[50, 100, 200]))


@eval_app.command("security-benchmark")
def eval_security_benchmark() -> None:
    """Security & prompt-injection benchmark across adapters."""
    from acp.evaluation.security_benchmark import run_security_benchmark

    console.print_json(data=run_security_benchmark())


@eval_app.command("docker-security-live")
def eval_docker_security_live() -> None:
    """Run enforceable Docker sandbox security checks (skips without Docker)."""
    from acp.evaluation.docker_security_live import run_docker_security_live

    console.print_json(data=run_docker_security_live())


@eval_app.command("vendor-harness-live")
def eval_vendor_harness_live() -> None:
    """Run the vendor-native harness live gate (codex/claude/openhands).

    Detects each installed vendor harness and runs a tiny no-patch repo task on the
    ones that drive headlessly; unavailable harnesses are skipped, not failed.
    """
    from acp.evaluation.vendor_harness_live import run_vendor_harness_live

    console.print_json(data=run_vendor_harness_live())


@eval_app.command("benchmark-baseline")
def eval_benchmark_baseline(harness: str = "claude_code", timeout_s: int = 180,
                            reps: int = 1) -> None:
    """Run the graded bugfix benchmark live (capability by difficulty, no skill).

    Drives the named vendor harness over the easy/medium/hard suite and prints the
    honest solve rate overall and per difficulty (conclusive attempts only).
    """
    import shutil

    from acp.agents.vendor_native import VENDOR_SPECS, VendorNativeHarness
    from acp.evaluation.benchmark_runner import run_benchmark

    spec = VENDOR_SPECS.get(harness)
    if spec is None or shutil.which(spec.binary) is None:
        console.print(f"[yellow]skip[/]: {harness} not available")
        return
    result = run_benchmark(VendorNativeHarness(harness), timeout_s=timeout_s, reps=reps)
    console.print_json(data=result.to_dict())


@eval_app.command("security-benchmark-v2")
def eval_security_benchmark_v2() -> None:
    """Expanded security & prompt-injection benchmark (10 attack classes)."""
    from acp.evaluation.security_benchmark_v2 import run_security_benchmark_v2

    console.print_json(data=run_security_benchmark_v2())


@eval_app.command("large-corpus")
def eval_large_corpus(repetitions: int = 8) -> None:
    """Generate the large empirical bakeoff corpus + coverage report."""
    from acp.evaluation.large_corpus import generate_large_corpus

    console.print_json(data=generate_large_corpus(repetitions=repetitions))


@eval_app.command("scale-benchmark-v2")
def eval_scale_benchmark_v2() -> None:
    """v2 storage/perf scaling sweep (more measured operations)."""
    from acp.evaluation.scale_benchmark_v2 import run_scale_benchmark_v2

    console.print_json(data=run_scale_benchmark_v2(sizes=[50, 100, 200]))


@eval_app.command("data-governance-redteam")
def eval_data_governance_redteam() -> None:
    """Red-team the data/model governance policies (attacks must be blocked)."""
    from acp.evaluation.data_governance_redteam import run_data_governance_redteam

    console.print_json(data=run_data_governance_redteam())


@eval_app.command("preference-reward-gate")
def eval_preference_reward_gate() -> None:
    """Preference-reward governance gate over the synthetic governance dataset."""
    from acp.learning.reviewer_reliability import (
        default_governance_dataset,
        evaluate_preference_reward_governance,
    )

    labels, features, truth = default_governance_dataset()
    console.print_json(data=evaluate_preference_reward_governance(
        labels, features, truth_by_attempt=truth, post_merge_correlation=0.5))


@eval_app.command("mixed-corpus")
def eval_mixed_corpus(scale: str = "test") -> None:
    """Generate the larger mixed empirical corpus."""
    from acp.evaluation.mixed_corpus import generate_mixed_corpus

    console.print_json(data=generate_mixed_corpus(scale=scale))


@eval_app.command("harness-metrics")
def eval_harness_metrics() -> None:
    """Harness activation/adherence/benefit metrics (HAR/HFR/PWL)."""
    from acp.evaluation.harness_metrics import (
        default_harness_metrics_dataset,
        harness_benefit_metrics,
    )

    data = default_harness_metrics_dataset()
    traces = [t for t, _ in data]
    solved = {t.attempt_id: s for t, s in data}
    console.print_json(data=harness_benefit_metrics(traces, solved).model_dump(mode="json"))


@eval_app.command("trajectory-judge")
def eval_trajectory_judge() -> None:
    """Relative trajectory judge over the default synthetic pair."""
    from acp.evaluation.trajectory_judge import (
        RelativeTrajectoryJudge,
        default_pair_context,
        default_trajectory_pair,
    )

    a, b = default_trajectory_pair()
    ca, cb = default_pair_context()
    judge = RelativeTrajectoryJudge()
    cmp = judge.compare(a, b, solved_a=ca.solved, solved_b=cb.solved,
                        diff_a=ca.diff, diff_b=cb.diff)
    console.print_json(data={
        "comparison": cmp.model_dump(mode="json"),
        "audit": judge.cross_judge_audit(cmp).model_dump(mode="json")})


@eval_app.command("list")
def eval_list() -> None:
    """List persisted eval runs."""
    from acp.api.service import AppService

    for r in AppService().list_eval_runs():
        console.print(f"{r['id']}  {r['kind']:18} {r['status']}")


@eval_app.command("show")
def eval_show(eval_run_id: str) -> None:
    """Show a persisted eval run + summary."""
    from acp.api.service import AppService

    r = AppService().get_eval_run(eval_run_id)
    if r is None:
        console.print(f"eval run {eval_run_id} not found")
        raise typer.Exit(1)
    console.print_json(data={"id": r["id"], "kind": r["kind"], "summary": r["summary"]})


@eval_app.command("bakeoff")
def eval_bakeoff(seeds: int = 2) -> None:
    """Run the bakeoff matrix and print the summary."""
    import tempfile

    from acp.api.service import AppService
    from acp.cli.demos import make_demo_repo
    from acp.core.config import ACPSettings
    from acp.evaluation.bakeoff import BakeoffConfig, run_bakeoff

    tmp = Path(tempfile.mkdtemp())
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'b.db'}",
        artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
    ))
    repo = svc.create_repo("bakeoff", make_demo_repo(tmp / "repo"), default_branch="master")
    rep = run_bakeoff(svc, repo.id, BakeoffConfig(seeds=list(range(1, seeds + 1))))
    console.print_json(data=rep["summary"])


@eval_app.command("multi-harness-bakeoff")
def eval_multi_harness_bakeoff(
    dataset: str = "evals/datasets/no_patch_tasks.yaml",
    adapters: str = "patch,fake",
    repetitions: int = 1,
    backend: str = "local",
    out: str = "",
) -> None:
    """Dataset-driven multi-harness no-patch bakeoff v2 (round-5 WS6).

    Adapters: comma-separated (openai_harness,claude_harness,patch,fake).
    """
    import json

    from acp.api.service import AppService

    names = [a.strip() for a in adapters.split(",") if a.strip()]
    svc = AppService()
    run = svc.run_bakeoff_v2(names, dataset, repetitions=repetitions, backend=backend)
    stored = svc.get_eval_report(run.id)
    assert stored is not None
    report = stored["content"]
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=2))
    console.print_json(data={"eval_run_id": run.id, "summary": report["summary"],
                             "by_adapter": report["by_adapter"]})


@eval_app.command("simulate-postmerge")
def eval_simulate_postmerge(eval_run: str, seed: int = 1234) -> None:
    """Simulate delayed post-merge outcomes for a bakeoff and update the policy."""
    from acp.api.service import AppService

    try:
        result = AppService().simulate_postmerge(eval_run, seed=seed)
    except KeyError:
        console.print(f"eval run {eval_run} not found")
        raise typer.Exit(1) from None
    console.print_json(data=result)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:  # pragma: no cover
    """Run the FastAPI app with uvicorn."""
    import uvicorn

    from acp.api.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.callback()
def _root(
    ctx: typer.Context,
) -> None:
    """agent-control-plane CLI."""
    # Placeholder for global options (e.g. --config, --verbose) added later.
    ctx.ensure_object(dict)


# --- Alpha 42: MetaRouter Arena + FinOps + context-strategy OPE command surface ----------
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_script(rel: str, *args: str) -> None:
    import subprocess
    import sys

    code = subprocess.run([sys.executable, str(_REPO_ROOT / rel), *args],
                          cwd=str(_REPO_ROOT)).returncode
    if code != 0:
        raise typer.Exit(code)


def _show_json(rel: str, hint: str) -> None:
    import json

    p = _REPO_ROOT / rel
    if not p.exists():
        console.print(hint)
        raise typer.Exit(1)
    console.print_json(data=json.loads(p.read_text()))


arena_app = typer.Typer(help="MetaRouter Arena — evidence-driven policy comparison (Alpha 42).")
app.add_typer(arena_app, name="arena")


@arena_app.command("run")
def arena_run(full: bool = False) -> None:
    """Run the arena across policies (live Claude where available); writes reports."""
    _run_script("evals/metarouter_arena/run_arena.py", *(["--full"] if full else []))


@arena_app.command("compare")
def arena_compare() -> None:
    """Show the latest arena policy ranking (verified success per dollar)."""
    _show_json("reports/metarouter_policy_compare.json", "run `acp arena run` first")


finops_app = typer.Typer(help="Meta-agent FinOps — cost per verified success (Alpha 42).")
app.add_typer(finops_app, name="finops")


@finops_app.command("report")
def finops_report_cmd() -> None:
    """Build + show the FinOps report (cost attribution + Pareto promotion) from the arena."""
    _run_script("evals/scripts/build_finops_report.py")
    _show_json("reports/finops_cost_per_verified_success.json", "no finops report")


context_app = typer.Typer(help="Context-strategy routing/OPE (Alpha 42).")
app.add_typer(context_app, name="context")


@context_app.command("strategy-ope")
def context_strategy_ope_cmd() -> None:
    """Build + show the context-strategy OPE (which strategy to route per context need)."""
    _run_script("evals/scripts/build_context_strategy_ope.py")
    _show_json("reports/context_strategy_ope.json", "no context-strategy OPE report")


@context_app.command("topology-search")
def context_topology_search_cmd() -> None:
    """Build + show the offline topology-controller search over arena traces."""
    _run_script("evals/scripts/build_topology_controller_search.py")
    _show_json("reports/topology_controller_search.json", "no topology search report")


def main() -> None:  # pragma: no cover - thin entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
