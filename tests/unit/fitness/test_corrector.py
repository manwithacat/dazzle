"""Tests for corrector (v1 task 17).

Two-gate routing (low_confidence/maturity/disambiguation) plus
alternative-generation that mechanically flags disambiguation when the
primary and alternative fixes diverge materially.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

from dazzle.fitness.corrector import (
    Fix,
    generate_fix,
    materially_same,
    route_finding,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _finding(**overrides: Any) -> Finding:
    base: dict[str, Any] = {
        "id": "F1",
        "created": datetime(2026, 4, 13, tzinfo=UTC),
        "run_id": "r",
        "cycle": None,
        "axis": "conformance",
        "locus": "lifecycle",
        "severity": "high",
        "persona": "a",
        "capability_ref": "c",
        "expected": "x",
        "observed": "y",
        "evidence_embedded": EvidenceEmbedded({}, [], []),
        "disambiguation": False,
        "low_confidence": False,
        "status": "PROPOSED",
        "route": "hard",
        "fix_commit": None,
        "alternative_fix": None,
    }
    base.update(overrides)
    return Finding(**base)


def test_low_confidence_always_goes_soft() -> None:
    f = _finding(low_confidence=True)
    assert route_finding(f, maturity="mvp") == "soft"


def test_stable_maturity_always_goes_soft() -> None:
    f = _finding()
    assert route_finding(f, maturity="stable") == "soft"


def test_disambiguation_goes_soft() -> None:
    f = _finding(disambiguation=True)
    assert route_finding(f, maturity="mvp") == "soft"


def test_mvp_clean_finding_goes_hard() -> None:
    f = _finding()
    assert route_finding(f, maturity="mvp") == "hard"


def test_spec_stale_goes_soft_regardless() -> None:
    f = _finding(locus="spec_stale")
    assert route_finding(f, maturity="mvp") == "soft"


def test_materially_same_identical_fixes() -> None:
    a = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x\n-y\n")
    b = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x\n-y\n")
    assert materially_same(a, b) is True


def test_materially_same_different_files() -> None:
    a = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x")
    b = Fix(touched_files=["src/b.py"], summary="refactor", diff="+x")
    assert materially_same(a, b) is False


def test_generate_fix_flags_disambiguation_when_alternatives_diverge() -> None:
    fake_llm = Mock()
    fake_llm.complete.side_effect = [
        '{"touched_files": ["src/a.py"], "summary": "fix route", "diff": "+a"}',
        '{"touched_files": ["src/b.py"], "summary": "fix template", "diff": "+b"}',
    ]
    f = _finding()
    primary, alternative, updated = generate_fix(f, llm=fake_llm)

    assert primary is not None
    assert primary.touched_files == ["src/a.py"]
    assert alternative is not None
    assert alternative.touched_files == ["src/b.py"]
    assert updated.disambiguation is True
    assert updated.alternative_fix == "fix template"
    assert fake_llm.complete.call_count == 2
