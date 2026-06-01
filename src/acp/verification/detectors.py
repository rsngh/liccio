"""Project / toolchain detectors (charter §14.2).

Inspect a workspace to decide which verification commands apply. Pure filesystem
inspection — no command execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectProfile:
    is_python: bool = False
    is_node: bool = False
    package_managers: list[str] = field(default_factory=list)
    test_command: list[str] | None = None
    lint_command: list[str] | None = None
    typecheck_command: list[str] | None = None
    playwright: bool = False
    docker_compose: bool = False
    has_pytest: bool = False


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def detect(root: Path | str) -> ProjectProfile:
    root = Path(root)
    p = ProjectProfile()
    pyproject = root / "pyproject.toml"
    setup_py = root / "setup.py"
    reqs = root / "requirements.txt"
    pkg = root / "package.json"

    if pyproject.exists() or setup_py.exists() or reqs.exists():
        p.is_python = True
        p.package_managers.append("pip")
        text = _read(pyproject) + _read(reqs)
        if "pytest" in text or (root / "tests").exists() or list(root.glob("test_*.py")):
            p.has_pytest = True
            p.test_command = ["python", "-m", "pytest", "-q"]
        if "ruff" in text:
            p.lint_command = ["ruff", "check", "."]
        if "mypy" in text:
            p.typecheck_command = ["mypy", "."]

    if pkg.exists():
        p.is_node = True
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts", {})
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "test" in scripts:
            p.test_command = p.test_command or ["npm", "test"]
        if "@playwright/test" in deps or "playwright" in deps:
            p.playwright = True
        if "yarn.lock" in {x.name for x in root.iterdir() if x.is_file()}:
            p.package_managers.append("yarn")
        else:
            p.package_managers.append("npm")

    if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
        p.docker_compose = True

    return p
