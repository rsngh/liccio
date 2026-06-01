"""Fixture-repo generators for the no-patch benchmark suite (round-5 WS5).

Each generator writes a small but real repository into a directory (no git — the
bakeoff engine inits + commits). They give the no-patch tasks genuine code to
fix, so an agent must actually read/edit/run, not apply a supplied patch. The
registry is keyed by the ``fixture`` field of a dataset task.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

PYPROJECT = ('[project]\nname = "{name}"\nversion = "0.1.0"\n'
             'requires-python = ">=3.11"\n')


def _write(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def python_buggy_app(root: Path) -> None:
    """divide() returns 0 on a zero divisor; must raise ZeroDivisionError."""
    _write(root, {
        "calculator.py": "def divide(a, b):\n    return 0\n",
        "test_calculator.py": (
            "import pytest\nfrom calculator import divide\n\n\n"
            "def test_zero():\n    with pytest.raises(ZeroDivisionError):\n"
            "        divide(1, 0)\n\n\ndef test_ok():\n    assert divide(6, 2) == 3\n"),
        "pyproject.toml": PYPROJECT.format(name="buggy"),
    })


def python_package_with_cli(root: Path) -> None:
    """A CLI whose `add` subcommand ignores its second argument (bug)."""
    _write(root, {
        "app/__init__.py": "",
        "app/core.py": "def add(a, b):\n    return a  # BUG: ignores b\n",
        "test_core.py": (
            "from app.core import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"),
        "pyproject.toml": PYPROJECT.format(name="cliapp"),
    })


def refactor_app(root: Path) -> None:
    """Behaviour-correct but messy; a refactor must preserve behaviour."""
    _write(root, {
        "shapes.py": (
            "def area(kind, x, y=0):\n"
            "    if kind == 'rect':\n        return x * y\n"
            "    elif kind == 'square':\n        return x * x\n"
            "    else:\n        return 0\n"),
        "test_shapes.py": (
            "from shapes import area\n\n\n"
            "def test_rect():\n    assert area('rect', 2, 3) == 6\n\n\n"
            "def test_square():\n    assert area('square', 4) == 16\n"),
        "pyproject.toml": PYPROJECT.format(name="shapes"),
    })


def security_sensitive_app(root: Path) -> None:
    """Uses eval() on input; a safe fix must remove the unsafe evaluation."""
    _write(root, {
        "calc_eval.py": (
            "def compute(expr):\n"
            "    return eval(expr)  # noqa: S307 - intentionally unsafe for the fixture\n"),
        "test_calc_eval.py": (
            "from calc_eval import compute\n\n\n"
            "def test_basic():\n    assert compute('1 + 2') == 3\n"),
        "pyproject.toml": PYPROJECT.format(name="seceval"),
    })


def migration_app(root: Path) -> None:
    """A dict-based store that must migrate to include a schema version field."""
    _write(root, {
        "store.py": (
            "def make_record(name):\n    return {'name': name}\n"),
        "test_store.py": (
            "from store import make_record\n\n\n"
            "def test_has_version():\n    assert make_record('x').get('version') == 1\n"),
        "pyproject.toml": PYPROJECT.format(name="migrate"),
    })


FIXTURES: dict[str, Callable[[Path], None]] = {
    "python_buggy_app": python_buggy_app,
    "python_package_with_cli": python_package_with_cli,
    "refactor_app": refactor_app,
    "security_sensitive_app": security_sensitive_app,
    "migration_app": migration_app,
}


def build_fixture(name: str, root: Path) -> None:
    if name not in FIXTURES:
        raise KeyError(f"unknown fixture {name!r}; known: {sorted(FIXTURES)}")
    FIXTURES[name](root)
