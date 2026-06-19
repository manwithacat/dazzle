"""Framework structural-fitness (A1) — churn×complexity hotspot ranking."""

from __future__ import annotations

from pathlib import Path

from dazzle.fitness.code import compute_complexity, rank_hotspots

_SRC = Path("src/dazzle")


def test_compute_complexity_on_a_known_module() -> None:
    cx = compute_complexity(_SRC)
    key = next(k for k in cx if k.endswith("back/runtime/route_overrides.py"))
    assert cx[key]["mi_rank"] in ("A", "B", "C")
    assert cx[key]["max_cc"] >= 1
    assert isinstance(cx[key]["functions"], dict) and cx[key]["functions"]


def test_keys_are_dazzle_relative() -> None:
    cx = compute_complexity(_SRC)
    assert all(k.startswith("dazzle/") and k.endswith(".py") for k in cx)


def test_rank_hotspots_orders_by_churn_times_complexity() -> None:
    complexity = {"a.py": {"mi": 30.0, "mi_rank": "C"}, "b.py": {"mi": 90.0, "mi_rank": "A"}}
    churn = {"a.py": 2, "b.py": 50}
    ranked = rank_hotspots(complexity, churn)
    # a.py: 2*(100-30)=140 ; b.py: 50*(100-90)=500 → b first
    assert ranked[0][0] == "b.py" and ranked[0][1] == 500.0
    assert ranked[1][0] == "a.py"


def test_rank_hotspots_zero_churn_scores_zero() -> None:
    ranked = rank_hotspots({"x.py": {"mi": 10.0, "mi_rank": "C"}}, {})
    assert ranked[0] == ("x.py", 0.0, 0, "C")
