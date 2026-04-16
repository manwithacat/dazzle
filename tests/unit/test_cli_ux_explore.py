"""Tests for the ``dazzle ux explore`` CLI command (#789)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.ux import ux_app

runner = CliRunner()


def _write_min_manifest(root: Path, name: str = "downstream") -> None:
    (root / "dazzle.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n\n[modules]\npaths = ["./dsl"]\n'
    )


class TestExploreCommand:
    def test_missing_persona_and_all_personas_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(ux_app, ["explore", "--app-dir", str(tmp_path)])
        assert result.exit_code == 2
        assert "--persona or --all-personas" in result.output

    def test_unknown_strategy_rejected(self, tmp_path: Path) -> None:
        result = runner.invoke(
            ux_app,
            ["explore", "--persona", "user", "--strategy", "wat", "--app-dir", str(tmp_path)],
        )
        assert result.exit_code == 2
        assert "Unknown strategy" in result.output

    def test_missing_app_dir_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(
            ux_app,
            [
                "explore",
                "--persona",
                "user",
                "--app-dir",
                str(tmp_path / "does_not_exist"),
            ],
        )
        assert result.exit_code == 2
        assert "does not exist" in result.output

    def test_prepares_single_run(self, tmp_path: Path) -> None:
        _write_min_manifest(tmp_path)
        result = runner.invoke(
            ux_app,
            ["explore", "--persona", "user", "--app-dir", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        assert "Prepared 1 explore run" in result.output
        assert "persona=user" in result.output
        # State dir lives under tmp_path because dazzle.toml anchors it there
        assert "dev_docs/ux_cycle_runs" in result.output

    def test_cycles_parameter_creates_multiple_runs(self, tmp_path: Path) -> None:
        _write_min_manifest(tmp_path)
        result = runner.invoke(
            ux_app,
            [
                "explore",
                "--persona",
                "user",
                "--cycles",
                "3",
                "--app-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Prepared 3 explore run" in result.output

    def test_json_output_structured(self, tmp_path: Path) -> None:
        _write_min_manifest(tmp_path)
        result = runner.invoke(
            ux_app,
            [
                "explore",
                "--persona",
                "user",
                "--strategy",
                "persona_journey",
                "--json",
                "--app-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        # Find JSON block in output
        payload = json.loads(result.output.strip())
        assert "runs" in payload
        assert len(payload["runs"]) == 1
        run = payload["runs"][0]
        assert run["persona_id"] == "user"
        assert run["strategy"] == "persona_journey"
        assert "findings_path" in run
        assert "state_dir" in run

    def test_all_personas_without_appspec_exits_cleanly(self, tmp_path: Path) -> None:
        """--all-personas requires a loadable AppSpec. Malformed project exits 2."""
        _write_min_manifest(tmp_path)
        result = runner.invoke(
            ux_app,
            ["explore", "--all-personas", "--app-dir", str(tmp_path)],
        )
        # No DSL files → load_project_appspec fails → exit 2
        assert result.exit_code == 2
