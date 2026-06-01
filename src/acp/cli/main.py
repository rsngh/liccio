"""Main Typer application wiring up all subcommands.

In Phase 0 most subcommands are placeholders that print structured info; later
phases fill in real behavior. The CLI must always import and ``--help`` cleanly
with no optional dependencies installed.
"""

from __future__ import annotations

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
