"""Consent + analytics JS must live under the runtime static root (#867).

`site_base.html` references both scripts via the ``static_url`` filter:

    <script src="{{ 'js/dz-consent.js' | static_url }}"></script>
    <script src="{{ 'js/dz-analytics.js' | static_url }}"></script>

``static_url`` resolves to ``/static/<path>``, which the runtime serves from
``src/dazzle_ui/runtime/static/``. In v0.61.0 these files were mistakenly
placed under ``src/dazzle_ui/static/js/`` — a different directory only
reached by the bespoke ``/site.js`` route handler — so every app with an
``analytics:`` block 404'd on page load and the consent banner buttons
became inert.

This regression test pins both files to the runtime static root so the
shape can't silently drift again.
"""

from __future__ import annotations

from pathlib import Path

_RUNTIME_STATIC_JS = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "runtime" / "static" / "js"
)
_LEGACY_STATIC_JS = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "static" / "js"


class TestAnalyticsJsLocation:
    def test_dz_consent_under_runtime_static(self) -> None:
        assert (_RUNTIME_STATIC_JS / "dz-consent.js").is_file()

    def test_dz_analytics_under_runtime_static(self) -> None:
        assert (_RUNTIME_STATIC_JS / "dz-analytics.js").is_file()

    def test_legacy_static_has_no_framework_js(self) -> None:
        """``src/dazzle_ui/static/js/`` should only carry ``site.js`` — the
        custom ``/site.js`` route reads from there. Everything else belongs
        under the runtime static mount."""
        if not _LEGACY_STATIC_JS.exists():
            return
        entries = {p.name for p in _LEGACY_STATIC_JS.iterdir() if p.is_file()}
        framework_files = entries - {"site.js"}
        assert framework_files == set(), (
            f"unexpected JS in legacy static root — will 404 at runtime: {framework_files}"
        )


class TestSiteBaseScriptReferences:
    def test_site_base_references_both_scripts(self) -> None:
        """Belt-and-braces: if someone removes the <script> tags, the JS
        location test above won't catch it."""
        site_base = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_ui"
            / "templates"
            / "site"
            / "site_base.html"
        )
        source = site_base.read_text()
        assert "'js/dz-consent.js' | static_url" in source
        assert "'js/dz-analytics.js' | static_url" in source
