"""Policy-graph warehouse + signature explorer (Alpha 41).

Makes the AgensFlow coordination policy inspectable, persistable, and warm-startable across
repos: serialize a PolicyGraph to a dict (and back) so action-values survive a restart and
can be warm-started into a new repo; a folded signature that ADDS a repo_family dimension so
policy transfers within a repo family; and an explorer that ranks, per signature, the best
action by learned value — the operator's "why this action here?" view.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.routing.policy_graph import ACTIONS, PolicyGraph, _ActionStat


@dataclass(frozen=True)
class RepoFamilySignature:
    """A folded signature extended with repo family + budget state (Alpha 41 dims)."""
    base_key: str               # a FoldedTaskSignature.key()
    repo_family: str = "unknown"
    budget_state: str = "normal"  # normal | low | exhausted

    def key(self) -> str:
        return f"{self.base_key}::repo={self.repo_family}::budget={self.budget_state}"


def serialize_graph(graph: PolicyGraph) -> dict:
    """Persistable snapshot of a PolicyGraph (signature + global action sums/counts)."""
    return {
        "by_sig": {k: {a: {"total_reward": s.total_reward, "n": s.n}
                       for a, s in acts.items()}
                   for k, acts in graph._by_sig.items()},
        "global": {a: {"total_reward": s.total_reward, "n": s.n}
                   for a, s in graph._global.items()},
    }


def deserialize_graph(data: dict) -> PolicyGraph:
    """Rebuild a PolicyGraph from a snapshot (warm-start across sessions/repos)."""
    g = PolicyGraph()
    for key, acts in data.get("by_sig", {}).items():
        g._by_sig[key] = {a: _ActionStat(total_reward=v["total_reward"], n=v["n"])
                          for a, v in acts.items() if a in ACTIONS}
    for a, v in data.get("global", {}).items():
        if a in ACTIONS:
            g._global[a] = _ActionStat(total_reward=v["total_reward"], n=v["n"])
    return g


def explore(graph: PolicyGraph) -> dict:
    """Per-signature best action + value + n — the operator's policy inspection view."""
    rows = []
    for key, acts in graph._by_sig.items():
        ranked = sorted(((a, s.mean(), s.n) for a, s in acts.items()),
                        key=lambda t: (t[1], t[2]), reverse=True)
        if ranked:
            best = ranked[0]
            rows.append({"signature": key, "best_action": best[0],
                         "value": best[1], "n": best[2],
                         "actions": {a: {"value": m, "n": n} for a, m, n in ranked}})
    return {"experiment": "policy_graph_explore", "n_signatures": len(rows),
            "signatures": sorted(rows, key=lambda r: r["n"], reverse=True)}


def warm_start_across_repos(graphs: list, *, weight: float = 0.5) -> PolicyGraph:
    """Merge several repos' policy graphs into one warm-started graph (cross-repo transfer)."""
    merged = PolicyGraph()
    for g in graphs:
        merged.warm_start(g, weight=weight)
    return merged
