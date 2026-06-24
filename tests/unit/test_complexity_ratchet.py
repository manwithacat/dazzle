"""Framework structural-fitness (A2) — the complexity ratchet.

Drift gate (same posture as test_api_surface_drift): a touched file may not drop its radon
MI rank, a new file may not land at C, and a new/changed function may not exceed the CC
ceiling. Improve a file and regenerate with `dazzle fitness code --write-baseline` to
re-tighten the one-way valve. NEVER run `ruff format` over the .json baseline (the v0.83.16
lesson — it injects a trailing comma and breaks JSON parsing).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.fitness.code import build_complexity_baseline, compare_complexity

pytestmark = pytest.mark.gate

_BASELINE = Path("tests/unit/fixtures/complexity_baseline.json")
_SRC = Path("src/dazzle")


def test_baseline_is_valid_json() -> None:
    data = json.loads(_BASELINE.read_text())
    assert isinstance(data, dict) and data


def test_current_tree_does_not_regress_against_baseline() -> None:
    baseline = json.loads(_BASELINE.read_text())
    current = build_complexity_baseline(_SRC)
    violations = compare_complexity(baseline, current)
    assert violations == [], (
        f"{len(violations)} structural-complexity regression(s) — refactor, or "
        f"`dazzle fitness code --write-baseline` if the increase is justified:\n  "
        + "\n  ".join(violations[:20])
    )


def test_compare_flags_mi_rank_drop() -> None:
    base = {"a.py": {"mi_rank": "B", "functions": {}}}
    worse = {"a.py": {"mi_rank": "C", "functions": {}}}
    v = compare_complexity(base, worse)
    assert any("a.py" in s and "MI rank" in s for s in v), v


def test_compare_flags_new_high_cc_function() -> None:
    base = {"a.py": {"mi_rank": "B", "functions": {"f": 5}}}
    worse = {"a.py": {"mi_rank": "B", "functions": {"f": 5, "g": 20}}}
    v = compare_complexity(base, worse, cc_ceiling=15)
    assert any("g" in s and "complexity 20" in s for s in v), v


def test_compare_flags_new_c_rank_file() -> None:
    v = compare_complexity({}, {"new.py": {"mi_rank": "C", "functions": {}}})
    assert any("new.py" in s and "new file at MI rank C" in s for s in v), v


def test_clean_when_unchanged() -> None:
    base = {"a.py": {"mi_rank": "B", "functions": {"f": 5}}}
    assert compare_complexity(base, dict(base)) == []
