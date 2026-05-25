"""Tests for tooling-file scaffolding shipped with new and existing projects."""

from __future__ import annotations

import tomllib
from pathlib import Path

from dazzle.core.init_impl import init_project
from dazzle.quality.bootstrap import quality_bootstrap


def _read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def test_init_project_writes_tooling_files(tmp_path: Path) -> None:
    target = tmp_path / "myproj"
    init_project(target, project_name="myproj", no_llm=True, no_git=True)

    assert (target / "pyproject.toml").exists()
    assert (target / "pyrightconfig.json").exists()
    assert (target / ".pre-commit-config.yaml").exists()

    cfg = _read_toml(target / "pyproject.toml")
    assert "tool" in cfg and "ruff" in cfg["tool"]
    select = cfg["tool"]["ruff"]["lint"]["select"]
    assert "TRY" in select
    assert "BLE" in select
    assert "S" in select


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    """Running bootstrap twice produces identical files."""
    target = tmp_path / "existing"
    target.mkdir()
    quality_bootstrap(target)
    first = (target / "pyproject.toml").read_text()
    quality_bootstrap(target)
    second = (target / "pyproject.toml").read_text()
    assert first == second


def test_bootstrap_preserves_unrelated_tables(tmp_path: Path) -> None:
    """Existing [project] / [tool.poetry] / etc. survive a bootstrap."""
    target = tmp_path / "existing"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.2.3"\n\n[tool.poetry]\nfoo = "bar"\n'
    )
    quality_bootstrap(target)
    cfg = _read_toml(target / "pyproject.toml")
    assert cfg["project"]["name"] == "myapp"
    assert cfg["project"]["version"] == "1.2.3"
    assert cfg["tool"]["poetry"]["foo"] == "bar"
    assert "ruff" in cfg["tool"]


def test_bootstrap_replaces_managed_ruff_table(tmp_path: Path) -> None:
    """If [tool.ruff] already exists, it is replaced (we own it)."""
    target = tmp_path / "existing"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 80\n[tool.ruff.lint]\nselect = ["E"]\n'
    )
    quality_bootstrap(target)
    cfg = _read_toml(target / "pyproject.toml")
    assert cfg["tool"]["ruff"]["line-length"] == 100
    assert "TRY" in cfg["tool"]["ruff"]["lint"]["select"]
