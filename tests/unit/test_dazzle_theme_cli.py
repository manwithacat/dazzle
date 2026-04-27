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
        result = runner.invoke(theme_app, ["list", "--project-root", "/tmp"])
        assert result.exit_code == 0, result.output
        assert "linear-dark" in result.output
        assert "paper" in result.output
        assert "stripe" in result.output
        # Footer reports the count
        assert "3 theme(s)" in result.output

    def test_table_header_present(self) -> None:
        result = runner.invoke(theme_app, ["list", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Scheme" in result.output
        assert "Tags" in result.output
        assert "Inspired by" in result.output


# ────────────────────── filtering ────────────────────────


class TestFilters:
    def test_filter_by_tag(self) -> None:
        result = runner.invoke(theme_app, ["list", "--tag", "dark", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" in result.output
        assert "paper" not in result.output
        assert "stripe" not in result.output
        assert "1 theme(s)" in result.output

    def test_filter_by_light_scheme(self) -> None:
        result = runner.invoke(theme_app, ["list", "--scheme", "light", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" not in result.output
        assert "paper" in result.output
        assert "stripe" in result.output
        assert "2 theme(s)" in result.output

    def test_filter_by_dark_scheme(self) -> None:
        result = runner.invoke(theme_app, ["list", "--scheme", "dark", "--project-root", "/tmp"])
        assert result.exit_code == 0
        assert "linear-dark" in result.output
        assert "1 theme(s)" in result.output

    def test_invalid_scheme_exits_2(self) -> None:
        result = runner.invoke(theme_app, ["list", "--scheme", "rainbow", "--project-root", "/tmp"])
        assert result.exit_code == 2
        assert "Invalid --scheme" in result.output

    def test_filter_returning_zero_themes_exits_0(self) -> None:
        """A filter that matches no themes is a normal empty-result, not
        an error. CLI exits 0 with a friendly message."""
        result = runner.invoke(
            theme_app, ["list", "--tag", "nonexistent-tag", "--project-root", "/tmp"]
        )
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

        result = runner.invoke(theme_app, ["list", "--project-root", str(tmp_path)])
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

        result = runner.invoke(theme_app, ["list", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        # paper line should now show source=project
        paper_line = next(line for line in result.output.splitlines() if line.startswith("paper"))
        assert "project" in paper_line
        # Still 3 themes total (project paper REPLACES framework paper)
        assert "3 theme(s)" in result.output


# ────────────────────── help / discovery ────────────────────────


class TestHelp:
    def test_no_args_shows_help(self) -> None:
        """With multiple subcommands (``list`` + ``init``), `dazzle theme`
        with no args triggers ``no_args_is_help`` and shows the
        subcommand list — restored from v0.61.40's single-command
        collapse behaviour."""
        result = runner.invoke(theme_app, [])
        # no_args_is_help exits 2 (usage); both `list` and `init` should
        # appear in the subcommand listing
        assert result.exit_code == 2
        assert "list" in result.output
        assert "init" in result.output

    def test_list_help_mentions_filters(self) -> None:
        import re

        result = runner.invoke(theme_app, ["list", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes — Typer's help formatter inserts
        # colour/wrap escapes in CI environments that split flag names
        # across format runs (e.g. `--\x1b[0m\x1b[1;36m-tag`).
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--tag" in plain
        assert "--scheme" in plain
        assert "--project-root" in plain


# ────────────────────── init subcommand ────────────────────────


class TestThemeInit:
    """``dazzle theme init <name>`` scaffolds a project-local theme by
    copying an existing one. v0.61.41 (Phase B Patch 5)."""

    def test_init_creates_css_and_toml(self, tmp_path: Path) -> None:
        result = runner.invoke(theme_app, ["init", "my-brand", "--project-root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "themes" / "my-brand.css").is_file()
        assert (tmp_path / "themes" / "my-brand.toml").is_file()
        assert "Created theme 'my-brand'" in result.output

    def test_init_copies_default_source_linear_dark(self, tmp_path: Path) -> None:
        """Without --inspired-by, init copies linear-dark as the
        starting point."""
        runner.invoke(theme_app, ["init", "test-theme", "--project-root", str(tmp_path)])
        toml_text = (tmp_path / "themes" / "test-theme.toml").read_text()
        assert "Linear" in toml_text  # inspired_by inherited from linear-dark
        assert 'name = "test-theme"' in toml_text
        assert 'default_color_scheme = "dark"' in toml_text  # linear-dark's default

    def test_init_inspired_by_flag(self, tmp_path: Path) -> None:
        runner.invoke(
            theme_app,
            [
                "init",
                "warm-brand",
                "--inspired-by",
                "paper",
                "--project-root",
                str(tmp_path),
            ],
        )
        toml_text = (tmp_path / "themes" / "warm-brand.toml").read_text()
        assert "Notion" in toml_text  # paper's inspired_by
        assert 'default_color_scheme = "light"' in toml_text  # paper's default

    def test_init_unknown_inspired_by_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(
            theme_app,
            [
                "init",
                "x",
                "--inspired-by",
                "doesnt-exist",
                "--project-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 2
        assert "not found" in result.output

    def test_init_invalid_name_exits_2(self, tmp_path: Path) -> None:
        # Name with a space — invalid
        result = runner.invoke(theme_app, ["init", "Bad Name", "--project-root", str(tmp_path)])
        assert result.exit_code == 2
        assert "Invalid theme name" in result.output

    def test_init_uppercase_name_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(theme_app, ["init", "MyBrand", "--project-root", str(tmp_path)])
        assert result.exit_code == 2
        assert "should be lowercase" in result.output

    def test_init_existing_theme_exits_2(self, tmp_path: Path) -> None:
        """Init refuses to overwrite — user must delete first."""
        # Create the theme once
        runner.invoke(theme_app, ["init", "duplicate", "--project-root", str(tmp_path)])
        # Try to create again
        result = runner.invoke(theme_app, ["init", "duplicate", "--project-root", str(tmp_path)])
        assert result.exit_code == 2
        assert "already exists" in result.output

    def test_init_then_list_shows_new_theme(self, tmp_path: Path) -> None:
        """End-to-end: init scaffolds → list discovers immediately."""
        init_result = runner.invoke(
            theme_app, ["init", "scaffolded", "--project-root", str(tmp_path)]
        )
        assert init_result.exit_code == 0
        list_result = runner.invoke(theme_app, ["list", "--project-root", str(tmp_path)])
        assert list_result.exit_code == 0
        assert "scaffolded" in list_result.output
        assert "project" in list_result.output  # source flagged correctly


# ────────────────────── preview subcommand ────────────────────────


class TestThemePreview:
    """``dazzle theme preview <name>`` validates the theme exists then
    execs ``dazzle serve --local`` with DAZZLE_OVERRIDE_THEME set.
    Tests cover the validation path (the actual exec is not testable
    without a real dev server)."""

    def test_unknown_theme_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(
            theme_app, ["preview", "does-not-exist", "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "not found" in result.output
        # Lists available themes for guidance
        assert "linear-dark" in result.output
        assert "paper" in result.output

    def test_unknown_project_theme_also_exits_2(self, tmp_path: Path) -> None:
        """Even with a project-local theme directory, an unknown name
        still exits 2 — preview validates against the full registry."""
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "actual.css").write_text("/* placeholder */")
        result = runner.invoke(
            theme_app, ["preview", "wrong-name", "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "wrong-name" in result.output
        # Project theme appears in the available list
        assert "actual" in result.output

    def test_help_describes_override_mechanism(self) -> None:
        """`--help` should make clear this is non-mutating — operators
        worry about preview commands silently committing config changes."""
        result = runner.invoke(theme_app, ["preview", "--help"])
        assert result.exit_code == 0
        # Hint that the override is via env var, not toml mutation
        assert (
            "DAZZLE_OVERRIDE_THEME" in result.output
            or "no commit needed" in result.output.lower()
            or "no project files" in result.output.lower()
            or "override" in result.output.lower()
        )
