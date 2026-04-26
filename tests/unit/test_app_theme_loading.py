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

    def test_contact_manager_uses_paper(self) -> None:
        """v0.61.36 follow-up: contact_manager opts into the paper
        theme (Notion-warm) since the small-firm-owner persona benefits
        from readability over density."""
        repo_root = Path(__file__).resolve().parents[2]
        mf = load_manifest(repo_root / "examples/contact_manager/dazzle.toml")
        assert mf.app_theme == "paper"

    def test_support_tickets_uses_stripe(self) -> None:
        """v0.61.36 follow-up: support_tickets opts into the stripe
        theme (Stripe-formal) for the agent + manager personas."""
        repo_root = Path(__file__).resolve().parents[2]
        mf = load_manifest(repo_root / "examples/support_tickets/dazzle.toml")
        assert mf.app_theme == "stripe"


# ────────────────────────── theme CSS file ────────────────────────────


SHIPPED_THEMES = ["linear-dark", "paper", "stripe"]


@pytest.mark.parametrize("theme_name", SHIPPED_THEMES)
class TestShippedThemeCSS:
    """Every theme file shipped with the framework must satisfy the same
    structural invariants — `@layer overrides` block, every load-bearing
    token re-defined, both dark + light variants."""

    def _css_path(self, theme_name: str) -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / f"src/dazzle_ui/runtime/static/css/themes/{theme_name}.css"

    def test_css_file_exists(self, theme_name: str) -> None:
        path = self._css_path(theme_name)
        assert path.is_file(), f"Theme CSS missing at {path}"

    def test_uses_overrides_layer(self, theme_name: str) -> None:
        """Theme CSS must declare `@layer overrides { ... }` so it wins
        over base/framework/app cascade layers (defined in base.html)."""
        text = self._css_path(theme_name).read_text()
        assert "@layer overrides" in text

    def test_overrides_required_app_tokens(self, theme_name: str) -> None:
        """Each token consumed by templates as `hsl(var(--<name>))` must
        be re-defined by the theme so swap is total. Spot-check the
        load-bearing ones."""
        text = self._css_path(theme_name).read_text()
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

    def test_provides_both_dark_and_light_variants(self, theme_name: str) -> None:
        """Each theme is opinionated about its default mode but ships
        the other variant too — otherwise toggling data-theme would
        fall back to the default bundle's tokens and clash with the
        theme's accent."""
        text = self._css_path(theme_name).read_text()
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


class TestThemeURLResolution:
    """v0.61.41 (Phase B Patch 5): the resolved theme URL is set on
    the Jinja env at startup, distinct from the theme name. base.html
    prefers ``_app_theme_url`` over the legacy inline path so framework
    and project themes use different URL spaces (`/static/css/themes/`
    vs `/static/themes/`)."""

    def _render_base(self, *, app_theme: str | None, app_theme_url: str | None) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        if app_theme is not None:
            env.globals["_app_theme"] = app_theme
        if app_theme_url is not None:
            env.globals["_app_theme_url"] = app_theme_url
        tmpl = env.get_template("base.html")
        return tmpl.render(page_title="t", app_name="t", theme_variant=lambda: "dark")

    def test_resolved_url_wins_over_legacy_inline_path(self) -> None:
        """When ``_app_theme_url`` is set, base.html uses it verbatim
        and skips the legacy `('css/themes/' + name + '.css') | static_url`
        construction. Lets the registry decide the URL — framework
        themes get `/static/css/themes/<name>.css`, project themes get
        `/static/themes/<name>.css`."""
        html = self._render_base(
            app_theme="linear-dark",
            app_theme_url="/static/themes/my-brand.css",
        )
        # Resolved URL is rendered verbatim
        assert 'href="/static/themes/my-brand.css"' in html
        # Legacy fingerprinted framework path is NOT rendered (the
        # `elif` branch is skipped)
        assert "themes/linear-dark." not in html

    def test_legacy_inline_path_still_works_when_url_unset(self) -> None:
        """Backwards compat: deployments that only set ``_app_theme``
        (without ``_app_theme_url``) still get a working framework
        theme link via the fingerprinted static_url filter."""
        html = self._render_base(app_theme="paper", app_theme_url=None)
        assert "themes/paper" in html

    def test_neither_set_renders_no_theme_link(self) -> None:
        html = self._render_base(app_theme=None, app_theme_url=None)
        assert "themes/" not in html


class TestFontPreconnect:
    """v0.61.42 (Phase B Patch 6): each theme can declare a list of
    Google Fonts URLs in `font_preconnect`. base.html threads them in
    after Inter so first-paint can fetch the theme's actual fonts in
    parallel with the bundle."""

    def _render_base(self, *, font_preconnect: list[str] | None) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        if font_preconnect is not None:
            env.globals["_app_theme_font_preconnect"] = font_preconnect
        tmpl = env.get_template("base.html")
        return tmpl.render(page_title="t", app_name="t", theme_variant=lambda: "light")

    def test_each_url_renders_as_link(self) -> None:
        urls = [
            "https://fonts.googleapis.com/css2?family=Source+Serif+4&display=swap",
            "https://fonts.googleapis.com/css2?family=Geist+Mono&display=swap",
        ]
        html = self._render_base(font_preconnect=urls)
        # Jinja autoescapes & → &amp; in attribute values; the browser
        # decodes back so the URL is functionally correct. Assert the
        # escaped form here so we pin the actual rendered output.
        for url in urls:
            assert url.replace("&", "&amp;") in html

    def test_inter_always_present(self) -> None:
        """Inter is always preconnected as the universal fallback —
        themes only declare ADDITIONAL fonts."""
        html = self._render_base(font_preconnect=None)
        assert "fonts.googleapis.com/css2?family=Inter" in html

    def test_empty_list_renders_no_extra_links(self) -> None:
        """linear-dark uses Inter only → empty font_preconnect → no
        extra <link> elements beyond the always-present Inter one."""
        html = self._render_base(font_preconnect=[])
        # Only the Inter line should match
        family_links = [line for line in html.splitlines() if "fonts.googleapis.com/css2" in line]
        assert len(family_links) == 1
        assert "family=Inter" in family_links[0]


class TestShippedThemeFontPreconnect:
    """The three shipped themes have specific fonts declared in their
    manifests — pin them so a refactor doesn't drop them silently."""

    def test_linear_dark_uses_inter_only(self) -> None:
        from dazzle_ui.themes.app_theme_registry import get_theme

        m = get_theme("linear-dark")
        assert m is not None
        assert m.font_preconnect == ()

    def test_paper_preconnects_source_serif(self) -> None:
        from dazzle_ui.themes.app_theme_registry import get_theme

        m = get_theme("paper")
        assert m is not None
        assert any("Source+Serif" in u for u in m.font_preconnect)

    def test_stripe_preconnects_inter_tight_and_geist_mono(self) -> None:
        from dazzle_ui.themes.app_theme_registry import get_theme

        m = get_theme("stripe")
        assert m is not None
        assert any("Inter+Tight" in u for u in m.font_preconnect)
        assert any("Geist+Mono" in u for u in m.font_preconnect)


class TestThemeChainRendering:
    """Phase C Patch 1: base.html emits one <link> per stylesheet in
    the inheritance chain so parent CSS loads before child CSS. Single-
    parent themes have a length-1 chain and render identically."""

    def _render_base(self, *, chain: list[str] | None) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        if chain is not None:
            env.globals["_app_theme_url_chain"] = chain
        tmpl = env.get_template("base.html")
        return tmpl.render(page_title="t", app_name="t", theme_variant=lambda: "dark")

    def test_chain_with_two_themes_emits_two_links(self) -> None:
        html = self._render_base(
            chain=[
                "/static/css/themes/linear-dark.css",
                "/static/themes/cyan-tweak.css",
            ]
        )
        # Both links present
        assert 'href="/static/css/themes/linear-dark.css"' in html
        assert 'href="/static/themes/cyan-tweak.css"' in html
        # Parent loads BEFORE child (cascade order matters — child's
        # @layer overrides must win)
        parent_pos = html.find("linear-dark.css")
        child_pos = html.find("cyan-tweak.css")
        assert parent_pos < child_pos

    def test_single_chain_renders_one_link(self) -> None:
        html = self._render_base(chain=["/static/css/themes/linear-dark.css"])
        assert html.count("themes/linear-dark.css") == 1

    def test_chain_takes_precedence_over_legacy_url(self) -> None:
        """When _app_theme_url_chain is set, it wins over the legacy
        single-URL _app_theme_url path."""
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        env.globals["_app_theme_url_chain"] = ["/static/themes/new-chain.css"]
        env.globals["_app_theme_url"] = "/static/css/themes/legacy.css"
        tmpl = env.get_template("base.html")
        html = tmpl.render(page_title="t", app_name="t", theme_variant=lambda: "dark")
        assert "new-chain.css" in html
        assert "legacy.css" not in html


class TestThemeSwitcherWiring:
    """Phase C Patch 3: live theme switching needs the server to emit
    (a) `data-theme-name` on `<html>`, (b) `data-theme-link` on each
    theme `<link>`, and (c) a JSON map of all switchable themes. The
    dzThemeSwitcher Alpine component reads these to swap themes
    without a page reload."""

    def _render(self, **globals_overrides: object) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        for k, v in globals_overrides.items():
            env.globals[k] = v
        tmpl = env.get_template("base.html")
        return tmpl.render(page_title="t", app_name="t", theme_variant=lambda: "dark")

    def test_html_carries_theme_name_attribute(self) -> None:
        html = self._render(_app_theme="paper")
        # The component reads `document.documentElement.dataset.themeName`
        # to know what's currently active.
        assert 'data-theme-name="paper"' in html

    def test_html_omits_attribute_when_no_theme(self) -> None:
        html = self._render()
        assert "data-theme-name" not in html

    def test_theme_link_marked_for_switcher(self) -> None:
        """Each theme `<link>` carries `data-theme-link="<name>"` so
        the JS can find + replace it on switch."""
        html = self._render(
            _app_theme="paper",
            _app_theme_url_chain=["/static/css/themes/paper.css"],
        )
        assert 'data-theme-link="paper"' in html

    def test_theme_map_emitted_as_json_script(self) -> None:
        """All available themes ship as inline JSON for the switcher to read."""
        theme_map = {
            "linear-dark": ["/static/css/themes/linear-dark.css"],
            "paper": ["/static/css/themes/paper.css"],
        }
        html = self._render(_app_theme="paper", _app_theme_map=theme_map)
        assert 'id="dz-app-themes"' in html
        assert 'type="application/json"' in html
        assert "linear-dark" in html
        assert "/static/css/themes/paper.css" in html

    def test_no_map_when_empty(self) -> None:
        """Empty/missing map → no <script> element. Component init
        early-returns when the map is missing."""
        html = self._render(_app_theme="paper")
        assert 'id="dz-app-themes"' not in html

    def test_chain_links_share_theme_link_marker(self) -> None:
        """A multi-link chain still gets the marker on every <link> so
        the switcher removes them all on swap."""
        html = self._render(
            _app_theme="cyan-tweak",
            _app_theme_url_chain=[
                "/static/css/themes/linear-dark.css",
                "/static/themes/cyan-tweak.css",
            ],
        )
        assert html.count('data-theme-link="cyan-tweak"') == 2
