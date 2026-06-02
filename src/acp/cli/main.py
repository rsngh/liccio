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


def main() -> None:  # pragma: no cover - thin entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
