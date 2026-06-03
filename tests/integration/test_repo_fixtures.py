"""Realistic repo fixtures (Alpha 11, WS13)."""

from __future__ import annotations

from acp.evaluation.repo_fixtures import FIXTURE_KINDS, make_all_fixtures


def test_all_fixture_kinds_created(tmp_path) -> None:
    result = make_all_fixtures(tmp_path)
    assert set(result) == set(FIXTURE_KINDS)
    for kind, info in result.items():
        assert info["source_files"], f"{kind} has no source files"
        assert info["test_files"], f"{kind} has no test file"
        assert info["generated_files"] or info["decoy_files"], \
            f"{kind} has no generated/decoy file"


def test_security_and_migration_fixtures_have_relevant_files(tmp_path) -> None:
    result = make_all_fixtures(tmp_path)
    assert result["security_auth_app"]["security_files"]
    assert result["db_migration_app"]["migration_files"]
