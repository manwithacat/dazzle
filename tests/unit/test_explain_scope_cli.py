"""#1448: `dazzle db explain-scope` traceability oracle."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.db import db_app

runner = CliRunner()

_TOML = """[project]
name = "polytest"
version = "0.1.0"
root = "polytest_core"

[modules]
paths = ["./dsl"]

[stack]
name = "dnr"
"""

_DSL = """module polytest_core
app polytest "Poly Test"

entity Cohort "Cohort":
  id: uuid pk
  uploaded_by: uuid

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort] required

  permit:
    read: role(teacher)

  scope:
    read: target[Cohort].uploaded_by = current_user
      as: teacher
"""


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "dazzle.toml").write_text(_TOML)
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "domain.dsl").write_text(_DSL)
    return tmp_path


def test_explain_scope_prints_compiled_forms(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    monkeypatch.chdir(project)
    result = runner.invoke(db_app, ["explain-scope", "AIJob", "read"])
    assert result.exit_code == 0, result.output
    assert "target_type" in result.output
    assert "RLS" in result.output or "app-layer" in result.output


def test_explain_scope_unknown_entity_exits_nonzero(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    monkeypatch.chdir(project)
    result = runner.invoke(db_app, ["explain-scope", "Nope", "read"])
    assert result.exit_code == 1
