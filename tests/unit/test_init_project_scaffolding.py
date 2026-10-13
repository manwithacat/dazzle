"""Tests for tooling-file scaffolding shipped with new and existing projects."""

from __future__ import annotations

import tomllib
from pathlib import Path

from dazzle.core.init_impl import init_project


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
