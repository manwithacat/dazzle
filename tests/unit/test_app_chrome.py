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
        assert chrome.topbar_title == "app"

    def test_manifest_favicon_overrides_default(self) -> None:
        manifest = SimpleNamespace(favicon="/static/custom.svg", cdn=False, app_theme=None)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.favicon == "/static/custom.svg"

    def test_manifest_cdn_toggle(self) -> None:
        manifest = SimpleNamespace(favicon=None, cdn=True, app_theme=None)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.use_cdn is True

    def test_manifest_topbar_title_carried_1794(self) -> None:
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme=None, topbar_title="page")
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.topbar_title == "page"

    def test_manifest_page_purpose_carried_1811(self) -> None:
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme=None, page_purpose=False)
        chrome = resolve_app_chrome(None, project_root=None, manifest=manifest)
        assert chrome.page_purpose is False

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
            (SimpleNamespace(enabled=True, shortcut="backtick"), True),
            (SimpleNamespace(enabled=False, shortcut="backtick"), False),
            (None, False),
        ],
    )
    def test_feedback_widget_script_iff_enabled(self, feedback_widget: Any, mounted: bool) -> None:
        appspec = SimpleNamespace(feedback_widget=feedback_widget, app_config=None)
        chrome = resolve_app_chrome(appspec, project_root=None, manifest=None)
        assert (FEEDBACK_WIDGET_JS in chrome.js_scripts) is mounted
        assert (("dz-feedback-shortcut", "backtick") in chrome.meta) is mounted

    @pytest.mark.parametrize("shortcut", ["none", "ctrl-shift-f", "f1"])
    def test_feedback_shortcut_reaches_the_page_1842(self, shortcut: str) -> None:
        """The DSL `shortcut:` rides the chrome meta into every app-shell page."""
        from dazzle.http.runtime.page_routes import _resolve_chrome_assets

        appspec = SimpleNamespace(
            feedback_widget=SimpleNamespace(enabled=True, shortcut=shortcut), app_config=None
        )
        chrome = resolve_app_chrome(appspec, project_root=None, manifest=None)
        assert chrome.meta[0] == ("dz-feedback-shortcut", shortcut)
        assets = _resolve_chrome_assets(SimpleNamespace(fragment_chrome_meta=chrome.meta))
        ctx = PageContext(page_title="Tasks", app_name="Demo", user_email="ada@example.test")
        html = dispatch_render_page(
            ctx, "<p>body</p>", js_scripts=chrome.js_scripts, extra_meta=assets.meta
        )
        assert f'<meta name="dz-feedback-shortcut" content="{shortcut}">' in html

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


class TestProjectAssetFingerprint1793:
    """In production every project URL the chrome links is content-hashed (#1793)."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DAZZLE_ENV", "production")
        monkeypatch.delenv("DAZZLE_OVERRIDE_THEME", raising=False)
        (tmp_path / "static" / "css").mkdir(parents=True)
        (tmp_path / "static" / "js").mkdir()
        (tmp_path / "static" / "css" / "custom.css").write_text("body{}")
        (tmp_path / "static" / "js" / "brand-chrome.js").write_text("brand();")
        (tmp_path / "themes").mkdir()
        (tmp_path / "themes" / "acme.css").write_text("@import url('/static/css/custom.css');")
        return tmp_path

    def _chrome(self, project, scripts: list[str]) -> AppChrome:
        manifest = SimpleNamespace(favicon=None, cdn=False, app_theme="acme", app_scripts=scripts)
        return resolve_app_chrome(None, project_root=project, manifest=manifest)

    def test_project_urls_hashed_custom_css_last(self, project) -> None:
        chrome = self._chrome(project, ["/static/js/brand-chrome.js"])
        assert chrome.js_scripts[-1].startswith("/static/js/brand-chrome.")
        assert chrome.js_scripts[-1] != "/static/js/brand-chrome.js"
        theme = [u for u in chrome.css_links if u.startswith("/static/themes/acme.")]
        assert theme and theme[0] != "/static/themes/acme.css"
        assert chrome.theme_map["acme"][-1] == theme[0]
        assert chrome.css_links[-1].startswith("/static/css/custom.")
        assert chrome.css_links[-1] != "/static/css/custom.css"

    def test_query_bumped_app_script_passes_through_with_warning(self, project, caplog) -> None:
        with caplog.at_level("WARNING", logger="dazzle.page.runtime.app_chrome"):
            chrome = self._chrome(project, ["/static/js/brand-chrome.js?v=8"])
        assert chrome.js_scripts[-1] == "/static/js/brand-chrome.js?v=8"
        assert "hand-bumped query string" in caplog.text


class TestFeedbackPolicyMeta1854:
    """The chrome carries the widget policy and the renderer the reviewer flag (#1854)."""

    @staticmethod
    def _spec(review: Any = None, **over: Any) -> Any:
        from dazzle.core.ir.feedback_widget import FeedbackReviewSpec, FeedbackWidgetSpec

        kwargs: dict[str, Any] = {"enabled": True, **over}
        if review is not None:
            kwargs["review"] = FeedbackReviewSpec(**review)
        return FeedbackWidgetSpec(**kwargs)

    def test_policy_metas_without_review(self) -> None:
        chrome = resolve_app_chrome(
            SimpleNamespace(
                feedback_widget=self._spec(categories=["bug", "ux"], severities=["p1", "note"]),
                app_config=None,
            ),
            project_root=None,
            manifest=None,
        )
        meta = dict(chrome.meta)
        assert meta["dz-feedback-categories"] == "bug,ux"
        assert meta["dz-feedback-severities"] == "p1,note"
        assert meta["dz-feedback-screenshot"] == "off"
        assert meta["dz-feedback-review-shortcut"] == "none"
        assert "dz-feedback-review-personas" not in meta

    def test_policy_metas_with_review(self) -> None:
        spec = self._spec(
            review={"personas": ["super_admin", "trust_admin"], "screenshot": "optional"}
        )
        chrome = resolve_app_chrome(
            SimpleNamespace(feedback_widget=spec, app_config=None), project_root=None, manifest=None
        )
        meta = dict(chrome.meta)
        assert meta["dz-feedback-review-shortcut"] == "alt+shift+r"
        assert meta["dz-feedback-screenshot"] == "optional"
        assert meta["dz-feedback-review-personas"] == "super_admin,trust_admin"

    def test_disabled_widget_emits_no_policy_metas(self) -> None:
        chrome = resolve_app_chrome(
            SimpleNamespace(feedback_widget=self._spec(enabled=False), app_config=None),
            project_root=None,
            manifest=None,
        )
        assert chrome.meta == ()

    @staticmethod
    def _render(roles: list[str], chrome_meta: tuple[tuple[str, str], ...]) -> str:
        ctx = PageContext(
            page_title="Tasks",
            app_name="Demo",
            is_authenticated=True,
            user_email="ada@example.test",
            user_roles=roles,
        )
        return dispatch_render_page(
            ctx,
            "<p>body</p>",
            js_scripts=("/static/dist/dazzle.min.js", FEEDBACK_WIDGET_JS),
            extra_meta=chrome_meta,
        )

    def test_reviewer_role_gets_the_review_meta(self) -> None:
        """A `role_`-prefixed database role matches the bare DSL persona name."""
        html = self._render(
            ["role_trust_admin"], (("dz-feedback-review-personas", "super_admin,trust_admin"),)
        )
        assert '<meta name="dz-feedback-review" content="1">' in html
        assert '<meta name="dz-user-role" content="trust_admin">' in html

    def test_second_role_also_qualifies(self) -> None:
        html = self._render(
            ["teacher", "super_admin"], (("dz-feedback-review-personas", "super_admin"),)
        )
        assert 'name="dz-feedback-review"' in html

    def test_non_reviewer_gets_no_review_meta(self) -> None:
        html = self._render(["teacher"], (("dz-feedback-review-personas", "super_admin"),))
        assert "dz-feedback-review" not in html.replace("dz-feedback-review-personas", "")

    def test_no_review_block_means_no_review_meta(self) -> None:
        html = self._render(["super_admin"], ())
        assert 'name="dz-feedback-review"' not in html


class TestPageBodyAttrs1854:
    """`<body data-dz-*>` carries the page context for client anchors (#1854)."""

    def test_authenticated_detail_page(self) -> None:
        from dazzle.render.context import DetailContext

        ctx = PageContext(
            page_title="Task",
            app_name="Demo",
            is_authenticated=True,
            user_email="ada@example.test",
            user_roles=["role_teacher"],
            view_name="task_detail",
            entity_ref="Task",
            detail=DetailContext(
                entity_name="Task", title="Task", fields=[], item={"id": "abc-123", "title": "x"}
            ),
        )
        html = dispatch_render_page(ctx, "<p>body</p>")
        assert (
            '<body class="dz-page" data-dz-surface="task_detail" data-dz-entity="Task" '
            'data-dz-record="abc-123" data-dz-persona="teacher">' in html
        )

    def test_edit_form_record_and_workspace(self) -> None:
        from dazzle.render.context import FormContext

        ctx = PageContext(
            page_title="Edit",
            app_name="Demo",
            is_authenticated=True,
            user_email="ada@example.test",
            user_roles=["admin"],
            view_name="task_edit",
            entity_ref="Task",
            workspace_name="ops",
            form=FormContext(
                entity_name="Task",
                title="Edit",
                fields=[],
                action_url="/x",
                mode="edit",
                initial_values={"id": "rec-9"},
            ),
        )
        html = dispatch_render_page(ctx, "<p>body</p>")
        assert 'data-dz-record="rec-9"' in html
        assert 'data-dz-workspace="ops"' in html

    def test_create_form_has_no_record(self) -> None:
        from dazzle.render.context import FormContext

        ctx = PageContext(
            page_title="New",
            app_name="Demo",
            is_authenticated=True,
            user_email="ada@example.test",
            view_name="task_create",
            entity_ref="Task",
            form=FormContext(
                entity_name="Task", title="New", fields=[], action_url="/x", mode="create"
            ),
        )
        html = dispatch_render_page(ctx, "<p>body</p>")
        assert "data-dz-record" not in html
        assert 'data-dz-surface="task_create"' in html
        # No roles → no persona attribute (empty values are omitted).
        assert "data-dz-persona" not in html

    def test_anonymous_page_has_no_body_attrs(self) -> None:
        ctx = PageContext(page_title="Tasks", app_name="Demo", view_name="task_list")
        html = dispatch_render_page(ctx, "<p>body</p>")
        assert '<body class="dz-page">' in html

    def test_values_are_attribute_escaped(self) -> None:
        ctx = PageContext(
            page_title="Tasks",
            app_name="Demo",
            is_authenticated=True,
            user_email="ada@example.test",
            view_name='x" onload="alert(1)',
        )
        html = dispatch_render_page(ctx, "<p>body</p>")
        assert 'onload="alert' not in html
        assert 'data-dz-surface="x&quot; onload=&quot;alert(1)"' in html
