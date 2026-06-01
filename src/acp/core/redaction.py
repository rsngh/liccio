"""Secret redaction utilities.

Every value that leaves the process (logs, traces, artifacts, prompts, command
output) must pass through redaction. We never want secrets in any persisted
record. Redaction is pattern-based on *keys* (env var names, dict keys) plus a
set of *value* heuristics for common token shapes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"

DEFAULT_KEY_PATTERNS: tuple[str, ...] = (
    r".*TOKEN.*",
    r".*KEY.*",
    r".*SECRET.*",
    r".*PASSWORD.*",
    r".*CREDENTIAL.*",
    r".*AUTH.*",
    r".*SESSION.*",
)

# Value-shape heuristics for things that look like secrets even when the key is
# innocuous. Kept conservative to avoid over-redacting normal text.
DEFAULT_VALUE_PATTERNS: tuple[str, ...] = (
    r"sk-[A-Za-z0-9_\-]{16,}",  # OpenAI-style
    r"sk-ant-[A-Za-z0-9_\-]{16,}",  # Anthropic-style
    r"ghp_[A-Za-z0-9]{20,}",  # GitHub PAT
    r"gho_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)


class Redactor:
    """Redacts secrets from strings, mappings, and nested structures."""

    def __init__(
        self,
        key_patterns: tuple[str, ...] | list[str] = DEFAULT_KEY_PATTERNS,
        value_patterns: tuple[str, ...] | list[str] = DEFAULT_VALUE_PATTERNS,
        extra_secret_values: list[str] | None = None,
    ) -> None:
        self._key_re = [re.compile(p, re.IGNORECASE) for p in key_patterns]
        self._value_re = [re.compile(p) for p in value_patterns]
        # Explicit secret values (e.g. the actual API keys read from env) are
        # redacted by exact substring match regardless of context.
        self._literal_secrets = [v for v in (extra_secret_values or []) if v]

    def key_is_sensitive(self, key: str) -> bool:
        return any(rx.fullmatch(key) for rx in self._key_re)

    def redact_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        for secret in self._literal_secrets:
            if secret and secret in out:
                out = out.replace(secret, REDACTED)
        for rx in self._value_re:
            out = rx.sub(REDACTED, out)
        return out

    def redact_value(self, key: str, value: Any) -> Any:
        if self.key_is_sensitive(key):
            return REDACTED
        return self.redact(value)

    def redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {k: self.redact_value(str(k), v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            redacted = [self.redact(v) for v in value]
            return type(value)(redacted)
        return value

    def redact_env(self, env: Mapping[str, str]) -> dict[str, str]:
        """Return a copy of env with sensitive values redacted.

        Keys are always preserved (callers often need the key names); only
        values for sensitive keys are masked.
        """
        return {k: (REDACTED if self.key_is_sensitive(k) else v) for k, v in env.items()}

    def sanitized_env_keys(self, env: Mapping[str, str]) -> list[str]:
        """Names of env vars present, safe to log (no values)."""
        return sorted(env.keys())


_default_redactor = Redactor()


def redact_text(text: str) -> str:
    return _default_redactor.redact_text(text)


def redact(value: Any) -> Any:
    return _default_redactor.redact(value)
