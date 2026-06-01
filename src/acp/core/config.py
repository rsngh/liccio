"""Configuration system (charter §6).

Config sources, in order of precedence (highest last):
  1. defaults defined here
  2. YAML file at ACP_CONFIG_FILE (if set)
  3. .env file
  4. environment variables (ACP_ prefix)
  5. explicit overrides passed in code / CLI flags

Sensitive values are redacted in repr/log output.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from acp.core.redaction import Redactor


class ACPSettings(BaseSettings):
    """Top-level runtime settings."""

    model_config = SettingsConfigDict(
        env_prefix="ACP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite+aiosqlite:///./acp.db"
    sync_database_url: str | None = None
    artifact_dir: Path = Path(".acp/artifacts")
    workspace_dir: Path = Path(".acp/workspaces")

    default_token_budget: int = 80_000
    default_cost_budget_usd: float = 5.0
    default_command_timeout_s: int = 120

    allow_network_by_default: bool = False
    enable_external_agents: bool = False
    enable_docker: bool = False
    docker_image: str = "python:3.11-slim"
    docker_memory_mb: int = 1024
    docker_cpus: float = 1.0
    docker_pids_limit: int = 256
    enable_qdrant: bool = False
    enable_pgvector: bool = False
    enable_braintrust: bool = False
    enable_langsmith: bool = False

    random_seed: int = 1234

    redacted_env_patterns: list[str] = Field(
        default_factory=lambda: [
            r".*TOKEN.*",
            r".*KEY.*",
            r".*SECRET.*",
            r".*PASSWORD.*",
            r".*CREDENTIAL.*",
        ]
    )

    # Secrets — held as SecretStr so they never appear in repr/logs.
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    @field_validator("default_token_budget")
    @classmethod
    def _token_budget_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("default_token_budget must be positive")
        return v

    @field_validator("default_cost_budget_usd")
    @classmethod
    def _cost_budget_nonneg(cls, v: float) -> float:
        if v < 0:
            raise ValueError("default_cost_budget_usd must be >= 0")
        return v

    @field_validator("default_command_timeout_s")
    @classmethod
    def _timeout_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("default_command_timeout_s must be positive")
        return v

    def redactor(self) -> Redactor:
        """A Redactor seeded with this config's patterns and known secrets."""
        literals: list[str] = []
        for secret in (self.openai_api_key, self.anthropic_api_key):
            if secret is not None:
                literals.append(secret.get_secret_value())
        return Redactor(
            key_patterns=tuple(self.redacted_env_patterns),
            extra_secret_values=literals,
        )

    def safe_dict(self) -> dict[str, Any]:
        """Config as a dict with secrets masked — safe to log."""
        data = self.model_dump(mode="json")
        for k in ("openai_api_key", "anthropic_api_key"):
            if data.get(k) is not None:
                data[k] = "***REDACTED***"
        return data


def _load_yaml_overrides() -> dict[str, Any]:
    path = os.environ.get("ACP_CONFIG_FILE")
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    loaded = yaml.safe_load(p.read_text()) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"ACP_CONFIG_FILE {path} must contain a YAML mapping")
    return loaded


def load_settings(**overrides: Any) -> ACPSettings:
    """Load settings merging YAML file, env/.env, and explicit overrides."""
    merged: dict[str, Any] = {}
    merged.update(_load_yaml_overrides())
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return ACPSettings(**merged)


_settings: ACPSettings | None = None


def get_settings() -> ACPSettings:
    """Process-wide cached settings."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Clear the cache (used by tests)."""
    global _settings
    _settings = None
