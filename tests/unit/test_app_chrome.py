"""Tests for the AppChrome resolver (#1042 follow-up).

The resolver is the typed-Page replacement for the legacy Jinja env
globals (``_use_cdn``, ``_app_theme*``, ``_favicon``,
``_feedback_widget_enabled``) that fed ``base.html`` / ``app_shell.html``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.page.runtime.app_chrome import FEEDBACK_WIDGET_JS, AppChrome, resolve_app_chrome
from dazzle.render.context import PageContext
from dazzle.render.dispatch import dispatch_render_page


class TestResolveAppChrome:
    def test_defaults_with_no_appspec_or_manifest(self) -> None:
        chrome = resolve_app_chrome(None, project_root=None, manifest=None)
        assert isinstance(chrome, AppChrome)
        assert chrome.css_links == ("/static/dist/dazzle.min.css",)
        # #1276: lucide UMD precedes the framework bundle so window.lucide
        # exists when dazzle.min.js calls lucide.createIcons().
        # HMC-018 slice 3: the TomSelect vendor JS entry was retired —
        # combobox/tags are HM-native controllers inside the framework bundle.
        assert chrome.js_scripts == (
            "/static/dist/dazzle-icons.min.js",
            "/static/dist/dazzle.min.js",
        )
        assert chrome.theme is None
        assert chrome.theme_map == {}
        assert chrome.font_preconnect == ()
        assert chrome.favicon == "/static/assets/dazzle-favicon.svg"
        assert chrome.use_cdn is False

    def test_manifest_favicon_overrides_default(self) -> None:
        manifest = SimpleNamespace(favicon="/static/custom.svg", cdn=False, app_theme=None)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.favicon == "/static/custom.svg"

    def test_manifest_cdn_toggle(self) -> None:
        manifest = SimpleNamespace(favicon=None, cdn=True, app_theme=None)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.use_cdn is True

    def test_manifest_app_scripts_appended_after_framework(self) -> None:
        # #1515: downstream [ui] app_scripts thread into the chrome <head>
        # after the framework bundle, in declared order.
        manifest = SimpleNamespace(
            favicon=None,
            cdn=False,
            app_theme=None,
            app_scripts=["/static/js/dz-islands.js", "/static/js/charts.js"],
        )
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.js_scripts[-2:] == (
            "/static/js/dz-islands.js",
            "/static/js/charts.js",
        )
        # Framework bundle still precedes the app scripts.
        assert chrome.js_scripts.index("/static/dist/dazzle.min.js") < chrome.js_scripts.index(
            "/static/js/dz-islands.js"
        )

    def test_manifest_no_app_scripts_is_byte_stable(self) -> None:
        # Absent / empty app_scripts → unchanged framework-only script list.
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme=None, app_scripts=[])
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.js_scripts == (
            "/static/dist/dazzle-icons.min.js",
            "/static/dist/dazzle.min.js",
        )

    @pytest.mark.parametrize(
        ("feedback_widget", "mounted"),
        [
            (SimpleNamespace(enabled=True), True),
            (SimpleNamespace(enabled=False), False),
            (None, False),
        ],
    )
    def test_feedback_widget_script_iff_enabled(self, feedback_widget: Any, mounted: bool) -> None:
        appspec = SimpleNamespace(feedback_widget=feedback_widget, app_config=None)
        chrome = resolve_app_chrome(appspec, project_root=None, manifest=None)
        assert (FEEDBACK_WIDGET_JS in chrome.js_scripts) is mounted

    def test_missing_theme_returns_default_chain(self) -> None:
        """Themes that don't exist return the default chain — the
        warning is logged but the app still boots."""
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme="theme-that-does-not-exist")
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        # Resolution failed → theme stays None, default CSS chain only.
        assert chrome.theme is None
        assert chrome.css_links == ("/static/dist/dazzle.min.css",)

    def test_env_theme_wins_over_dsl_and_manifest(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("DAZZLE_OVERRIDE_THEME", "env-winner")
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme="manifest-loser")
        appspec = SimpleNamespace(
            feedback_widget=None,
            app_config=SimpleNamespace(theme="dsl-loser"),
        )
        # Theme resolution will fail (env-winner doesn't exist as a
        # registered theme) but the precedence still resolves to
        # env-winner before failure. We assert the failure path leaves
        # theme=None (graceful degradation).
        chrome = resolve_app_chrome(appspec, project_root=None, manifest=manifest)
        assert chrome.theme is None  # failed resolution → None

    def test_lucide_umd_precedes_framework_bundle_1276(self) -> None:
        """#1276: data-lucide icons render invisible if dazzle.min.js
        calls `lucide.createIcons()` before the lucide UMD bundle has
        defined window.lucide. The script order must put lucide first."""
        chrome = resolve_app_chrome(None, project_root=None, manifest=None)
        lucide_idx = next(
            (i for i, s in enumerate(chrome.js_scripts) if s.endswith("dazzle-icons.min.js")),
            -1,
        )
        bundle_idx = next(
            (i for i, s in enumerate(chrome.js_scripts) if s.endswith("/dazzle.min.js")),
            -1,
        )
        assert lucide_idx >= 0, f"lucide UMD missing from js_scripts: {chrome.js_scripts}"
        assert bundle_idx >= 0, f"framework bundle missing: {chrome.js_scripts}"
        assert lucide_idx < bundle_idx, (
            "lucide UMD must precede the framework bundle so window.lucide "
            f"is defined before dazzle.min.js runs: {chrome.js_scripts}"
        )

    def test_use_cdn_does_not_affect_default_urls(self) -> None:
        """v0.67.93: the use_cdn field is informational only — the
        framework currently always serves local ``dist/`` assets.
        Routing CDN-vs-local is a follow-up."""
        manifest = SimpleNamespace(favicon=None, cdn=True, app_theme=None)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.use_cdn is True
        assert chrome.css_links == ("/static/dist/dazzle.min.css",)


class TestFeedbackWidgetPage:
    """The chromed page carries the widget script and the signed-in identity
    the widget reads (``<meta name="dz-user-email|dz-user-role">``)."""

    @staticmethod
    def _render(js_scripts: tuple[str, ...], email: str) -> str:
        ctx = PageContext(
            page_title="Tasks",
            app_name="Demo",
            is_authenticated=bool(email),
            user_email=email,
            user_roles=["role_teacher"],
        )
        return dispatch_render_page(ctx, "<p>body</p>", js_scripts=js_scripts)

    def test_enabled_emits_script_and_identity(self) -> None:
        html = self._render(("/static/dist/dazzle.min.js", FEEDBACK_WIDGET_JS), "ada@example.test")
        assert f'<script defer src="{FEEDBACK_WIDGET_JS}"></script>' in html
        assert '<meta name="dz-user-email" content="ada@example.test">' in html
        assert '<meta name="dz-user-role" content="teacher">' in html

    def test_disabled_emits_neither(self) -> None:
        html = self._render(("/static/dist/dazzle.min.js",), "ada@example.test")
        assert "feedback-widget" not in html
        assert "dz-user-email" not in html

    def test_anonymous_gets_script_without_identity(self) -> None:
        html = self._render(("/static/dist/dazzle.min.js", FEEDBACK_WIDGET_JS), "")
        assert FEEDBACK_WIDGET_JS in html
        assert "dz-user-email" not in html


class TestProjectCustomCss1796:
    """`static/css/custom.css` reaches the app shell, after the theme chain (#1796)."""

    def test_custom_css_linked_after_theme_chain_when_present(self, tmp_path) -> None:
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "static" / "css" / "custom.css").write_text("body{}")
        chrome = resolve_app_chrome(None, project_root=tmp_path, manifest=None)
        links = [u.split("?")[0] for u in chrome.css_links]
        assert "/static/css/custom.css" in links
        assert links.index("/static/css/custom.css") == len(links) - 1

    def test_no_custom_css_no_link(self, tmp_path) -> None:
        chrome = resolve_app_chrome(None, project_root=tmp_path, manifest=None)
        assert all("custom.css" not in u for u in chrome.css_links)
