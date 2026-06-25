from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_rag_decorators

_HEADER = """module t
app T "T"

entity System "System":
  id: uuid pk
  name: str(40)
  error_rate: decimal(5,2)

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


_BANDS = """    tone_bands:
      - at: 5
        tone: destructive
      - at: 0
        tone: positive
"""


def test_requires_list_display(tmp_path: Path) -> None:
    dsl = (
        """  r:
    source: System
    display: grid
    rag_on: error_rate
"""
        + _BANDS
    )
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_DISPLAY" in e for e in errors)


def test_must_be_numeric(tmp_path: Path) -> None:
    dsl = (
        """  r:
    source: System
    display: list
    rag_on: name
"""
        + _BANDS
    )
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_NOT_NUMERIC" in e for e in errors)


def test_requires_bands(tmp_path: Path) -> None:
    dsl = """  r:
    source: System
    display: list
    rag_on: error_rate
"""
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_BANDS_REQUIRED" in e for e in errors)


def test_valid(tmp_path: Path) -> None:
    dsl = (
        """  r:
    source: System
    display: list
    rag_on: error_rate
"""
        + _BANDS
    )
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert errors == []
