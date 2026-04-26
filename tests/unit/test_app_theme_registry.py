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


# ─────────────────────── inheritance (Phase C Patch 1) ──────────────────────


class TestThemeInheritance:
    """A theme can declare ``extends = "<parent>"`` in its manifest.
    The registry walks the chain so the runtime can emit parent + child
    CSS links in cascade order. Phase C Patch 1."""

    def test_extends_field_parses(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "child.css").write_text("/* child */")
        (themes_dir / "child.toml").write_text('name = "child"\nextends = "linear-dark"\n')
        m = discover_themes(project_root=tmp_path)["child"]
        assert m.extends == "linear-dark"

    def test_extends_default_is_none(self) -> None:
        m = get_theme("linear-dark")
        assert m is not None
        assert m.extends is None

    def test_extends_must_be_string(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad.css").write_text("/* */")
        (themes_dir / "bad.toml").write_text('name = "bad"\nextends = 42\n')
        with pytest.raises(ValueError, match="must be a string"):
            discover_themes(project_root=tmp_path)

    def test_extends_self_raises(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "narcissus.css").write_text("/* */")
        (themes_dir / "narcissus.toml").write_text('name = "narcissus"\nextends = "narcissus"\n')
        with pytest.raises(ValueError, match="cannot extend itself"):
            discover_themes(project_root=tmp_path)


class TestResolveInheritanceChain:
    def test_no_extends_returns_self(self) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        chain = resolve_inheritance_chain("linear-dark")
        assert [m.name for m in chain] == ["linear-dark"]

    def test_two_level_chain_root_to_leaf(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "tweak.css").write_text("/* tweak */")
        (themes_dir / "tweak.toml").write_text('name = "tweak"\nextends = "linear-dark"\n')
        chain = resolve_inheritance_chain("tweak", project_root=tmp_path)
        # Root → leaf order so the runtime can emit CSS in cascade order
        assert [m.name for m in chain] == ["linear-dark", "tweak"]

    def test_three_level_chain(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "mid.css").write_text("/* */")
        (themes_dir / "mid.toml").write_text('name = "mid"\nextends = "linear-dark"\n')
        (themes_dir / "leaf.css").write_text("/* */")
        (themes_dir / "leaf.toml").write_text('name = "leaf"\nextends = "mid"\n')
        chain = resolve_inheritance_chain("leaf", project_root=tmp_path)
        assert [m.name for m in chain] == ["linear-dark", "mid", "leaf"]

    def test_unknown_theme_raises(self) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        with pytest.raises(ValueError, match="not found in registry"):
            resolve_inheritance_chain("does-not-exist")

    def test_missing_parent_raises(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "orphan.css").write_text("/* */")
        (themes_dir / "orphan.toml").write_text('name = "orphan"\nextends = "missing-parent"\n')
        with pytest.raises(ValueError, match="missing-parent"):
            resolve_inheritance_chain("orphan", project_root=tmp_path)

    def test_cycle_raises(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "a.css").write_text("/* */")
        (themes_dir / "a.toml").write_text('name = "a"\nextends = "b"\n')
        (themes_dir / "b.css").write_text("/* */")
        (themes_dir / "b.toml").write_text('name = "b"\nextends = "a"\n')
        with pytest.raises(ValueError, match="cycle"):
            resolve_inheritance_chain("a", project_root=tmp_path)

    def test_depth_cap_enforced(self, tmp_path: Path) -> None:
        """Inheritance depth caps at 4. Build a 5-level chain → raises."""
        from dazzle_ui.themes.app_theme_registry import resolve_inheritance_chain

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        # parent5 → parent4 → parent3 → parent2 → parent1 → linear-dark
        # (linear-dark is depth 0, so depths 1..5 → 6 total)
        chain_names = ["p1", "p2", "p3", "p4", "p5"]
        # p1 extends linear-dark, p2 extends p1, ...
        for i, n in enumerate(chain_names):
            parent = "linear-dark" if i == 0 else chain_names[i - 1]
            (themes_dir / f"{n}.css").write_text("/* */")
            (themes_dir / f"{n}.toml").write_text(f'name = "{n}"\nextends = "{parent}"\n')
        with pytest.raises(ValueError, match="exceeds max depth"):
            resolve_inheritance_chain("p5", project_root=tmp_path)


# ─────────────────────── templates_dir (Phase C Patch 2) ──────────────────────


class TestThemeTemplatesDir:
    """A theme can ship template overrides at ``<theme>/templates/``
    alongside its CSS. The registry resolves the path so the runtime
    knows where to point the Jinja loader."""

    def test_templates_dir_none_when_absent(self) -> None:
        """All three shipped themes are CSS-only — none has a sibling
        templates/ directory."""
        for name in ("linear-dark", "paper", "stripe"):
            m = get_theme(name)
            assert m is not None
            assert m.templates_dir is None

    def test_templates_dir_resolved_when_present(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "shaped.css").write_text("/* */")
        # Sibling directory matching the CSS file stem
        shaped_dir = themes_dir / "shaped"
        shaped_dir.mkdir()
        (shaped_dir / "templates").mkdir()
        (shaped_dir / "templates" / "card_wrapper.html").write_text(
            '<div class="theme-card">override</div>'
        )

        m = discover_themes(project_root=tmp_path)["shaped"]
        assert m.templates_dir == shaped_dir / "templates"

    def test_templates_dir_skipped_when_dir_exists_but_no_templates_subdir(
        self, tmp_path: Path
    ) -> None:
        """A bare `<theme>/` dir without a `templates/` subdir resolves
        to None — only the conventional layout enables overrides."""
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "named.css").write_text("/* */")
        (themes_dir / "named").mkdir()  # no templates/ subdir
        m = discover_themes(project_root=tmp_path)["named"]
        assert m.templates_dir is None


class TestAddThemeTemplateDirs:
    """``add_theme_template_dirs`` mutates the Jinja loader chain so
    theme templates win over project + framework. Phase C Patch 2."""

    def test_theme_template_overrides_framework(self, tmp_path: Path) -> None:
        import dazzle_ui.runtime.template_renderer as tr
        from dazzle_ui.runtime.template_renderer import (
            add_theme_template_dirs,
            create_jinja_env,
        )

        # Reset env so this test is hermetic
        tr._env = create_jinja_env()

        # Create a theme override for `base.html`
        theme_templates = tmp_path / "themes" / "shaped" / "templates"
        theme_templates.mkdir(parents=True)
        (theme_templates / "base.html").write_text("<html>THEME WINS</html>")

        add_theme_template_dirs([theme_templates])

        from dazzle_ui.runtime.template_renderer import get_jinja_env

        tmpl = get_jinja_env().get_template("base.html")
        rendered = tmpl.render()
        assert "THEME WINS" in rendered

        # Restore env so the rest of the suite gets the framework default
        tr._env = create_jinja_env()

    def test_empty_list_is_noop(self) -> None:
        import dazzle_ui.runtime.template_renderer as tr
        from dazzle_ui.runtime.template_renderer import (
            add_theme_template_dirs,
            create_jinja_env,
        )

        tr._env = create_jinja_env()
        loader_before = tr._env.loader
        add_theme_template_dirs([])
        assert tr._env.loader is loader_before

    def test_nonexistent_dirs_skipped(self, tmp_path: Path) -> None:
        import dazzle_ui.runtime.template_renderer as tr
        from dazzle_ui.runtime.template_renderer import (
            add_theme_template_dirs,
            create_jinja_env,
        )

        tr._env = create_jinja_env()
        loader_before = tr._env.loader
        # All-nonexistent dirs → loader unchanged
        add_theme_template_dirs([tmp_path / "nope1", tmp_path / "nope2"])
        assert tr._env.loader is loader_before

    def test_chain_order_leaf_wins(self, tmp_path: Path) -> None:
        """When a chain has multiple template dirs, the LEAF (last in
        the cascade order list) wins for same-name templates. The
        helper reverses internally so ChoiceLoader's first-match
        semantics match the cascade intent."""
        import dazzle_ui.runtime.template_renderer as tr
        from dazzle_ui.runtime.template_renderer import (
            add_theme_template_dirs,
            create_jinja_env,
        )

        tr._env = create_jinja_env()

        parent_dir = tmp_path / "parent" / "templates"
        parent_dir.mkdir(parents=True)
        (parent_dir / "base.html").write_text("PARENT")

        leaf_dir = tmp_path / "leaf" / "templates"
        leaf_dir.mkdir(parents=True)
        (leaf_dir / "base.html").write_text("LEAF")

        # Cascade order: root → leaf
        add_theme_template_dirs([parent_dir, leaf_dir])

        from dazzle_ui.runtime.template_renderer import get_jinja_env

        rendered = get_jinja_env().get_template("base.html").render()
        assert "LEAF" in rendered
        assert "PARENT" not in rendered

        tr._env = create_jinja_env()


# ─────────────────────── site config (Phase C Patch 4) ──────────────────────


class TestSiteSection:
    """Phase C Patch 4 — themes can declare a ``[site]`` section that
    configures the legacy ThemeSpec-based site/marketing pipeline.
    Allows a single theme file to carry both app-shell and site tokens."""

    def test_no_site_section_yields_defaults(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "plain.css").write_text("/* placeholder */")
        (themes_dir / "plain.toml").write_text('name = "plain"\ndefault_color_scheme = "light"\n')
        m = discover_themes(project_root=tmp_path)["plain"]
        assert m.site_preset is None
        assert m.site_overrides == {}

    def test_site_preset_only_parses(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "preset-only.css").write_text("/* placeholder */")
        (themes_dir / "preset-only.toml").write_text(
            'name = "preset-only"\ndefault_color_scheme = "light"\n[site]\npreset = "minimal"\n'
        )
        m = discover_themes(project_root=tmp_path)["preset-only"]
        assert m.site_preset == "minimal"
        assert m.site_overrides == {}

    def test_site_overrides_parse_per_category(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "branded.css").write_text("/* placeholder */")
        (themes_dir / "branded.toml").write_text(
            'name = "branded"\n'
            'default_color_scheme = "dark"\n'
            "[site]\n"
            'preset = "corporate"\n'
            "[site.colors]\n"
            'hero-bg-from = "hsl(228, 8%, 8%)"\n'
            'hero-bg-to = "hsl(228, 6%, 18%)"\n'
            "[site.spacing]\n"
            "section-y = 96\n"
        )
        m = discover_themes(project_root=tmp_path)["branded"]
        assert m.site_preset == "corporate"
        assert m.site_overrides["colors"]["hero-bg-from"] == "hsl(228, 8%, 8%)"
        assert m.site_overrides["spacing"]["section-y"] == 96

    def test_site_must_be_table(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad.css").write_text("/* placeholder */")
        (themes_dir / "bad.toml").write_text(
            'name = "bad"\ndefault_color_scheme = "light"\nsite = "minimal"\n'
        )
        with pytest.raises(ValueError, match=r"`\[site\]` must be a table"):
            discover_themes(project_root=tmp_path)

    def test_site_preset_must_be_string(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad.css").write_text("/* placeholder */")
        (themes_dir / "bad.toml").write_text(
            'name = "bad"\ndefault_color_scheme = "light"\n[site]\npreset = 42\n'
        )
        with pytest.raises(ValueError, match=r"`\[site\] preset` must be a string"):
            discover_themes(project_root=tmp_path)

    def test_unknown_site_key_rejected(self, tmp_path: Path) -> None:
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad.css").write_text("/* placeholder */")
        (themes_dir / "bad.toml").write_text(
            'name = "bad"\n'
            'default_color_scheme = "light"\n'
            "[site]\n"
            "[site.typography]\n"  # not in _SITE_OVERRIDE_KEYS
            'body = "Inter"\n'
        )
        with pytest.raises(ValueError, match=r"unknown `\[site\]` key 'typography'"):
            discover_themes(project_root=tmp_path)


class TestResolveSiteConfig:
    """``resolve_site_config`` looks up the active app theme's site
    config and walks the inheritance chain so a child can inherit a
    parent's site preset / overrides without restating them."""

    def test_none_name_returns_defaults(self) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        preset, overrides = resolve_site_config(None)
        assert preset is None
        assert overrides == {}

    def test_unknown_theme_returns_defaults(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        preset, overrides = resolve_site_config("does-not-exist", project_root=tmp_path)
        assert preset is None
        assert overrides == {}

    def test_theme_without_site_section_returns_defaults(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "plain.css").write_text("/* placeholder */")
        (themes_dir / "plain.toml").write_text('name = "plain"\ndefault_color_scheme = "light"\n')
        preset, overrides = resolve_site_config("plain", project_root=tmp_path)
        assert preset is None
        assert overrides == {}

    def test_theme_with_site_section_resolves(self, tmp_path: Path) -> None:
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "branded.css").write_text("/* placeholder */")
        (themes_dir / "branded.toml").write_text(
            'name = "branded"\n'
            'default_color_scheme = "light"\n'
            "[site]\n"
            'preset = "corporate"\n'
            "[site.colors]\n"
            'hero-bg-from = "hsl(0,0%,5%)"\n'
        )
        preset, overrides = resolve_site_config("branded", project_root=tmp_path)
        assert preset == "corporate"
        assert overrides == {"colors": {"hero-bg-from": "hsl(0,0%,5%)"}}

    def test_chain_inherits_parent_site_config(self, tmp_path: Path) -> None:
        """A child theme that omits ``[site]`` inherits the parent's
        site preset + overrides via the inheritance chain. Cascade:
        parent values fill in first, child values shallow-merge on top."""
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "parent.css").write_text("/* parent */")
        (themes_dir / "parent.toml").write_text(
            'name = "parent"\n'
            'default_color_scheme = "light"\n'
            "[site]\n"
            'preset = "minimal"\n'
            "[site.colors]\n"
            'hero-bg-from = "PARENT_FROM"\n'
            'hero-bg-to = "PARENT_TO"\n'
        )
        (themes_dir / "child.css").write_text("/* child */")
        (themes_dir / "child.toml").write_text(
            'name = "child"\nextends = "parent"\ndefault_color_scheme = "light"\n'
        )

        preset, overrides = resolve_site_config("child", project_root=tmp_path)
        # Inherited from parent
        assert preset == "minimal"
        assert overrides == {"colors": {"hero-bg-from": "PARENT_FROM", "hero-bg-to": "PARENT_TO"}}

    def test_child_overrides_parent_site_values(self, tmp_path: Path) -> None:
        """When both parent and child declare the same site token, the
        child wins (cascade leaf wins)."""
        from dazzle_ui.themes.app_theme_registry import resolve_site_config

        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "parent.css").write_text("/* parent */")
        (themes_dir / "parent.toml").write_text(
            'name = "parent"\n'
            'default_color_scheme = "light"\n'
            "[site]\n"
            'preset = "minimal"\n'
            "[site.colors]\n"
            'hero-bg-from = "PARENT"\n'
        )
        (themes_dir / "child.css").write_text("/* child */")
        (themes_dir / "child.toml").write_text(
            'name = "child"\n'
            'extends = "parent"\n'
            'default_color_scheme = "light"\n'
            "[site]\n"
            'preset = "corporate"\n'
            "[site.colors]\n"
            'hero-bg-from = "CHILD"\n'
        )
        preset, overrides = resolve_site_config("child", project_root=tmp_path)
        assert preset == "corporate"  # child preset wins
        assert overrides == {"colors": {"hero-bg-from": "CHILD"}}  # child color wins
