"""Harness arena — offline tests (no network, no CLI spawn).

Guards the wiring: the Gemini-CLI vendor spec, the policy registry, corpus integrity (oracle solves
its own hidden test / buggy stub fails it), and the sandbox secret-scrubbing contract. The live
harness solve-rates are measured in reports/harness_arena_*.json.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from evals.harness_arena import sandbox
from evals.harness_arena.harness_tasks import capability_corpus, ceiling_corpus
from evals.harness_arena.policies import ALL_POLICIES
from evals.metarouter_arena.policies import policy_cheap_static, policy_oracle

from acp.agents.vendor_native import VENDOR_SPECS


def test_gemini_cli_vendor_spec_registered() -> None:
    assert "gemini_cli" in VENDOR_SPECS
    spec = VENDOR_SPECS["gemini_cli"]
    assert spec.binary == "gemini"
    argv = spec.argv_fn(Path("/tmp/x"), "fix it")  # type: ignore[misc]
    assert argv[0] == "gemini" and "-p" in argv and "fix it" in argv
    assert "--yolo" in argv  # headless auto-approve


def test_policy_registry() -> None:
    assert set(ALL_POLICIES) == {"single_shot", "inproc_harness", "gemini_cli", "openhands"}


def test_corpora_nonempty_and_typed() -> None:
    cap = capability_corpus()
    ceil = ceiling_corpus()
    assert len(cap) >= 5
    assert len(ceil) >= 6
    # capability is self-contained (context_need none); ceiling is cross-file
    assert all(t.context_need == "none" for t in cap)
    assert all(t.context_need in ("cross_file_api", "broad_repo_map") for t in ceil)


def test_corpus_integrity_oracle_solves_buggy_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for spec in capability_corpus():
            assert policy_oracle(spec, root).solved, f"oracle failed {spec.name}"
            assert not policy_cheap_static(spec, root).solved, f"buggy solved {spec.name}"


def test_sandbox_scrubs_secrets(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSECRETSECRETSECRET12345")
    assert sandbox._secret_leak("token AIzaSECRETSECRETSECRET12345 here")
    assert "<REDACTED>" in sandbox._scrub("leak AIzaSECRETSECRETSECRET12345 end")
    assert "AIzaSECRETSECRETSECRET12345" not in sandbox._scrub("x AIzaSECRETSECRETSECRET12345")
