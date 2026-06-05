"""Research-engineering benchmark hardening (Alpha 24 area 15).

NanoGPT-Bench reports coding agents recover only ~9% of human progress on real AI-R&D tasks
and over-focus on hyperparameter tuning rather than algorithmic change. These tasks test
whether ACP helps agents do research engineering, not just patch small bugs. The benchmark:

- classifies a change as algorithmic vs hyperparameter-tuning vs mixed (from changed
  symbols), so progress from tuning is not mistaken for a real contribution;
- scores ResearchProgress = recovered fraction of the human baseline->target gap, and CAPS
  the reward for non-substantive (tuning-only) changes so passing tests via tuning is not
  rewarded as algorithmic progress;
- routes research tasks differently from bugfix: they engage advisor + HeavySkill + topology
  search (the heavy machinery), reflecting that research tasks are harder and ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_HYPERPARAM = {"learning_rate", "lr", "batch_size", "epochs", "seed", "weight_decay",
               "dropout", "warmup", "momentum", "n_layers", "hidden_size"}
_ALGORITHMIC = {"forward", "loss", "attention", "architecture", "optimizer_step",
                "algorithm", "mcts", "value_head", "policy_head", "backbone", "embedding",
                "rollout", "self_play", "reward_model"}
RESEARCH_KINDS = ("reproduce_baseline", "improve_architecture", "ablate_idea",
                  "alphazero_loop", "experiment_report")
# the reward ceiling for a change that is only hyperparameter tuning
TUNING_REWARD_CAP = 0.2


def classify_change(changed_symbols: list) -> str:
    """algorithmic | hyperparameter_tuning | mixed | unknown from the changed symbols."""
    low = [s.lower() for s in changed_symbols]
    has_algo = any(any(sig in s for sig in _ALGORITHMIC) for s in low)
    has_hp = any(any(k in s for k in _HYPERPARAM) for s in low)
    if has_algo and has_hp:
        return "mixed"
    if has_algo:
        return "algorithmic"
    if has_hp:
        return "hyperparameter_tuning"
    return "unknown"


@dataclass
class ResearchTask:
    id: str
    kind: str
    baseline_metric: float
    human_target_metric: float
    risk: str = "medium"


@dataclass
class ResearchProgress:
    task_id: str
    recovered_fraction: float
    substantive: bool
    change_type: str
    reward: float

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def research_progress(task: ResearchTask, achieved_metric: float, changed_symbols: list
                      ) -> ResearchProgress:
    """Recovered fraction of the human gap, with reward capped for tuning-only changes."""
    denom = task.human_target_metric - task.baseline_metric
    recovered = ((achieved_metric - task.baseline_metric) / denom) if abs(denom) > 1e-9 else 0.0
    recovered = round(max(0.0, recovered), 4)
    change_type = classify_change(changed_symbols)
    substantive = change_type in ("algorithmic", "mixed")
    reward = recovered if substantive else round(min(recovered, TUNING_REWARD_CAP), 4)
    return ResearchProgress(task_id=task.id, recovered_fraction=recovered,
                            substantive=substantive, change_type=change_type, reward=reward)


def research_routing(task: ResearchTask) -> dict:
    """Research tasks engage the heavy machinery; bugfix-style tasks do not."""
    is_research = task.kind in RESEARCH_KINDS
    return {"consult_advisor": is_research, "heavy_skill": is_research,
            "topology_search": is_research,
            "strict_verification": True,           # always verify
            "rationale": ("research task -> heavy machinery" if is_research
                          else "non-research -> standard routing")}


@dataclass
class ResearchBenchmarkReport:
    n_tasks: int
    mean_recovered: float
    mean_reward: float
    n_substantive: int
    n_tuning_only: int
    routes_research_differently: bool
    rows: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"experiment": "research_engineering_benchmark", "n_tasks": self.n_tasks,
                "mean_recovered": self.mean_recovered, "mean_reward": self.mean_reward,
                "n_substantive": self.n_substantive, "n_tuning_only": self.n_tuning_only,
                "routes_research_differently": self.routes_research_differently,
                "rows": self.rows}


def run_research_benchmark(records: list) -> ResearchBenchmarkReport:
    """records: list of (ResearchTask, achieved_metric, changed_symbols)."""
    rows = []
    for task, achieved, symbols in records:
        prog = research_progress(task, achieved, symbols)
        route = research_routing(task)
        rows.append({**prog.to_dict(), "kind": task.kind,
                     "routed_to_advisor": route["consult_advisor"]})
    n = len(rows) or 1
    bugfix = ResearchTask("b", "bugfix", 0.0, 1.0)
    return ResearchBenchmarkReport(
        n_tasks=len(rows),
        mean_recovered=round(sum(r["recovered_fraction"] for r in rows) / n, 4),
        mean_reward=round(sum(r["reward"] for r in rows) / n, 4),
        n_substantive=sum(r["substantive"] for r in rows),
        n_tuning_only=sum(not r["substantive"] for r in rows),
        # research tasks route to advisor; a bugfix task does not -> different routing
        routes_research_differently=(any(r["routed_to_advisor"] for r in rows)
                                     and not research_routing(bugfix)["consult_advisor"]),
        rows=rows)
