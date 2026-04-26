"""Tests for the v0.61.40 ``dazzle theme list`` CLI subcommand
(#design-system Phase B Patch 3).

Subcommand wraps the v0.61.39 ``app_theme_registry`` — these tests
verify the user-facing surface (filters, exit codes, table output,
project-local discovery via ``--project-root``).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.theme import theme_app

runner = CliRunner()


# ────────────────────── default behaviour ────────────────────────


class TestListDefault:
    def test_lists_all_three_shipped_themes(self) -> None:
        result = runner.invoke(theme_app, ["--project-root", "/tmp"])
        assert result.exit_code == 0, result.output
        assert "linear-dark" in result.output
        assert "paper" in result.output
        assert "stripe" in result.output
        # Footer reports the count
        assert "3 theme(s)" in result.output

    def test_table_header_present(self) -> None:
        result = runner.invoke(theme_app, ["--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Scheme" in result.output
        assert "Tags" in result.output
        assert "Inspired by" in result.output


# ────────────────────── filtering ────────────────────────


class TestFilters:
    def test_filter_by_tag(self) -> None:
        result = runner.invoke(theme_app, ["--tag", "dark", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" in result.output
        assert "paper" not in result.output
        assert "stripe" not in result.output
        assert "1 theme(s)" in result.output

    def test_filter_by_light_scheme(self) -> None:
        result = runner.invoke(theme_app, ["--scheme", "light", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" not in result.output
        assert "paper" in result.output
        assert "stripe" in result.output
        assert "2 theme(s)" in result.output

    def test_filter_by_dark_scheme(self) -> None:
        result = runner.invoke(theme_app, ["--scheme", "dark", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" in result.output
        assert "1 theme(s)" in result.output

    def test_invalid_scheme_exits_2(self) -> None:
        result = runner.invoke(theme_app, ["--scheme", "rainbow", "--project-root", "/tmp"])
        assert result.exit_code == 2
        assert "Invalid --scheme" in result.output

    def test_filter_returning_zero_themes_exits_0(self) -> None:
        """A filter that matches no themes is a normal empty-result, not
        an error. CLI exits 0 with a friendly message."""
        result = runner.invoke(theme_app, ["--tag", "nonexistent-tag", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "No themes match the filter" in result.output


# ────────────────────── project-local themes ────────────────────────


class TestProjectLocalDiscovery:
    def test_project_theme_appears_in_list(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "my-brand.css").write_text("/* brand */")
        (themes_dir / "my-brand.toml").write_text(
            'name = "my-brand"\n'
            'description = "Internal brand theme"\n'
            'inspired_by = "Internal design system"\n'
            'default_color_scheme = "light"\n'
            'tags = ["internal", "brand"]\n'
        )

        result = runner.invoke(theme_app, ["--project-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "my-brand" in result.output
        # Project source flagged in the Src column
        assert "project" in result.output
        # Framework themes still listed alongside
        assert "linear-dark" in result.output
        assert "4 theme(s)" in result.output

    def test_project_overrides_framework_in_listing(self, tmp_path: Path) -> None:
        """When a project ships its own `paper`, the listing shows the
        project version (not the framework one) — the registry's
        override semantics flow through to the CLI."""
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "paper.css").write_text("/* project paper */")

        result = runner.invoke(theme_app, ["--project-root", str(tmp_path)])
        assert result.exit_code == 0
        # paper line should now show source=project
        paper_line = next(line for line in result.output.splitlines() if line.startswith("paper"))
        assert "project" in paper_line
        # Still 3 themes total (project paper REPLACES framework paper)
        assert "3 theme(s)" in result.output


# ────────────────────── help / discovery ────────────────────────


class TestHelp:
    def test_no_args_lists_all_themes(self) -> None:
        """v0.61.40 ships only ``list`` as the single subcommand under
        ``theme_app`` — typer collapses single-command apps to the
        command itself, so ``dazzle theme`` (no args) lists themes.
        When Patches 4 (``preview``) and 5 (``init``) land, ``no_args``
        will route to help instead."""
        result = runner.invoke(theme_app, [])
        assert result.exit_code == 0
        assert "linear-dark" in result.output

    def test_list_help_mentions_filters(self) -> None:
        result = runner.invoke(theme_app, ["--help"])
        assert result.exit_code == 0
        assert "--tag" in result.output
        assert "--scheme" in result.output
        assert "--project-root" in result.output
