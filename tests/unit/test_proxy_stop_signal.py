"""P1: the proxy verifier as the production stop signal."""

from __future__ import annotations

from acp.evaluation.comparator_strength import Candidate
from acp.verification.independent_proof import ProxyVerdict
from acp.verification.proxy_stop_signal import (
    decide,
    proxy_confidence,
    proxy_health_by_family,
)


def _verdict(cid: str, *, proxy_pass: bool, public_pass: bool = True,
             surviving: int = 3, failed: int = 0, adversarial: bool = False) -> ProxyVerdict:
    return ProxyVerdict(
        candidate_id=cid, proxy_pass=proxy_pass, public_pass=public_pass,
        independent_pass=(failed == 0), adversarial_high=adversarial,
        n_checks_run=surviving, n_checks_surviving=surviving, n_checks_failed=failed)


def _cand(cid: str, *, public_pass: bool = True, diff_lines: int = 10) -> Candidate:
    return Candidate(id=cid, public_pass=public_pass, hidden_pass=False, diff_lines=diff_lines)


def test_commits_minimal_proxy_verified_candidate_and_charges_cost() -> None:
    cands = [_cand("a", diff_lines=20), _cand("b", diff_lines=5)]
    verdicts = {"a": _verdict("a", proxy_pass=True), "b": _verdict("b", proxy_pass=True)}
    sig = decide(cands, verdicts, gen_cost_usd=0.002, run_cost_usd=0.001, risk_level="low")
    assert sig.action == "commit"
    assert sig.selected == "b"            # minimal diff among proxy-verified
    assert sig.selected_proxy_pass
    assert sig.proxy_cost_usd == 0.003     # the verifier is not free


def test_public_only_cannot_promote_where_proxy_contradicts() -> None:
    # 'a' passes public but the proxy rejects it (overfit); no candidate is proxy-verified.
    cands = [_cand("a")]
    verdicts = {"a": _verdict("a", proxy_pass=False, surviving=3, failed=2)}
    sig = decide(cands, verdicts, risk_level="low")
    assert sig.action == "human_review"
    assert sig.selected_proxy_pass is False
    assert "proxy" in sig.reason


def test_no_independent_checks_is_weak_evidence_to_human_review() -> None:
    # public passed and proxy_pass is True, but there were no surviving independent checks:
    # the proxy has only the public signal -> insufficient evidence -> human review.
    cands = [_cand("a")]
    verdicts = {"a": _verdict("a", proxy_pass=True, surviving=0, failed=0)}
    sig = decide(cands, verdicts, risk_level="low")
    assert sig.action == "human_review"
    assert sig.sufficiency == 0.0


def test_high_risk_raises_the_commit_bar() -> None:
    # two surviving checks that pass -> judge 1.0, sufficiency 2/3; low risk commits,
    # critical risk does not auto-commit.
    cands = [_cand("a")]
    verdicts = {"a": _verdict("a", proxy_pass=True, surviving=2, failed=0)}
    low = decide(cands, verdicts, risk_level="low")
    crit = decide([_cand("a")], {"a": _verdict("a", proxy_pass=True, surviving=2, failed=0)},
                  risk_level="critical")
    assert low.action == "commit"
    assert crit.action == "human_review"


def test_proxy_confidence_grades_with_corroboration() -> None:
    j_full, suf_full = proxy_confidence(_verdict("x", proxy_pass=True, surviving=3, failed=0))
    j_thin, suf_thin = proxy_confidence(_verdict("x", proxy_pass=True, surviving=1, failed=0))
    assert j_full == 1.0 and suf_full == 1.0
    assert j_thin == 1.0 and suf_thin < suf_full     # less corroboration -> lower sufficiency
    # adversarial-high gets no confidence at all
    assert proxy_confidence(_verdict("x", proxy_pass=False, adversarial=True)) == (0.0, 0.0)


def test_proxy_health_by_family_precision_recall() -> None:
    samples = [
        # family "calc": proxy is perfectly calibrated
        {"family": "calc", "proxy_pass": True, "hidden_pass": True},
        {"family": "calc", "proxy_pass": False, "hidden_pass": False},
        # family "str": one dangerous false positive (proxy said ok, hidden failed)
        {"family": "str", "proxy_pass": True, "hidden_pass": True},
        {"family": "str", "proxy_pass": True, "hidden_pass": False},
        # family "graph": one false negative (proxy too cautious -> sent a good one to humans)
        {"family": "graph", "proxy_pass": False, "hidden_pass": True},
        {"family": "graph", "proxy_pass": True, "hidden_pass": True},
    ]
    health = proxy_health_by_family(samples)
    assert health["calc"].precision == 1.0 and health["calc"].recall == 1.0
    assert health["str"].precision == 0.5 and health["str"].false_positives == 1
    assert health["graph"].recall == 0.5 and health["graph"].false_negatives == 1
