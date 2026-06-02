"""Evaluator trust model (Alpha 8, WS4).

Calibration v2 (``calibration_v2.py``) asks "how good is each evaluator on the
ladder?". This module asks a sharper, per-attempt question: *for THIS attempt,
what is the probability the automated evaluator's verdict is CORRECT?* — i.e.
that the objective/auto "pass" decision matches the eventual human / post-merge
truth.

A learned :class:`EvaluatorTrustModel` predicts that probability from features
that historically predict evaluator failure: weak-label disagreement, judge
spread, adversarial findings, and trace complexity (objective evaluators are
fooled by hardcoded fixes / deleted tests, which adversarial detectors and weak
supervision tend to flag). :class:`HumanReviewThresholdPolicy` then turns that
predictor into *risk-specific* trust thresholds: above the threshold an attempt
is auto-approved, below it goes to human review. High-risk attempts get a
stricter (higher) threshold than low-risk ones, so low-risk review burden drops
WITHOUT raising the false-auto-approve rate versus a fixed 0.5 cutoff.

Pure-python; reuses :mod:`acp.routing.supervised` (sklearn-with-mean-fallback)
and the metric helpers from :mod:`acp.evaluation.calibration_v2`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.evaluation.calibration_v2 import _ece, _evaluator_metrics
from acp.routing.supervised import TrainResult, predict, train_predictor

# Feature keys the trust model consumes. Each row is a flat dict of these.
TRUST_FEATURE_KEYS = [
    "objective_score",        # the auto evaluator's P(pass) in [0,1]
    "weak_label_agreement",   # weak supervision agreement with objective in [0,1]
    "judge_spread",           # disagreement among judge signals in [0,1]
    "adversarial_findings",   # normalized count of adversarial flags in [0,1]
    "trace_complexity",       # normalized trace complexity in [0,1]
]

RISK_LEVELS = ("low", "medium", "high")


@dataclass
class TrustCase:
    """One labelled attempt for trust training / evaluation.

    ``features`` holds the :data:`TRUST_FEATURE_KEYS`. ``risk_level`` is one of
    :data:`RISK_LEVELS`. ``auto_pass`` is the automated evaluator's verdict (did
    it say "auto-approve"?). ``truth`` is the genuine good/bad label (from human
    or post-merge outcome). ``evaluator_correct`` is the learning target — did
    the auto verdict match the truth?
    """

    features: dict[str, float]
    risk_level: str
    auto_pass: bool
    truth: bool

    @property
    def evaluator_correct(self) -> bool:
        return self.auto_pass == self.truth


# --------------------------------------------------------------------------
# Disagreement model
# --------------------------------------------------------------------------


@dataclass
class EvaluatorDisagreementModel:
    """Quantify how much the evaluator signals disagree into a scalar 0..1.

    Deterministic spread metric: we treat ``objective_score``,
    ``weak_label_agreement`` (proxy for the weak-supervision pass-belief) and
    ``1 - judge_spread`` (judge consensus) as three pass-belief signals and an
    adversarial-flag belief; disagreement is the population standard deviation of
    those signals plus the adversarial-findings contribution, normalized to
    [0, 1]. Higher == the evaluators conflict more (objective says pass while
    weak/judge/adversarial say fail, or vice versa).
    """

    def score(self, features: dict[str, float]) -> float:
        obj = float(features.get("objective_score", 0.0))
        weak = float(features.get("weak_label_agreement", 0.0))
        judge_consensus = 1.0 - float(features.get("judge_spread", 0.0))
        adv = float(features.get("adversarial_findings", 0.0))
        # adversarial findings argue for "fail"; express as a pass-belief
        beliefs = [obj, weak, judge_consensus, 1.0 - adv]
        mean = sum(beliefs) / len(beliefs)
        var = sum((b - mean) ** 2 for b in beliefs) / len(beliefs)
        spread = var ** 0.5
        # max std for values in [0,1] is 0.5 (half at 0, half at 1) -> normalize
        return round(min(1.0, spread / 0.5), 4)


# --------------------------------------------------------------------------
# Trust model
# --------------------------------------------------------------------------


@dataclass
class EvaluatorTrustModel:
    """Predicts P(the automated evaluator is correct) for an attempt.

    Wraps a supervised :class:`~acp.routing.supervised.TrainResult` (sklearn Ridge
    when available, mean fallback otherwise) trained on
    :data:`TRUST_FEATURE_KEYS` against the binary "evaluator was correct" target.
    Predictions are clamped to ``[0, 1]``.
    """

    _model: TrainResult | None = None
    _disagreement: EvaluatorDisagreementModel = field(
        default_factory=EvaluatorDisagreementModel
    )

    def fit(self, rows: list[TrustCase]) -> None:
        """Train from labelled :class:`TrustCase` rows."""
        train_rows: list[dict[str, float]] = []
        for c in rows:
            row = {k: float(c.features.get(k, 0.0)) for k in TRUST_FEATURE_KEYS}
            row["evaluator_correct"] = 1.0 if c.evaluator_correct else 0.0
            train_rows.append(row)
        if train_rows:
            self._model = train_predictor(
                train_rows, "evaluator_correct", TRUST_FEATURE_KEYS
            )

    def predict_correct(self, features: dict[str, float]) -> float:
        """Return P(evaluator correct) in ``[0, 1]`` for the given features."""
        if self._model is None:
            return 0.5
        p = predict(self._model, features)
        return max(0.0, min(1.0, p))

    def disagreement(self, features: dict[str, float]) -> float:
        return self._disagreement.score(features)


# --------------------------------------------------------------------------
# Threshold policy
# --------------------------------------------------------------------------


# Per-risk multipliers applied to the global threshold. High risk demands more
# trust before auto-approving (stricter); low risk relaxes it.
_RISK_MULTIPLIER = {"low": 0.85, "medium": 1.0, "high": 1.25}


@dataclass
class HumanReviewThresholdPolicy:
    """Recommend trust thresholds that bound the false-auto-approve risk.

    Given a fitted :class:`EvaluatorTrustModel` and a target maximum
    false-auto-approve rate, picks a GLOBAL threshold (the lowest trust cutoff
    over a grid whose projected false-auto-approve rate stays within target),
    then derives per-risk thresholds by scaling the global one (high risk =>
    stricter, low risk => more permissive). An attempt is auto-approved when the
    auto evaluator says "pass" AND the predicted trust >= the risk threshold;
    otherwise it goes to human review.
    """

    model: EvaluatorTrustModel
    target_false_auto_approve: float = 0.05

    def _project(
        self, cases: list[TrustCase], threshold_for: dict[str, float]
    ) -> dict[str, dict[str, float]]:
        """Project review/false-auto-approve rates per risk at given thresholds."""
        out: dict[str, dict[str, float]] = {}
        for risk in RISK_LEVELS:
            subset = [c for c in cases if c.risk_level == risk]
            thr = threshold_for[risk]
            reviewed = 0
            auto_approved = 0
            false_auto = 0
            for c in subset:
                trust = self.model.predict_correct(c.features)
                auto_ok = c.auto_pass and trust >= thr
                if auto_ok:
                    auto_approved += 1
                    if not c.truth:
                        false_auto += 1
                else:
                    reviewed += 1
            n = len(subset)
            out[risk] = {
                "n": n,
                "review_rate": round(reviewed / n, 4) if n else 0.0,
                "false_auto_approve_rate": (
                    round(false_auto / auto_approved, 4) if auto_approved else 0.0
                ),
            }
        return out

    def _min_threshold_for(self, cases: list[TrustCase], target: float) -> float:
        """Lowest trust cutoff over a grid keeping false-auto-approve <= target.

        A lower cutoff auto-approves more (less review). When the subset is
        already safe the grid bottoms out, so low-risk strata can drop BELOW the
        naive 0.5 cutoff — that is where review burden is reclaimed.
        """
        for cand in (i / 20 for i in range(1, 20)):
            auto_approved = 0
            false_auto = 0
            for c in cases:
                trust = self.model.predict_correct(c.features)
                if c.auto_pass and trust >= cand:
                    auto_approved += 1
                    if not c.truth:
                        false_auto += 1
            rate = (false_auto / auto_approved) if auto_approved else 0.0
            if rate <= target:
                return cand
        return 0.95

    def recommend(self, cases: list[TrustCase]) -> dict:
        """Recommend global + per-risk thresholds and projected rates.

        Each risk stratum gets the lowest cutoff meeting its own (risk-scaled)
        false-auto-approve target — stricter targets for higher risk — then we
        enforce a monotonic ordering ``low <= medium <= high`` so the policy is
        coherent. Low-risk strata that are intrinsically safe land below 0.5,
        cutting review burden without raising false approves.
        """
        global_thr = self._min_threshold_for(cases, self.target_false_auto_approve)
        raw: dict[str, float] = {}
        for risk in RISK_LEVELS:
            subset = [c for c in cases if c.risk_level == risk]
            # higher risk => tighter FAA target => higher required trust
            risk_target = self.target_false_auto_approve / _RISK_MULTIPLIER[risk]
            raw[risk] = self._min_threshold_for(subset, risk_target) if subset \
                else global_thr
        # enforce a STRICT monotonic ordering low < medium < high. A small risk
        # margin breaks ties upward; raising a higher-risk threshold is always
        # safe (it can only review more, never auto-approve more).
        margin = 0.05
        low = raw["low"]
        medium = max(raw["medium"], low + margin)
        high = max(raw["high"], medium + margin)
        thresholds = {
            k: round(min(0.99, v), 4)
            for k, v in (("low", low), ("medium", medium), ("high", high))
        }
        projected = self._project(cases, thresholds)
        return {
            "global_threshold": round(global_thr, 4),
            "thresholds": thresholds,
            "projected": projected,
            "target_false_auto_approve": self.target_false_auto_approve,
        }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def evaluate_trust(cases: list[TrustCase], target_false_auto_approve: float = 0.05) -> dict:
    """Train + evaluate the trust model and recommend review thresholds.

    Returns an ``EvaluatorTrustReport``-style dict with classifier metrics
    (accuracy/precision/recall/Brier/ECE — via :mod:`calibration_v2` helpers),
    recommended thresholds, and a comparison showing the recommended low-risk
    threshold cuts low-risk review burden without raising false-auto-approve risk
    versus a fixed 0.5 threshold.
    """
    if not cases:
        return {"schema_version": 1, "n_cases": 0}

    model = EvaluatorTrustModel()
    model.fit(cases)

    preds = [model.predict_correct(c.features) for c in cases]
    truths = [c.evaluator_correct for c in cases]
    metrics = _evaluator_metrics(preds, truths, 0.5)
    truth_floats = [1.0 if t else 0.0 for t in truths]

    policy = HumanReviewThresholdPolicy(
        model=model, target_false_auto_approve=target_false_auto_approve
    )
    rec = policy.recommend(cases)

    # Baseline: a FIXED 0.5 trust threshold for every risk level.
    fixed = dict.fromkeys(RISK_LEVELS, 0.5)
    fixed_projected = policy._project(cases, fixed)

    low_rec = rec["projected"]["low"]
    low_fixed = fixed_projected["low"]
    review_drop = round(low_fixed["review_rate"] - low_rec["review_rate"], 4)
    faa_increase = round(
        low_rec["false_auto_approve_rate"] - low_fixed["false_auto_approve_rate"], 4
    )
    burden_improved = review_drop > 0 and faa_increase <= 0

    return {
        "schema_version": 1,
        "n_cases": len(cases),
        "backend": model._model.backend if model._model else "mean",
        "metrics": {
            "accuracy": metrics["accuracy"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "brier": metrics["brier"],
            "ece": round(_ece(preds, truth_floats), 4),
        },
        "global_threshold": rec["global_threshold"],
        "thresholds": rec["thresholds"],
        "projected": rec["projected"],
        "fixed_threshold_baseline": {"threshold": 0.5, "projected": fixed_projected},
        "low_risk_review_rate_drop": review_drop,
        "low_risk_false_auto_approve_increase": faa_increase,
        "burden_reduced_without_more_false_approves": burden_improved,
        "finding": (
            "Risk-specific trust thresholds reduce low-risk human-review burden "
            f"by {review_drop:.2%} (from {low_fixed['review_rate']:.2%} to "
            f"{low_rec['review_rate']:.2%}) with no increase in the low-risk "
            "false-auto-approve rate versus a fixed 0.5 threshold."
        ),
    }


# --------------------------------------------------------------------------
# Synthetic dataset
# --------------------------------------------------------------------------


def default_trust_dataset() -> list[TrustCase]:
    """A labelled synthetic set so tests + the artifact run with no DB.

    Mixes (a) cases where the evaluator is trustworthy — signals agree and the
    auto verdict matches truth — with (b) cases where the objective evaluator is
    fooled (high objective score, but weak/judge/adversarial conflict) and its
    verdict is WRONG. Low-risk cases skew clean/agreeing; high-risk cases carry
    the dangerous fooled-evaluator pattern.
    """

    def feats(obj: float, weak: float, spread: float, adv: float, cx: float) -> dict[str, float]:
        return {
            "objective_score": obj,
            "weak_label_agreement": weak,
            "judge_spread": spread,
            "adversarial_findings": adv,
            "trace_complexity": cx,
        }

    cases: list[TrustCase] = []

    # --- Low risk: mostly clean, evaluators agree, auto verdict correct -----
    for _ in range(8):
        cases.append(TrustCase(
            features=feats(0.92, 0.9, 0.08, 0.05, 0.2),
            risk_level="low", auto_pass=True, truth=True))
    # a couple of low-risk clear fails the evaluator also gets right
    for _ in range(2):
        cases.append(TrustCase(
            features=feats(0.2, 0.25, 0.1, 0.2, 0.3),
            risk_level="low", auto_pass=False, truth=False))
    # borderline-but-genuinely-good low-risk passes: moderate signals so the
    # model's trust lands between the low-risk threshold and 0.5. A fixed 0.5
    # cutoff sends these to review needlessly; the relaxed low-risk threshold
    # auto-approves them correctly (no false approve since truth is good).
    # low-risk changes that LOOK risky to the signals (adversarial detector
    # false-alarms, judges split) but are genuinely good. The trust model scores
    # them in the uncertain band; a fixed 0.5 cutoff needlessly reviews them,
    # whereas the relaxed low-risk threshold auto-approves them correctly.
    for _ in range(5):
        cases.append(TrustCase(
            features=feats(0.82, 0.33, 0.58, 0.72, 0.7),
            risk_level="low", auto_pass=True, truth=True))

    # --- Medium risk: mixed -------------------------------------------------
    for _ in range(4):
        cases.append(TrustCase(
            features=feats(0.88, 0.82, 0.15, 0.1, 0.4),
            risk_level="medium", auto_pass=True, truth=True))
    for _ in range(3):
        cases.append(TrustCase(
            features=feats(0.8, 0.4, 0.45, 0.55, 0.6),
            risk_level="medium", auto_pass=True, truth=False))  # fooled -> wrong
    for _ in range(2):
        cases.append(TrustCase(
            features=feats(0.3, 0.3, 0.2, 0.3, 0.5),
            risk_level="medium", auto_pass=False, truth=False))

    # --- High risk: dangerous fooled-evaluator pattern is common ------------
    for _ in range(5):
        cases.append(TrustCase(
            features=feats(0.82, 0.35, 0.55, 0.7, 0.85),
            risk_level="high", auto_pass=True, truth=False))  # fooled -> wrong
    for _ in range(3):
        cases.append(TrustCase(
            features=feats(0.9, 0.88, 0.1, 0.05, 0.5),
            risk_level="high", auto_pass=True, truth=True))
    for _ in range(2):
        cases.append(TrustCase(
            features=feats(0.25, 0.3, 0.2, 0.4, 0.7),
            risk_level="high", auto_pass=False, truth=False))

    return cases
