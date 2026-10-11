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
