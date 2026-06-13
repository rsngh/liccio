"""Auto-referee: mutation_score, debate parse/fail-closed, referee abstain/accept gates."""

from __future__ import annotations

from pathlib import Path

from acp.verification.auto_referee import referee
from acp.verification.battery_mutation import sensitivity_weights
from acp.verification.debate import debate_verdict
from acp.verification.repair_battery import RepairBattery

_BUGGY = "def add(a, b):\n    return a - b\n"
_GOLD = "def add(a, b):\n    return a + b\n"
_PUBLIC = "from m import add\n\ndef test_pub():\n    assert add(1, 1) == 2\n"
_DISC = "from m import add\n\ndef test_d():\n    assert add(2, 1) == 3\n"   # fails on buggy
_GUARD = "from m import add\n\ndef test_g():\n    assert add(0, 0) == 0\n"  # passes on buggy


class _StubMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 10})()


class _StubClient:
    """Scripts proposer/critic/judge replies in call order."""
    def __init__(self, replies):
        self._replies = list(replies)
        self.messages = self

    def create(self, **_kw):
        return _StubMsg(self._replies.pop(0) if self._replies else "{}")


def _battery(*, valid=True, mutation_score=0.9, n_disc=4) -> RepairBattery:
    bp = [False] * n_disc + [True, True]      # n_disc discriminating + 2 guard
    return RepairBattery(checks=[("pbt", _DISC)] * n_disc + [("example", _GUARD)] * 2,
                         baseline_pass=bp, public_test=_PUBLIC, module_path="m.py", extra_files={},
                         valid=valid, check_weights=[1.0] * (n_disc + 2),
                         mutation_info={"mutation_score": mutation_score, "n_mutants": 10})


def test_mutation_score_reported(tmp_path: Path) -> None:
    checks = [("ex", _DISC), ("ex", _GUARD)]
    _w, info = sensitivity_weights(_BUGGY, checks, [False, True], module_path="m.py",
                                   extra_files={}, root=tmp_path, spans=None, cap=8)
    assert "mutation_score" in info and 0.0 <= info["mutation_score"] <= 1.0
    assert info["mutation_score"] > 0.0   # a-b->a+b mutant flips the discriminating check


def test_debate_parses_and_fail_closed() -> None:
    spec = type("S", (), {"issue_text": "add must be commutative"})()
    client = _StubClient(["defence...", "NO DEFECT FOUND",
                          '{"accept": true, "confidence": 0.9, "rationale": "sound"}'])
    v = debate_verdict(spec, _GOLD, client=client, check_summary="all pass")
    assert v.accept and v.confidence == 0.9
    assert not debate_verdict(spec, _GOLD, client=None, check_summary="x").accept  # no-client=reject


def test_debate_rejects_on_concrete_objection() -> None:
    spec = type("S", (), {"issue_text": "add must be commutative"})()
    # critic names a defect; judge says accept but low confidence -> safety override rejects
    client = _StubClient(["defence", "FAILS on add(2,1): returns 1 not 3",
                          '{"accept": true, "confidence": 0.4, "rationale": "maybe"}'])
    assert not debate_verdict(spec, _BUGGY, client=client, check_summary="disc fail").accept


def test_referee_abstains_on_weak_battery(tmp_path: Path) -> None:
    spec = type("S", (), {"issue_text": "x", "public_test": _PUBLIC, "module_path": "m.py"})()
    weak = _battery(mutation_score=0.1)          # below floor -> not trusted
    rv = referee(weak, _GOLD, workspace_root=tmp_path, candidate_id="g", diff=None,
                 client=_StubClient(["d", "NO DEFECT FOUND", '{"accept":true}']),
                 spec=spec, mutation_floor=0.5)
    assert not rv.accept and not rv.mutation_validated and "weak battery" in rv.reason


def test_referee_invalid_battery_abstains(tmp_path: Path) -> None:
    spec = type("S", (), {"issue_text": "x", "public_test": _PUBLIC, "module_path": "m.py"})()
    rv = referee(_battery(valid=False), _GOLD, workspace_root=tmp_path, candidate_id="g", diff=None,
                 client=_StubClient([]), spec=spec)
    assert not rv.accept and not rv.mutation_validated


def test_referee_debate_is_decider_when_mutation_validated(tmp_path: Path) -> None:
    spec = type("S", (), {"issue_text": "add must be commutative", "public_test": _PUBLIC,
                          "module_path": "m.py"})()
    bat = _battery(mutation_score=0.9)        # trustworthy battery
    # debate ACCEPTS (critic finds nothing) -> referee accepts (debate is the decider)
    yes = _StubClient(["defence", "NO DEFECT FOUND", '{"accept": true, "confidence": 0.9}'])
    assert referee(bat, _GOLD, workspace_root=tmp_path / "a", candidate_id="g", diff=None,
                   client=yes, spec=spec).accept
    # same trustworthy battery, but debate REJECTS (critic names a defect) -> referee rejects
    no = _StubClient(["defence", "FAILS on add(2,1)=1", '{"accept": false, "confidence": 0.8}'])
    assert not referee(bat, _GOLD, workspace_root=tmp_path / "b", candidate_id="g", diff=None,
                       client=no, spec=spec).accept
