"""Provider contract (GOALS Alpha 43 P8).

Every provider — live or hook — must satisfy the same contract so the metarouter can treat them
uniformly and never mistake an unavailable provider for a bad agent.
"""

from __future__ import annotations

from acp.providers.base import Provider

_ACTIONABLE = ("sdk", "key", "not set", "not installed", "not found", "path")


def check_provider_contract(provider: Provider) -> dict:
    av = provider.availability()
    cm = provider.cost_model()
    checks = {
        "health_reports_reason": bool(av.reason),
        "unavailable_has_actionable_reason": (
            av.available or any(tok in av.reason.lower() for tok in _ACTIONABLE)),
        "failure_is_infra_not_capability": (
            provider.classify_failure(available=False).startswith("infra")),
        "cost_model_present_or_unknown": (
            cm.is_known or cm.unknown_cost_behavior in ("unknown", "estimate")),
        "budget_retries_safe_default": provider.budget.max_retries == 0,
        "budget_timeout_declared": provider.budget.per_call_timeout_s > 0,
        "trace_capability_declared": isinstance(provider.capability.supports_command_traces, bool),
    }
    return {"provider": provider.name, "available": av.available, "reason": av.reason,
            "checks": checks, "contract_passed": all(checks.values())}


def provider_contract_gate(providers: list[Provider]) -> dict:
    rows = [check_provider_contract(p) for p in providers]
    return {
        "experiment": "provider_contract_gate",
        "n_providers": len(rows),
        "n_contract_passed": sum(1 for r in rows if r["contract_passed"]),
        "all_contracts_pass": all(r["contract_passed"] for r in rows),
        "available": [r["provider"] for r in rows if r["available"]],
        "unavailable": [r["provider"] for r in rows if not r["available"]],
        "providers": rows,
        "note": "OpenAI/Gemini are hooks: contract-tested without network; live-skipped here.",
    }
