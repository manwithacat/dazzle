from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_insight_summaries

_HEADER = """module t
app T "T"

entity Alert "Alert":
  id: uuid pk
  team: str(40)

workspace w "W":
"""


def _appspec(region_dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(_HEADER + region_dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


def test_requires_group_by(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_GROUP_BY_REQUIRED" in e for e in errors)


def test_requires_aggregate(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: team
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_AGGREGATE_REQUIRED" in e for e in errors)


def test_rejects_multi_dim(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: [team, team]
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_SINGLE_DIM_ONLY" in e for e in errors)


def test_valid(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: team
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert errors == []
