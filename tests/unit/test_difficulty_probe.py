# ruff: noqa: E501
"""Difficulty probe — offline unit tests (no network): feature extraction, separable fit, routing."""

from __future__ import annotations

from acp.routing.difficulty_probe import FEATURE_NAMES, DifficultyProbe, features


def test_features_flag_feature_add_and_package() -> None:
    x = features(issue_title="Add running_statistics recipe", issue_body="",
                 module_src="def a():\n    pass\n", test_src="x" * 100, n_extra_files=2)
    assert len(x) == len(FEATURE_NAMES)
    assert x[FEATURE_NAMES.index("is_feature_add")] == 1.0
    assert x[FEATURE_NAMES.index("is_package")] == 1.0
    y = features(issue_title="fix off-by-one in slice", issue_body="", module_src="def a():\n    pass\n",
                 test_src="x" * 100, n_extra_files=0)
    assert y[FEATURE_NAMES.index("is_feature_add")] == 0.0
    assert y[FEATURE_NAMES.index("is_package")] == 0.0


def test_probe_learns_a_separable_signal_and_routes() -> None:
    # easy = tiny module, fix wording, no siblings (cheap rung succeeds, label 0);
    # hard = big package feature-add (cheap rung doomed, label 1)
    easy = features(issue_title="fix bug", issue_body="", module_src="def a():\n    return 1\n",
                    test_src="assert True\n", n_extra_files=0)
    hard = features(issue_title="add new feature", issue_body="", module_src="def a():\n    pass\n" * 400,
                    test_src="y" * 8000, n_extra_files=4)
    probe = DifficultyProbe().fit([easy, hard] * 8, [0, 1] * 8)
    assert probe.predict(hard) > 0.5 > probe.predict(easy)
    assert probe.start_rung(hard, threshold=0.5) == 1   # skip the cheap rung on the doomed task
    assert probe.start_rung(easy, threshold=0.5) == 0   # keep it on the easy one


def test_untrained_probe_is_neutral_and_keeps_cheap_rung() -> None:
    probe = DifficultyProbe()  # all-zero weights -> p=0.5 everywhere
    x = features(issue_title="x", issue_body="", module_src="def a():\n    pass\n", test_src="t\n", n_extra_files=0)
    assert abs(probe.predict(x) - 0.5) < 1e-9
    assert probe.start_rung(x, threshold=0.85) == 0  # never skip without evidence
