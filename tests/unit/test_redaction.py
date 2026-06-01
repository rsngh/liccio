"""Secret redaction tests (charter §1.2, §6)."""

from __future__ import annotations

from acp.core.redaction import REDACTED, Redactor


def test_sensitive_keys_redacted() -> None:
    r = Redactor()
    out = r.redact({"API_KEY": "abc123", "name": "ok", "DB_PASSWORD": "hunter2"})
    assert out["API_KEY"] == REDACTED
    assert out["DB_PASSWORD"] == REDACTED
    assert out["name"] == "ok"


def test_value_shape_patterns() -> None:
    r = Redactor()
    assert REDACTED in r.redact_text("token sk-ant-abcdefghijklmnopqrstuvwx here")
    assert REDACTED in r.redact_text("ghp_abcdefghijklmnopqrstuvwxyz123456")


def test_literal_secret_masked_everywhere() -> None:
    r = Redactor(extra_secret_values=["MY-LITERAL-SECRET"])
    assert "MY-LITERAL-SECRET" not in r.redact_text("value=MY-LITERAL-SECRET")


def test_redact_env_keeps_keys_masks_values() -> None:
    r = Redactor()
    env = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-secret"}
    red = r.redact_env(env)
    assert red["PATH"] == "/usr/bin"
    assert red["OPENAI_API_KEY"] == REDACTED
    assert r.sanitized_env_keys(env) == ["OPENAI_API_KEY", "PATH"]


def test_nested_redaction() -> None:
    r = Redactor()
    out = r.redact({"outer": {"SECRET_TOKEN": "x", "list": ["sk-ant-aaaaaaaaaaaaaaaaaaaa"]}})
    assert out["outer"]["SECRET_TOKEN"] == REDACTED
    assert out["outer"]["list"][0] == REDACTED
