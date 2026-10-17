"""Validation for `display: comparison` ranked-league regions (#1470).

A comparison region requires a `rank_by` metric. In group mode it must name an
aggregate; in entity-row mode it must name a numeric field on the source. Outlier
config must be well-formed (sigma_k > 0; threshold needs ≥1 bound).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import (
    validate_comparison_regions,
    validate_pivot_measures,
    validate_region_filter_aggregate_reach,
)

_ENTITY = """module t
app T "T"

entity Sale "Sale":
  id: uuid pk
  region: str(40)
  amount: decimal(12,2)

workspace w "W":
"""


def _appspec(region_dsl: str, tmp_path: Path, entities: str = _ENTITY):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(entities + region_dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


def test_missing_rank_by(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert any("E_COMPARISON_RANK_BY_REQUIRED" in e for e in errors)


def test_group_mode_rank_by_unknown(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: nonexistent
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert any("E_COMPARISON_RANK_BY_UNKNOWN" in e for e in errors)


def test_entity_row_rank_by_not_numeric(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    rank_by: region
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert any("E_COMPARISON_METRIC_NOT_NUMERIC" in e for e in errors)


def test_group_mode_valid(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: total
    outlier_method: iqr
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert errors == []


def test_entity_row_valid(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    rank_by: amount
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert errors == []


def test_sigma_k_non_positive_rejected(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: total
    outlier_method: sigma:0
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert any("E_COMPARISON_OUTLIER_INVALID" in e for e in errors)


def test_threshold_without_bounds_rejected(tmp_path: Path) -> None:
    dsl = """  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: total
    outlier_method: threshold
"""
    errors, _ = validate_comparison_regions(_appspec(dsl, tmp_path))
    assert any("E_COMPARISON_OUTLIER_INVALID" in e for e in errors)


@pytest.mark.parametrize(
    ("aggregate", "warns"),
    [
        ("count(Refund)", True),  # cross-entity: region filter can't reach it
        ("count(Refund where amount > 0)", False),  # author narrowed it explicitly
        ("count(Sale)", False),  # same-entity: runtime composes the filter (#1773)
    ],
)
def test_region_filter_aggregate_reach(tmp_path: Path, aggregate: str, warns: bool) -> None:
    entities = _ENTITY.replace(
        "workspace w",
        'entity Refund "Refund":\n  id: uuid pk\n  amount: decimal(12,2)\n\nworkspace w',
    )
    dsl = f"""  league:
    source: Sale
    display: comparison
    filter: amount > 100
    group_by: region
    aggregate:
      total: {aggregate}
    rank_by: total
"""
    _, warnings = validate_region_filter_aggregate_reach(_appspec(dsl, tmp_path, entities))
    assert any("W_REGION_FILTER_NOT_ON_AGGREGATE" in w for w in warnings) is warns


@pytest.mark.parametrize(
    ("measures", "code"),
    [
        (["total: sum(amount)", "mean: avg(amount)", "share: round(mean / total * 100)"], None),
        (["n: count(Sale)", "refunds: count(Refund)"], "E_PIVOT_MEASURE_CROSS_ENTITY"),
        (
            ["big: sum(amount where amount > 100)", "small: sum(amount where amount < 10)"],
            "E_PIVOT_MEASURE_WHERE_MISMATCH",
        ),
        (["n: count(Sale where region = current_bucket)"], "E_PIVOT_MEASURE_UNSUPPORTED"),
        (["n: count(Sale window week_from_monday on sold_at)"], "E_PIVOT_MEASURE_UNSUPPORTED"),
    ],
)
def test_pivot_measures(tmp_path: Path, measures: list[str], code: str | None) -> None:
    """#1800: pivot measures are any count/sum/avg/min/max over the source sharing one where."""
    entities = _ENTITY.replace(
        "  amount: decimal(12,2)\n",
        "  amount: decimal(12,2)\n  channel: str(20)\n  sold_at: datetime\n",
        1,
    ).replace(
        "workspace w",
        'entity Refund "Refund":\n  id: uuid pk\n  amount: decimal(12,2)\n\nworkspace w',
    )
    lines = "\n".join(f"      {m}" for m in measures)
    dsl = f"""  pivot:
    source: Sale
    display: pivot_table
    group_by: [region, channel]
    aggregate:
{lines}
"""
    errors, _ = validate_pivot_measures(_appspec(dsl, tmp_path, entities))
    if code is None:
        assert errors == []
    else:
        assert any(code in e for e in errors), errors
