"""Validation for `display: comparison` ranked-league regions (#1470).

A comparison region requires a `rank_by` metric. In group mode it must name an
aggregate; in entity-row mode it must name a numeric field on the source. Outlier
config must be well-formed (sigma_k > 0; threshold needs ≥1 bound).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_comparison_regions

_ENTITY = """module t
app T "T"

entity Sale "Sale":
  id: uuid pk
  region: str(40)
  amount: decimal(12,2)

workspace w "W":
"""


def _appspec(region_dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(_ENTITY + region_dsl)
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
