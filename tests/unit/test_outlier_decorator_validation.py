from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_outlier_decorators

_HEADER = """module t
app T "T"

entity System "System":
  id: uuid pk
  name: str(40)
  response_time_ms: int

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


def test_outlier_on_requires_list_display(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: bar_chart
    group_by: name
    aggregate:
      count: count(System)
    outlier_on: response_time_ms
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert any("E_OUTLIER_DISPLAY" in e for e in errors)


def test_outlier_on_must_be_numeric(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: list
    outlier_on: name
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert any("E_OUTLIER_NOT_NUMERIC" in e for e in errors)


def test_outlier_on_valid(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: list
    outlier_on: response_time_ms
    outlier_method: iqr
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert errors == []
