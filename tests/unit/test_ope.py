"""Offline policy evaluation (Alpha 6, WS3)."""

from __future__ import annotations

import pytest

from acp.routing.ope import (
    OPEError,
    OPESample,
    evaluate_policy,
    fit_reward_model,
    from_decision_log,
)

# Two arms; arm "good" pays reward 1.0, arm "bad" pays 0.0. The logging policy is
# uniform (0.5 each); we evaluate target policies that prefer one arm or the other.
CANDS = ["good", "bad"]


def _uniform_log(n: int = 200) -> list[OPESample]:
    out = []
    for i in range(n):
        action = "good" if i % 2 == 0 else "bad"
        reward = 1.0 if action == "good" else 0.0
        out.append(OPESample("ctx", action, behavior_prob=0.5, reward=reward,
                             candidates=CANDS))
    return out


def _greedy(best: str):
    # Deterministic-ish target: 0.9 mass on `best`, 0.1 on the other.
    def pi(ctx: str, action: str, cands: list[str]) -> float:
        return 0.9 if action == best else 0.1
    return pi


def test_empty_log_raises() -> None:
    with pytest.raises(OPEError):
        evaluate_policy([], _greedy("good"))


def test_invalid_propensity_rejected() -> None:
    with pytest.raises(OPEError):
        OPESample("ctx", "good", behavior_prob=0.0, reward=1.0, candidates=CANDS)


def test_target_preferring_good_beats_preferring_bad() -> None:
    log = _uniform_log()
    good = evaluate_policy(log, _greedy("good"), seed=1)
    bad = evaluate_policy(log, _greedy("bad"), seed=1)
    # All four estimators should rank "prefer good" above "prefer bad".
    assert good.ips.value > bad.ips.value
    assert good.snips.value > bad.snips.value
    assert good.dr.value > bad.dr.value
    # And the difference is real: CIs do not overlap.
    assert good.dr.ci_low > bad.dr.ci_high


def test_snips_and_dr_recover_reward_scale() -> None:
    log = _uniform_log()
    rep = evaluate_policy(log, _greedy("good"), seed=2)
    # Target puts 0.9 on the reward-1 arm => value ~ 0.9.
    assert 0.8 <= rep.snips.value <= 1.0
    assert 0.8 <= rep.dr.value <= 1.0


def test_diagnostics_report_overlap_and_ess() -> None:
    log = _uniform_log(100)
    rep = evaluate_policy(log, _greedy("good"), seed=3)
    d = rep.diagnostics
    assert d.n == 100
    assert 0 < d.effective_sample_size <= 100
    assert d.overlap == 1.0  # target has positive prob on every logged action
    assert d.min_behavior_prob == 0.5


def test_clipping_reduces_max_weight_mass() -> None:
    # Rare logged action (tiny propensity) blows up the IPS weight; clipping caps it.
    log = [OPESample("ctx", "good", behavior_prob=0.01, reward=1.0, candidates=CANDS)]
    log += _uniform_log(50)
    rep = evaluate_policy(log, _greedy("good"), weight_clip=5.0, seed=4)
    assert rep.diagnostics.max_weight > 5.0
    assert rep.diagnostics.clip_fraction > 0.0


def test_reward_model_fallback_levels() -> None:
    q = fit_reward_model(_uniform_log(20))
    assert q("ctx", "good") == pytest.approx(1.0)
    assert q("ctx", "bad") == pytest.approx(0.0)
    # Unknown action -> context mean (0.5); unknown context -> global mean.
    assert q("ctx", "unseen") == pytest.approx(0.5)
    assert 0.0 <= q("other-ctx", "x") <= 1.0


def test_from_decision_log_adapts_persisted_pairs() -> None:
    from acp.core.enums import AgentKind
    from acp.routing.policy import PolicyDecision
    from acp.schemas.learning import RewardEvent
    from acp.schemas.routing import RoutingAction

    action = RoutingAction(agent_kind=AgentKind.FAKE, agent_name="fake")
    dec = PolicyDecision(policy_version="v1", action=action, action_probability=0.5,
                         context_key="ctx",
                         candidate_scores={action.key(): 1.0, "other": 0.0})
    rew = RewardEvent(task_id="t", reward=1.0, components={"objective": 1.0})
    samples = from_decision_log([(dec, rew)])
    assert samples[0].context_key == "ctx"
    assert samples[0].behavior_prob == 0.5
    assert action.key() in samples[0].candidates


def test_bootstrap_is_reproducible() -> None:
    log = _uniform_log()
    a = evaluate_policy(log, _greedy("good"), seed=7)
    b = evaluate_policy(log, _greedy("good"), seed=7)
    assert a.dr.ci_low == b.dr.ci_low and a.dr.ci_high == b.dr.ci_high
