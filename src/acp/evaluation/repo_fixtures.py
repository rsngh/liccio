"""Realistic repo fixtures (Alpha 11, WS13).

The retrieval / context benchmarks in
:mod:`acp.evaluation.retrieval_benchmark` synthesize *abstract* repos (numbered
modules with planted gold/decoy files). This module is the complementary thing:
small but **shape-realistic** repositories, one per common project archetype, so
end-to-end planning / context / verification flows can be exercised against trees
that look like real projects (a package layout, a test file, a lint/type config,
a planted known-bug marker, plus — where relevant — a security or migration
fixture) instead of numbered noise.

Every fixture also writes a *generated* artifact (e.g. ``__pycache__/`` or
``build/``) and a *decoy* file, so retrieval and ignore logic have something to
correctly skip. Each ``make_*`` writer returns a manifest describing what it
created; :func:`make_all_fixtures` lays down every :data:`FIXTURE_KINDS` kind
under one root. Pure-python, deterministic, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Every fixture archetype this module can lay down.
FIXTURE_KINDS: tuple[str, ...] = (
    "python_package_cli",
    "fastapi_service",
    "react_ts_app",
    "monorepo_shared",
    "db_migration_app",
    "security_auth_app",
    "flaky_ci_repo",
    "legacy_refactor_repo",
)


@dataclass
class RepoFixtureSpec:
    """Manifest describing a laid-down fixture repo.

    Categorizes the written paths (all repo-relative, POSIX style) so a benchmark
    can assert on the planted gold/decoy/generated files without re-walking the
    tree. ``known_bug`` points at the file carrying the planted ``KNOWN-BUG``
    marker, the gold target a fix-the-bug task would aim for.
    """

    kind: str
    root: str
    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    decoy_files: list[str] = field(default_factory=list)
    security_files: list[str] = field(default_factory=list)
    migration_files: list[str] = field(default_factory=list)
    known_bug: str | None = None

    def to_dict(self) -> dict:
        """JSON-serializable view of the manifest."""
        return {
            "kind": self.kind,
            "root": self.root,
            "source_files": self.source_files,
            "test_files": self.test_files,
            "config_files": self.config_files,
            "generated_files": self.generated_files,
            "decoy_files": self.decoy_files,
            "security_files": self.security_files,
            "migration_files": self.migration_files,
            "known_bug": self.known_bug,
        }


# Marker a "fix the planted bug" task targets; cheap, greppable sentinel.
KNOWN_BUG_MARKER = "# KNOWN-BUG: off-by-one in the success path"


def _write(root: Path, rel: str, content: str) -> str:
    """Write ``content`` to ``root/rel`` (creating parents); return ``rel``."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return rel


def _write_bytes(root: Path, rel: str, content: bytes) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return rel


def _make_python_package_cli(root: Path) -> RepoFixtureSpec:
    src = _write(
        root,
        "src/widgetcli/core.py",
        "def add(a, b):\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    return a + b + 1\n",
    )
    cli = _write(
        root,
        "src/widgetcli/__main__.py",
        "from widgetcli.core import add\n\n\n"
        "def main() -> None:\n    print(add(1, 2))\n",
    )
    test = _write(
        root,
        "tests/test_core.py",
        "from widgetcli.core import add\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n",
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[project]\nname = "widgetcli"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\n\n'
        "[tool.ruff]\nline-length = 100\n\n[tool.mypy]\nstrict = true\n",
    )
    gen = _write(root, "src/widgetcli/__pycache__/core.cpython-311.pyc", "x")
    decoy = _write(
        root,
        "scratch/old_core_backup.py",
        "def add(a, b):\n    return a + b  # superseded by src/widgetcli/core.py\n",
    )
    return RepoFixtureSpec(
        kind="python_package_cli",
        root=str(root),
        source_files=[src, cli],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=src,
    )


def _make_fastapi_service(root: Path) -> RepoFixtureSpec:
    app = _write(
        root,
        "app/main.py",
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n\n"
        '@app.get("/health")\ndef health():\n'
        f"    {KNOWN_BUG_MARKER}\n"
        '    return {"status": "ok", "checks": 1}\n',
    )
    routes = _write(
        root,
        "app/routes/items.py",
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n"
        '@router.get("/items/{item_id}")\ndef get_item(item_id: int):\n'
        '    return {"item_id": item_id}\n',
    )
    test = _write(
        root,
        "tests/test_main.py",
        "from fastapi.testclient import TestClient\n\n"
        "from app.main import app\n\n\n"
        "def test_health():\n"
        "    client = TestClient(app)\n"
        '    assert client.get("/health").status_code == 200\n',
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[project]\nname = "svc"\nversion = "0.1.0"\n'
        'dependencies = ["fastapi"]\n\n[tool.ruff]\nline-length = 100\n',
    )
    gen = _write(root, "app/__pycache__/main.cpython-311.pyc", "x")
    decoy = _write(
        root,
        "docs/legacy_api.md",
        "Deprecated /healthz endpoint; see app/main.py:/health instead.\n",
    )
    return RepoFixtureSpec(
        kind="fastapi_service",
        root=str(root),
        source_files=[app, routes],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=app,
    )


def _make_react_ts_app(root: Path) -> RepoFixtureSpec:
    comp = _write(
        root,
        "src/components/Counter.tsx",
        "import React, { useState } from 'react';\n\n"
        "export function Counter() {\n"
        "  const [n, setN] = useState(0);\n"
        f"  {KNOWN_BUG_MARKER.replace('#', '//')}\n"
        "  const inc = () => setN(n + 2);\n"
        "  return <button onClick={inc}>{n}</button>;\n}\n",
    )
    app = _write(
        root,
        "src/App.tsx",
        "import { Counter } from './components/Counter';\n\n"
        "export default function App() {\n  return <Counter />;\n}\n",
    )
    test = _write(
        root,
        "src/components/Counter.test.tsx",
        "import { render } from '@testing-library/react';\n\n"
        "import { Counter } from './Counter';\n\n"
        "test('renders', () => {\n  render(<Counter />);\n});\n",
    )
    cfg = _write(
        root,
        "tsconfig.json",
        '{\n  "compilerOptions": {\n    "strict": true,\n'
        '    "jsx": "react-jsx"\n  }\n}\n',
    )
    eslint = _write(
        root,
        ".eslintrc.json",
        '{\n  "extends": ["react-app"]\n}\n',
    )
    gen = _write(root, "build/static/js/main.abc123.js", "console.log(1);\n")
    decoy = _write(
        root,
        "src/components/Counter.old.tsx",
        "// pre-hooks class version, replaced by Counter.tsx\n",
    )
    return RepoFixtureSpec(
        kind="react_ts_app",
        root=str(root),
        source_files=[comp, app],
        test_files=[test],
        config_files=[cfg, eslint],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=comp,
    )


def _make_monorepo_shared(root: Path) -> RepoFixtureSpec:
    shared = _write(
        root,
        "packages/shared/src/calc.py",
        "def discount(price, pct):\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    return price - price * pct / 10\n",
    )
    consumer = _write(
        root,
        "packages/billing/src/invoice.py",
        "from shared.calc import discount\n\n\n"
        "def total(price):\n    return discount(price, 0.1)\n",
    )
    test = _write(
        root,
        "packages/shared/tests/test_calc.py",
        "from shared.calc import discount\n\n\n"
        "def test_discount():\n    assert discount(100, 0.1) == 90\n",
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[tool.workspace]\nmembers = ["packages/shared", "packages/billing"]\n\n'
        "[tool.ruff]\nline-length = 100\n",
    )
    gen = _write(root, "packages/shared/dist/calc-0.1.0.whl", "x")
    decoy = _write(
        root,
        "packages/legacy/src/calc.py",
        "def discount(price, pct):\n    return price  # unused legacy pkg\n",
    )
    return RepoFixtureSpec(
        kind="monorepo_shared",
        root=str(root),
        source_files=[shared, consumer],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=shared,
    )


def _make_db_migration_app(root: Path) -> RepoFixtureSpec:
    models = _write(
        root,
        "app/models.py",
        "class User:\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    columns = ('id', 'email')\n",
    )
    repo = _write(
        root,
        "app/repository.py",
        "from app.models import User\n\n\n"
        "def emails(users):\n    return [u for u in users]\n",
    )
    migration = _write(
        root,
        "migrations/0001_add_users.sql",
        "-- migration: create users table\n"
        "CREATE TABLE users (\n  id SERIAL PRIMARY KEY,\n"
        "  email TEXT NOT NULL UNIQUE\n);\n",
    )
    migration2 = _write(
        root,
        "migrations/0002_add_created_at.sql",
        "ALTER TABLE users ADD COLUMN created_at TIMESTAMP;\n",
    )
    test = _write(
        root,
        "tests/test_models.py",
        "from app.models import User\n\n\n"
        "def test_columns():\n    assert 'email' in User.columns\n",
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[project]\nname = "dbapp"\nversion = "0.1.0"\n\n'
        "[tool.ruff]\nline-length = 100\n",
    )
    gen = _write(root, "app/__pycache__/models.cpython-311.pyc", "x")
    decoy = _write(
        root,
        "migrations/.archived/0000_initial.sql.bak",
        "-- archived, do not apply\n",
    )
    return RepoFixtureSpec(
        kind="db_migration_app",
        root=str(root),
        source_files=[models, repo],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        migration_files=[migration, migration2],
        known_bug=models,
    )


def _make_security_auth_app(root: Path) -> RepoFixtureSpec:
    auth = _write(
        root,
        "app/auth.py",
        "import hashlib\n\n\n"
        "def hash_password(pw: str) -> str:\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    return hashlib.sha256(pw.encode()).hexdigest()\n\n\n"
        "def verify(pw: str, digest: str) -> bool:\n"
        "    return hash_password(pw) == digest\n",
    )
    handler = _write(
        root,
        "app/login.py",
        "from app.auth import verify\n\n\n"
        "def login(pw, digest):\n    return verify(pw, digest)\n",
    )
    # security fixture: a policy/config the auth flow is checked against, plus a
    # planted-secret file a scanner must flag and retrieval must never surface.
    policy = _write(
        root,
        "security/auth_policy.yaml",
        "password:\n  algorithm: argon2id\n  min_length: 12\n"
        "session:\n  max_age_minutes: 30\n",
    )
    secret = _write(
        root,
        ".env",
        "AUTH_SIGNING_KEY=sk-must-not-leak-auth-000\n",
    )
    test = _write(
        root,
        "tests/test_auth.py",
        "from app.auth import hash_password, verify\n\n\n"
        "def test_roundtrip():\n"
        "    d = hash_password('pw')\n    assert verify('pw', d)\n",
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[project]\nname = "authapp"\nversion = "0.1.0"\n\n'
        "[tool.ruff]\nline-length = 100\n",
    )
    gen = _write(root, "app/__pycache__/auth.cpython-311.pyc", "x")
    decoy = _write(
        root,
        "docs/old_auth_notes.md",
        "Legacy MD5 hashing notes; superseded by app/auth.py.\n",
    )
    return RepoFixtureSpec(
        kind="security_auth_app",
        root=str(root),
        source_files=[auth, handler],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        security_files=[policy, secret],
        known_bug=auth,
    )


def _make_flaky_ci_repo(root: Path) -> RepoFixtureSpec:
    src = _write(
        root,
        "src/jobs/runner.py",
        "import os\n\n\n"
        "def run_job(n):\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    # depends on wall-clock parity -> intermittently fails in CI\n"
        "    return n if os.getpid() % 2 == 0 else n + 1\n",
    )
    test = _write(
        root,
        "tests/test_runner.py",
        "from src.jobs.runner import run_job\n\n\n"
        "def test_run_job():\n    assert run_job(5) == 5\n",
    )
    ci = _write(
        root,
        ".github/workflows/ci.yml",
        "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: pytest -q\n",
    )
    cfg = _write(
        root,
        "pyproject.toml",
        '[project]\nname = "flakyci"\nversion = "0.1.0"\n\n'
        "[tool.ruff]\nline-length = 100\n",
    )
    gen = _write(root, ".pytest_cache/v/cache/lastfailed", "{}\n")
    decoy = _write(
        root,
        "tests/test_runner_quarantined.py.skip",
        "# quarantined flaky test, not collected\n",
    )
    return RepoFixtureSpec(
        kind="flaky_ci_repo",
        root=str(root),
        source_files=[src],
        test_files=[test],
        config_files=[cfg, ci],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=src,
    )


def _make_legacy_refactor_repo(root: Path) -> RepoFixtureSpec:
    legacy = _write(
        root,
        "legacy/orders.py",
        "def process(order):\n"
        f"    {KNOWN_BUG_MARKER}\n"
        "    # 600-line god-function, abbreviated\n"
        "    total = 0\n"
        "    for line in order:\n        total = total + line + 1\n"
        "    return total\n",
    )
    helper = _write(
        root,
        "legacy/util.py",
        "def deprecated_helper(x):\n    return x  # TODO: remove after refactor\n",
    )
    test = _write(
        root,
        "tests/test_orders.py",
        "from legacy.orders import process\n\n\n"
        "def test_process():\n    assert process([1, 2]) == 3\n",
    )
    cfg = _write(
        root,
        "setup.cfg",
        "[flake8]\nmax-line-length = 100\n\n[mypy]\nignore_missing_imports = True\n",
    )
    gen = _write(root, "legacy/__pycache__/orders.cpython-38.pyc", "x")
    decoy = _write(
        root,
        "legacy/orders_v1_backup.py",
        "def process(order):\n    return 0  # ancient copy, do not edit\n",
    )
    return RepoFixtureSpec(
        kind="legacy_refactor_repo",
        root=str(root),
        source_files=[legacy, helper],
        test_files=[test],
        config_files=[cfg],
        generated_files=[gen],
        decoy_files=[decoy],
        known_bug=legacy,
    )


_MAKERS = {
    "python_package_cli": _make_python_package_cli,
    "fastapi_service": _make_fastapi_service,
    "react_ts_app": _make_react_ts_app,
    "monorepo_shared": _make_monorepo_shared,
    "db_migration_app": _make_db_migration_app,
    "security_auth_app": _make_security_auth_app,
    "flaky_ci_repo": _make_flaky_ci_repo,
    "legacy_refactor_repo": _make_legacy_refactor_repo,
}


def make_fixture_repo(kind: str, root: Path) -> dict:
    """Lay down one fixture repo of ``kind`` under ``root``; return its manifest.

    ``root`` is created if missing. Returns the :class:`RepoFixtureSpec` for the
    fixture as a JSON-serializable dict (see :meth:`RepoFixtureSpec.to_dict`).
    Raises ``ValueError`` for an unknown ``kind``.
    """
    if kind not in _MAKERS:
        raise ValueError(f"unknown fixture kind {kind!r}; expected one of {FIXTURE_KINDS}")
    root.mkdir(parents=True, exist_ok=True)
    return _MAKERS[kind](root).to_dict()


def make_all_fixtures(root: Path) -> dict:
    """Lay down every :data:`FIXTURE_KINDS` fixture under ``root/<kind>``.

    Returns a mapping ``kind -> manifest dict`` covering all archetypes, so a
    benchmark can iterate the whole realistic-repo suite from one call.
    Deterministic: the same ``root`` always yields the same trees.
    """
    root.mkdir(parents=True, exist_ok=True)
    return {kind: make_fixture_repo(kind, root / kind) for kind in FIXTURE_KINDS}
