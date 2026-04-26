"""Tests for the v0.61.39 app-shell theme registry (#design-system Phase B Patch 1).

The registry walks ``src/dazzle_ui/runtime/static/css/themes/`` for
shipped themes and an optional ``<project>/themes/`` for project-local
ones. Each ``<name>.css`` may have a sibling ``<name>.toml`` declaring
metadata (description / inspired_by / default_color_scheme /
font_preconnect / tags).

Themes without a manifest get sensible defaults so legacy CSS-only
themes still load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle_ui.themes.app_theme_registry import (
    AppThemeManifest,
    discover_themes,
    get_theme,
    list_theme_names,
)

# ─────────────────────── shipped-theme discovery ──────────────────────


class TestShippedThemes:
    """Each of the three shipped themes (linear-dark / paper / stripe)
    must discover with a parsed manifest."""

    def test_linear_dark_discovered(self) -> None:
        m = get_theme("linear-dark")
        assert m is not None
        assert m.name == "linear-dark"
        assert m.default_color_scheme == "dark"
        assert m.source == "framework"
        assert "Linear" in m.inspired_by
        assert "dark" in m.tags

    def test_paper_discovered(self) -> None:
        m = get_theme("paper")
        assert m is not None
        assert m.default_color_scheme == "light"
        assert "warm" in m.tags

    def test_stripe_discovered(self) -> None:
        m = get_theme("stripe")
        assert m is not None
        assert m.default_color_scheme == "light"
        assert "Stripe" in m.inspired_by

    def test_list_contains_all_three(self) -> None:
        names = list_theme_names()
        assert "linear-dark" in names
        assert "paper" in names
        assert "stripe" in names

    def test_unknown_theme_returns_none(self) -> None:
        assert get_theme("does-not-exist") is None

    def test_css_paths_resolve(self) -> None:
        """Each shipped theme's css_path must point at an existing file."""
        for name in ("linear-dark", "paper", "stripe"):
            m = get_theme(name)
            assert m is not None
            assert m.css_path.is_file(), f"{name} css_path missing: {m.css_path}"


# ─────────────────────── manifest parsing ──────────────────────


class TestManifestParsing:
    """The TOML loader must enforce the contract."""

    def test_default_color_scheme_must_be_valid(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad-scheme.css").write_text("/* placeholder */")
        (themes_dir / "bad-scheme.toml").write_text(
            'name = "bad-scheme"\ndefault_color_scheme = "rainbow"\n'
        )
        with pytest.raises(ValueError, match="default_color_scheme must be one of"):
            discover_themes(project_root=tmp_path)

    def test_manifest_name_must_match_filename(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "actual-name.css").write_text("/* placeholder */")
        (themes_dir / "actual-name.toml").write_text('name = "different-name"\n')
        with pytest.raises(ValueError, match="doesn't match CSS filename"):
            discover_themes(project_root=tmp_path)

    def test_css_only_theme_synthesises_defaults(self, tmp_path: Path) -> None:
        """A CSS file without a sibling TOML still loads — defaults are
        synthesised so legacy / quick-iteration themes work without
        manifest authoring."""
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "minimal.css").write_text("/* placeholder */")

        all_themes = discover_themes(project_root=tmp_path)
        assert "minimal" in all_themes
        m = all_themes["minimal"]
        assert m.default_color_scheme == "auto"
        assert m.tags == ()
        assert m.font_preconnect == ()
        assert m.description == ""

    def test_font_preconnect_parses_as_tuple(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "fonted.css").write_text("/* placeholder */")
        (themes_dir / "fonted.toml").write_text(
            'name = "fonted"\n'
            'default_color_scheme = "light"\n'
            'font_preconnect = ["https://fonts.example.test/css?family=A", '
            '"https://fonts.example.test/css?family=B"]\n'
        )
        m = discover_themes(project_root=tmp_path)["fonted"]
        assert isinstance(m.font_preconnect, tuple)
        assert len(m.font_preconnect) == 2


# ─────────────────────── project-local override ──────────────────────


class TestProjectLocalOverride:
    def test_project_theme_loads_alongside_framework(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "my-brand.css").write_text("/* project theme */")
        (themes_dir / "my-brand.toml").write_text(
            'name = "my-brand"\ndefault_color_scheme = "light"\n'
        )

        all_themes = discover_themes(project_root=tmp_path)
        assert "my-brand" in all_themes
        assert all_themes["my-brand"].source == "project"
        # Framework themes still discovered alongside
        assert "linear-dark" in all_themes
        assert all_themes["linear-dark"].source == "framework"

    def test_project_theme_overrides_framework_of_same_name(self, tmp_path: Path) -> None:
        """Projects can ship their own ``paper`` to tweak the framework
        default without forking — the project version wins."""
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "paper.css").write_text("/* project's paper */")

        m = discover_themes(project_root=tmp_path)["paper"]
        assert m.source == "project"
        assert m.css_path == themes_dir / "paper.css"

    def test_no_project_root_skips_project_discovery(self) -> None:
        """When ``project_root=None``, only framework themes load."""
        all_themes = discover_themes(project_root=None)
        # All sources should be framework
        assert all(m.source == "framework" for m in all_themes.values())

    def test_project_root_without_themes_dir_is_safe(self, tmp_path: Path) -> None:
        """No ``themes/`` directory in the project — registry still loads
        framework themes without error."""
        # tmp_path has no `themes/` subdir
        all_themes = discover_themes(project_root=tmp_path)
        assert "linear-dark" in all_themes


# ─────────────────────── registry shape ──────────────────────


class TestRegistryShape:
    def test_manifest_is_frozen_dataclass(self) -> None:
        """AppThemeManifest must be frozen so consumers can rely on
        immutability."""
        from dataclasses import FrozenInstanceError

        m = get_theme("linear-dark")
        assert m is not None
        with pytest.raises(FrozenInstanceError):
            m.name = "tampered"  # type: ignore[misc]

    def test_list_theme_names_is_sorted(self) -> None:
        names = list_theme_names()
        assert names == sorted(names)

    def test_returned_dict_keyed_by_name(self) -> None:
        themes = discover_themes()
        for name, m in themes.items():
            assert isinstance(m, AppThemeManifest)
            assert m.name == name
