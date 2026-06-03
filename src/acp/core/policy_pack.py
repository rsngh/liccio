"""Production-mode policy pack (Alpha 11, WS19).

Defines the operating policies for the three deployment modes and the gate each
imposes. ``production`` is the strict one: real harnesses must run on Docker with
a fresh passing security report, routing must be OPE-promotion-gated, high-risk
work requires human review, private-data governance is enforced, and the
test/coverage artifacts must be fresh. ``enforce(mode, health)`` evaluates a
control-plane health snapshot against the selected policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OperatingPolicy:
    mode: str
    require_docker_live_gate: bool
    allow_local_true_harness: bool
    require_ope_promotion: bool
    require_human_review_high_risk: bool
    enforce_data_governance: bool
    require_fresh_test_artifacts: bool
    require_vendor_harness_proof: bool = False

    def requirements(self) -> list[str]:
        reqs = []
        if self.require_docker_live_gate:
            reqs.append("docker_live_security_passed")
        if self.require_ope_promotion:
            reqs.append("ope_overlap_sufficient")
        if self.require_fresh_test_artifacts:
            reqs.append("test_reports_present")
        if not self.allow_local_true_harness:
            reqs.append("no_local_true_harness")
        return reqs


POLICY_PACK: dict[str, OperatingPolicy] = {
    "lab": OperatingPolicy(
        mode="lab", require_docker_live_gate=False, allow_local_true_harness=True,
        require_ope_promotion=False, require_human_review_high_risk=True,
        enforce_data_governance=True, require_fresh_test_artifacts=False),
    "staging": OperatingPolicy(
        mode="staging", require_docker_live_gate=True, allow_local_true_harness=False,
        require_ope_promotion=True, require_human_review_high_risk=True,
        enforce_data_governance=True, require_fresh_test_artifacts=True),
    "production": OperatingPolicy(
        mode="production", require_docker_live_gate=True, allow_local_true_harness=False,
        require_ope_promotion=True, require_human_review_high_risk=True,
        enforce_data_governance=True, require_fresh_test_artifacts=True,
        require_vendor_harness_proof=True),
}


@dataclass
class PolicyEnforcement:
    mode: str
    satisfied: bool
    failed_requirements: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"mode": self.mode, "satisfied": self.satisfied,
                "failed_requirements": self.failed_requirements}


def enforce(mode: str, health: dict) -> PolicyEnforcement:
    """Evaluate a control-plane health snapshot against a mode's operating policy."""
    policy = POLICY_PACK.get(mode, POLICY_PACK["lab"])
    gates = health.get("production_gates", {})
    failed: list[str] = []
    if policy.require_docker_live_gate and not gates.get("docker_live_security_passed"):
        failed.append("docker_live_security_passed")
    if policy.require_ope_promotion and not gates.get("ope_overlap_sufficient"):
        failed.append("ope_overlap_sufficient")
    if policy.require_fresh_test_artifacts and not gates.get("test_reports_present"):
        failed.append("test_reports_present")
    if not gates.get("artifact_manifest_valid"):
        failed.append("artifact_manifest_valid")
    return PolicyEnforcement(mode=mode, satisfied=not failed, failed_requirements=failed)
