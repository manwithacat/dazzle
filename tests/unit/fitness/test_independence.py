from dazzle.fitness.independence import (
    IndependenceReport,
    measure_independence,
)
from dazzle.fitness.spec_extractor import Capability


def _caps(*pairs: tuple[str, str]) -> list[Capability]:
    return [Capability(capability=c, persona=p) for c, p in pairs]


def test_perfect_overlap_flags_degraded() -> None:
    a = _caps(("triage", "agent"), ("resolve", "agent"))
    b = _caps(("triage", "agent"), ("resolve", "agent"))
    report = measure_independence(a, b, threshold=0.85)
    assert isinstance(report, IndependenceReport)
    assert report.jaccard == 1.0
    assert report.degraded is True


def test_zero_overlap_is_maximally_independent() -> None:
    a = _caps(("triage", "agent"))
    b = _caps(("checkout", "customer"))
    report = measure_independence(a, b, threshold=0.85)
    assert report.jaccard == 0.0
    assert report.degraded is False


def test_partial_overlap_below_threshold() -> None:
    a = _caps(("triage", "agent"), ("resolve", "agent"), ("escalate", "agent"))
    b = _caps(("triage", "agent"), ("reject", "agent"), ("reopen", "agent"))
    report = measure_independence(a, b, threshold=0.85)
    assert 0.0 < report.jaccard < 0.85
    assert report.degraded is False
    assert report.shared == [("triage", "agent")]


def test_empty_inputs_are_insufficient_data() -> None:
    report = measure_independence([], [], threshold=0.85)
    assert report.jaccard == 0.0
    assert report.insufficient_data is True
