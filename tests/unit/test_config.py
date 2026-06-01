"""Phase 0 config tests (charter §6)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from acp.core.config import ACPSettings, load_settings


def test_defaults_load() -> None:
    s = ACPSettings()
    assert s.default_token_budget == 80_000
    assert s.default_cost_budget_usd == 5.0
    assert s.allow_network_by_default is False


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_DEFAULT_TOKEN_BUDGET", "1000")
    monkeypatch.setenv("ACP_ALLOW_NETWORK_BY_DEFAULT", "true")
    s = ACPSettings()
    assert s.default_token_budget == 1000
    assert s.allow_network_by_default is True


def test_yaml_override(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "acp.yaml"
    cfg.write_text("default_cost_budget_usd: 12.5\napp_env: prod\n")
    monkeypatch.setenv("ACP_CONFIG_FILE", str(cfg))
    s = load_settings()
    assert s.default_cost_budget_usd == 12.5
    assert s.app_env == "prod"


def test_secrets_redacted_in_repr_and_dict() -> None:
    s = ACPSettings(anthropic_api_key=SecretStr("sk-ant-supersecretvalue123456"))
    assert "supersecret" not in repr(s)
    assert s.safe_dict()["anthropic_api_key"] == "***REDACTED***"


def test_redactor_masks_known_secret() -> None:
    s = ACPSettings(openai_api_key=SecretStr("sk-thisisasecretkey0001"))
    r = s.redactor()
    out = r.redact_text("the key is sk-thisisasecretkey0001 ok")
    assert "sk-thisisasecretkey0001" not in out
    assert "***REDACTED***" in out


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_token_budget", 0),
        ("default_token_budget", -5),
        ("default_cost_budget_usd", -1.0),
        ("default_command_timeout_s", 0),
    ],
)
def test_invalid_budgets_fail(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ACPSettings(**{field: value})
