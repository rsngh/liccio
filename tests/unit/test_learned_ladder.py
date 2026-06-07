"""Offline-learned ladder — deterministic tests."""

from __future__ import annotations

from acp.routing.learned_ladder import Trace, learn_ladder


def test_learns_cheapest_solving_lever_per_signature() -> None:
    traces = [
        Trace("sigB", "cheap", solved=False, cost=0.001),
        Trace("sigB", "ctx", solved=True, cost=0.004),
        Trace("sigB", "strong", solved=True, cost=0.02),
    ] * 3
    ll = learn_ladder(traces, fallback_order=["cheap", "ctx", "strong"])
    # both ctx and strong solve sigB, but ctx has lower expected cost-per-success -> first
    assert ll.ladder_for("sigB")[0] == "ctx"
    assert "cheap" not in ll.ladder_for("sigB")          # never solved -> dropped


def test_unseen_signature_falls_back_to_global() -> None:
    ll = learn_ladder([Trace("sigA", "cheap", True, 0.001)], fallback_order=["cheap", "ctx"])
    assert ll.ladder_for("never_seen") == ["cheap", "ctx"]


def test_signature_with_no_solver_falls_back() -> None:
    traces = [Trace("hard", "cheap", False, 0.001), Trace("hard", "ctx", False, 0.004)]
    ll = learn_ladder(traces, fallback_order=["cheap", "ctx", "strong"])
    assert ll.ladder_for("hard") == ["cheap", "ctx", "strong"]   # nothing solved -> global order
