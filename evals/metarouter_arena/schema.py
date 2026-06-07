"""MetaRouter Arena — schemas (GOALS Alpha 42 P0).

The arena is the evaluation substrate: it runs an unseen task across competing *policies*
(static single-agent baselines, the current ACP router, advisor/best-of-k/repo-map routers, …)
and scores them on verified success per dollar, separating **adapter availability** from
**capability** so an unavailable provider never looks like a bad agent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

# --- context need: what kind of context the task requires to be solvable ---------------
ContextNeed = str  # none | exact_symbol | cross_file_api | broad_repo_map | memory_required


class AdapterStatus(str, Enum):
    """How a policy's underlying adapter behaved on a task — availability vs capability."""

    LIVE_CONCLUSIVE = "live_conclusive"        # ran and produced a verdict (solved/failed)
    LIVE_INCONCLUSIVE = "live_inconclusive"    # ran but infra/provider noise -> no verdict
    UNAVAILABLE = "unavailable"                # SDK/key/binary/network missing -> not tried
    MOCK_CONTRACT_ONLY = "mock_contract_only"  # hook exists, only contract-tested
    FIXTURE_ONLY = "fixture_only"


@dataclass(frozen=True)
class ArenaTaskSpec:
    name: str
    task_type: str                      # bugfix | feature | security_fix | migration | ...
    risk_level: str                     # low | medium | high
    difficulty_band: str                # easy | medium | hard
    context_need: ContextNeed
    module_path: str
    buggy: str                          # buggy module the policy sees
    fixed: str                          # reference fix (offline fairness only; never shown)
    public_test: str                    # ships with the task (visible)
    hidden_test: str                    # held-out verifier (never shown to the agent)
    issue_text: str
    budget_class: str = "normal_bugfix"
    extra_files: dict[str, str] = field(default_factory=dict)  # other repo files (for context)
    forbidden_files: tuple[str, ...] = ()


@dataclass
class ArenaAttempt:
    """One policy's attempt at one task."""

    task: str
    policy: str
    adapter_status: str                 # AdapterStatus value
    solved: bool                        # hidden tests pass (the verified-success signal)
    public_solved: bool                 # public tests pass (weaker signal)
    conclusive: bool                    # a real verdict was obtained (vs infra noise)
    cost_usd: float
    latency_s: float
    changed_files: list[str] = field(default_factory=list)
    tool_calls: int = 0
    activated: bool | None = None       # harness activation (HAR) where applicable
    followed: bool | None = None        # harness adherence (HFR)
    advisor_calls: int = 0
    candidates_sampled: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PolicyScore:
    policy: str
    n_tasks: int = 0
    n_conclusive: int = 0
    n_solved: int = 0                   # hidden-test verified
    n_public_solved: int = 0
    n_unavailable: int = 0
    total_cost: float = 0.0
    advisor_calls: int = 0
    candidates_sampled: int = 0
    sum_latency: float = 0.0

    def add(self, a: ArenaAttempt) -> None:
        self.n_tasks += 1
        self.total_cost += a.cost_usd
        self.sum_latency += a.latency_s
        self.advisor_calls += a.advisor_calls
        self.candidates_sampled += a.candidates_sampled
        if a.adapter_status == AdapterStatus.UNAVAILABLE.value:
            self.n_unavailable += 1
        if a.conclusive:
            self.n_conclusive += 1
        if a.solved:
            self.n_solved += 1
        if a.public_solved:
            self.n_public_solved += 1

    def to_dict(self) -> dict:
        # verified-success metrics use CONCLUSIVE attempts as the denominator (availability
        # and infra noise must not be charged against capability).
        conc = self.n_conclusive or 0
        n = self.n_tasks
        verified_rate = round(self.n_solved / conc, 4) if conc else 0.0
        cps = round(self.total_cost / self.n_solved, 6) if self.n_solved else None

        def rate(num: float) -> float:
            return round(num / n, 4) if n else 0.0

        return {
            "policy": self.policy,
            "n_tasks": n,
            "verified_success_rate": verified_rate,            # solved / conclusive
            "hidden_test_pass_rate": verified_rate,
            "public_pass_rate": rate(self.n_public_solved),
            "conclusive_rate": rate(conc),
            "inconclusive_rate": round(1 - conc / n, 4) if n else 0.0,
            "adapter_unavailable_rate": rate(self.n_unavailable),
            "n_solved": self.n_solved,
            "n_conclusive": conc,
            "total_cost_usd": round(self.total_cost, 6),
            "cost_per_verified_success": cps,
            "advisor_call_rate": rate(self.advisor_calls),
            "avg_latency_s": round(self.sum_latency / n, 3) if n else 0.0,
        }
