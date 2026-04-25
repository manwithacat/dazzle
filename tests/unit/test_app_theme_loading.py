"""Tests for the v0.61.36 app-shell theme loading mechanism (#design-system Phase A).

The framework default ships shadcn-zinc tokens via design-system.css;
projects can override them with an alternate :root block by setting
``[ui] theme = "<name>"`` in dazzle.toml. The override CSS lives at
``src/dazzle_ui/runtime/static/css/themes/<name>.css`` and loads AFTER
the bundle so its ``@layer overrides`` block wins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.manifest import load_manifest

# ────────────────────────── manifest parsing ────────────────────────────


class TestManifestAppTheme:
    def test_app_theme_defaults_to_none(self, tmp_path: Path) -> None:
        (tmp_path / "dazzle.toml").write_text(
            '[project]\nname = "x"\nversion = "1.0.0"\nroot = "x"\n[dsl]\npaths = ["dsl/"]\n'
        )
        mf = load_manifest(tmp_path / "dazzle.toml")
        assert mf.app_theme is None

    def test_ui_theme_field_parses(self, tmp_path: Path) -> None:
        (tmp_path / "dazzle.toml").write_text(
            '[project]\nname = "x"\nversion = "1.0.0"\nroot = "x"\n'
            '[dsl]\npaths = ["dsl/"]\n'
            '[ui]\ntheme = "linear-dark"\n'
        )
        mf = load_manifest(tmp_path / "dazzle.toml")
        assert mf.app_theme == "linear-dark"

    def test_ui_app_theme_alias_also_parses(self, tmp_path: Path) -> None:
        """``[ui] app_theme = "..."`` works as an alias for ``theme`` —
        avoids the keyword overlap with the ``[theme]`` section that
        controls site/marketing-page tokens."""
        (tmp_path / "dazzle.toml").write_text(
            '[project]\nname = "x"\nversion = "1.0.0"\nroot = "x"\n'
            '[dsl]\npaths = ["dsl/"]\n'
            '[ui]\napp_theme = "paper"\n'
        )
        mf = load_manifest(tmp_path / "dazzle.toml")
        assert mf.app_theme == "paper"

    def test_ops_dashboard_uses_linear_dark(self) -> None:
        """The shipped ops_dashboard example sets the linear-dark theme
        as the v0.61.36 proof — this test pins the example so a
        rename of the theme triggers a CI red rather than a silent
        404 on the stylesheet."""
        repo_root = Path(__file__).resolve().parents[2]
        mf = load_manifest(repo_root / "examples/ops_dashboard/dazzle.toml")
        assert mf.app_theme == "linear-dark"


# ────────────────────────── theme CSS file ────────────────────────────


class TestLinearDarkCSS:
    """The linear-dark theme file ships with the framework — pin its
    presence + key invariants so a refactor doesn't silently break it."""

    @pytest.fixture
    def css_path(self) -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / "src/dazzle_ui/runtime/static/css/themes/linear-dark.css"

    def test_css_file_exists(self, css_path: Path) -> None:
        assert css_path.is_file(), f"Theme CSS missing at {css_path}"

    def test_uses_overrides_layer(self, css_path: Path) -> None:
        """Theme CSS must declare `@layer overrides { ... }` so it wins
        over base/framework/app cascade layers (defined in base.html)."""
        text = css_path.read_text()
        assert "@layer overrides" in text

    def test_overrides_required_app_tokens(self, css_path: Path) -> None:
        """Each token consumed by templates as `hsl(var(--<name>))` must
        be re-defined by the theme so swap is total. Spot-check the
        load-bearing ones."""
        text = css_path.read_text()
        for token in [
            "--background",
            "--foreground",
            "--primary",
            "--card",
            "--muted",
            "--border",
            "--ring",
            "--destructive",
        ]:
            assert f"{token}:" in text, f"Theme missing override for {token}"

    def test_provides_both_dark_and_light_variants(self, css_path: Path) -> None:
        """linear-dark is dark-first but ships a light variant for users
        who flip data-theme — otherwise toggling theme on a Linear-themed
        app would fall back to the bundle's default light tokens, which
        would clash with the dark cyan accent."""
        text = css_path.read_text()
        assert '[data-theme="dark"]' in text
        assert '[data-theme="light"]' in text


# ────────────────────── base.html theme link ───────────────────────


class TestBaseTemplateThemeLink:
    """``base.html`` conditionally emits `<link href="themes/<name>.css">`
    after the bundle when `_app_theme` is set on the Jinja env."""

    def _render_base(self, app_theme: str | None) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        if app_theme is not None:
            env.globals["_app_theme"] = app_theme
        # Test render needs a couple of globals normally provided by the
        # template_renderer init pipeline.
        tmpl = env.get_template("base.html")
        return tmpl.render(
            page_title="Test",
            app_name="Test",
            theme_variant=lambda: "dark",
        )

    def test_theme_link_present_when_app_theme_set(self) -> None:
        html = self._render_base("linear-dark")
        assert "themes/linear-dark" in html

    def test_theme_link_absent_when_app_theme_unset(self) -> None:
        html = self._render_base(None)
        assert "themes/" not in html

    def test_theme_link_renders_after_bundle(self) -> None:
        """Cascade order matters — the theme override must come AFTER
        the bundle so `@layer overrides` wins."""
        html = self._render_base("linear-dark")
        bundle_pos = html.find("dazzle-bundle")
        theme_pos = html.find("themes/linear-dark")
        assert bundle_pos > -1 and theme_pos > -1
        assert theme_pos > bundle_pos, "theme link must come AFTER bundle"
