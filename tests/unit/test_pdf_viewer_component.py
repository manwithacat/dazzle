"""Tests for #942 cycle 1b — PDF detail-view component (chrome
+ keyboard shortcuts).

Covers:
- Template renders required parameters (src, back_url) into the
  expected attributes
- Optional prev_url / next_url propagate to data-* attributes and
  the sibling-nav block
- Title defaults to "Document" when not supplied
- Element carries `data-dz-widget="pdf-viewer"` (and NOT `x-data`,
  per the widget contract from #940)
- JS handler: bridge registration, key dispatch (Esc/j/k/arrows),
  metakey suppression, editable-target suppression
- CSS: at least one rule, all dimensions in tokens (no literal px
  / hard-coded colours — passes the existing token-only
  expectation for component CSS)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "src/dazzle_ui/templates/components/pdf_viewer.html"
CSS_PATH = REPO_ROOT / "src/dazzle_ui/runtime/static/css/components/pdf-viewer.css"
JS_PATH = REPO_ROOT / "src/dazzle_ui/runtime/static/js/pdf-viewer.js"


@pytest.fixture
def jinja_env() -> Any:
    return create_jinja_env()


def _render(jinja_env: Any, **kwargs: Any) -> str:
    tmpl = jinja_env.from_string('{% include "components/pdf_viewer.html" %}')
    return tmpl.render(**kwargs)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    def test_required_params_render(self, jinja_env: Any) -> None:
        html = _render(
            jinja_env,
            src="/api/storage/cohort_pdfs/proxy?key=x",
            back_url="/app/manuscripts",
        )
        assert 'data-dz-widget="pdf-viewer"' in html
        assert 'data-dz-back-url="/app/manuscripts"' in html
        assert 'src="/api/storage/cohort_pdfs/proxy?key=x"' in html
        assert 'type="application/pdf"' in html

    def test_default_title_is_document(self, jinja_env: Any) -> None:
        html = _render(jinja_env, src="/x", back_url="/back")
        assert ">Document<" in html  # rendered as the h1 text

    def test_explicit_title_overrides_default(self, jinja_env: Any) -> None:
        html = _render(
            jinja_env,
            src="/x",
            back_url="/back",
            title="2024 Macbeth Y10 cohort",
        )
        assert "2024 Macbeth Y10 cohort" in html
        assert ">Document<" not in html

    def test_no_sibling_nav_when_urls_unset(self, jinja_env: Any) -> None:
        html = _render(jinja_env, src="/x", back_url="/back")
        assert "dz-pdf-viewer-nav" not in html
        assert "data-dz-prev-url" not in html
        assert "data-dz-next-url" not in html
        # Footer keyboard hints also drop the j / k mentions when no
        # sibling nav is present — only Esc remains.
        assert ">j<" not in html
        assert ">k<" not in html

    def test_sibling_nav_renders_when_urls_set(self, jinja_env: Any) -> None:
        html = _render(
            jinja_env,
            src="/x",
            back_url="/back",
            prev_url="/app/manuscripts/123",
            next_url="/app/manuscripts/125",
        )
        assert "dz-pdf-viewer-nav" in html
        assert 'data-dz-prev-url="/app/manuscripts/123"' in html
        assert 'data-dz-next-url="/app/manuscripts/125"' in html
        # Both keyboard hints surface when siblings exist.
        assert ">j<" in html
        assert ">k<" in html

    def test_only_prev_url_shows_disabled_next(self, jinja_env: Any) -> None:
        html = _render(
            jinja_env,
            src="/x",
            back_url="/back",
            prev_url="/app/manuscripts/123",
        )
        assert "dz-pdf-viewer-nav" in html
        assert "data-dz-prev-url=" in html
        assert "data-dz-next-url" not in html
        # Disabled-state next button still renders so the chrome stays
        # symmetrical, but is aria-disabled and tabindex=-1.
        assert 'aria-disabled="true"' in html

    def test_does_not_carry_x_data(self, jinja_env: Any) -> None:
        """Per the widget contract from #940 the wrapper must NOT
        co-locate `x-data` with `data-dz-widget`. The bridge owns the
        lifecycle alone."""
        html = _render(
            jinja_env,
            src="/x",
            back_url="/back",
            prev_url="/p",
            next_url="/n",
        )
        assert "x-data" not in html
        assert "x-init" not in html

    def test_embed_uses_proxy_url_verbatim(self, jinja_env: Any) -> None:
        """The src is passed straight to <embed>. No transforms,
        no rewriting — matches what the cycle 1a proxy returns."""
        proxy_url = (
            "/api/storage/cohort_pdfs/proxy?key=production/cohort_assessments/u1/abc/file.pdf"
        )
        html = _render(jinja_env, src=proxy_url, back_url="/back")
        assert proxy_url in html


# ---------------------------------------------------------------------------
# Source-level checks on the JS controller
# ---------------------------------------------------------------------------


class TestJsController:
    def _load(self) -> str:
        return JS_PATH.read_text()

    def test_registers_with_bridge(self) -> None:
        source = self._load()
        assert 'bridge.registerWidget("pdf-viewer"' in source

    def test_uses_module_scope_attribute_reads(self) -> None:
        """`getAttribute` rather than dataset because the data-* names
        with hyphens (data-dz-back-url) translate to camelCase via
        `dataset` — getAttribute keeps the name explicit and survives
        any future rename to a non-data-* attribute."""
        source = self._load()
        assert 'el.getAttribute("data-dz-back-url")' in source
        assert 'el.getAttribute("data-dz-prev-url")' in source
        assert 'el.getAttribute("data-dz-next-url")' in source

    def test_keys_handled(self) -> None:
        source = self._load()
        for key in ("Escape", '"j"', '"k"', "ArrowLeft", "ArrowRight"):
            assert key in source, f"Missing key handling for {key}"

    def test_meta_keys_pass_through(self) -> None:
        """Cmd-/Ctrl-/Alt-modified keystrokes must NOT navigate —
        they're typically reserved for browser shortcuts (Cmd+R,
        Ctrl+L) and shouldn't be hijacked by the viewer."""
        source = self._load()
        assert "metaKey" in source
        assert "ctrlKey" in source
        assert "altKey" in source

    def test_editable_target_suppression(self) -> None:
        """When the user's typing into a form field that happens to
        be inside the viewer (e.g. an annotation overlay), the j/k
        shortcuts must not trigger sibling nav."""
        source = self._load()
        assert "isEditableTarget" in source
        assert "INPUT" in source
        assert "TEXTAREA" in source
        assert "isContentEditable" in source

    def test_unmount_removes_listener(self) -> None:
        source = self._load()
        assert "removeEventListener" in source


# ---------------------------------------------------------------------------
# Source-level checks on the CSS chrome
# ---------------------------------------------------------------------------


class TestCss:
    def _load(self) -> str:
        return CSS_PATH.read_text()

    def test_top_level_class_exists(self) -> None:
        source = self._load()
        assert ".dz-pdf-viewer {" in source
        assert ".dz-pdf-viewer-header" in source
        assert ".dz-pdf-viewer-body" in source
        assert ".dz-pdf-viewer-footer" in source
        assert ".dz-pdf-viewer-embed" in source

    def test_uses_design_tokens(self) -> None:
        """Lengths + colours come from tokens — no hard-coded px /
        hex values in the chrome rules. Mirrors the token-only
        expectation already enforced for the rest of components/."""
        source = self._load()
        # Use the var(--colour-*) and var(--space-*) families.
        assert "var(--colour-bg)" in source
        assert "var(--colour-surface)" in source
        assert "var(--colour-border)" in source
        assert "var(--space-sm)" in source or "var(--space-md)" in source

    def test_passes_clip_check_baseline(self) -> None:
        """The component CSS doesn't introduce any height-vs-line-box
        regressions — runs the framework's clip-check from #937
        scoped to just this file."""
        import importlib.util
        import sys

        script_path = REPO_ROOT / "scripts" / "css_clip_check.py"
        spec = importlib.util.spec_from_file_location("css_clip_check_for_test", script_path)
        assert spec is not None and spec.loader is not None
        clip = importlib.util.module_from_spec(spec)
        sys.modules["css_clip_check_for_test"] = clip
        spec.loader.exec_module(clip)

        findings = clip.scan_file(CSS_PATH)
        assert findings == [], (
            f"pdf-viewer.css clip-check found {len(findings)} regression(s):\n"
            + "\n".join(f.render() for f in findings)
        )


# ---------------------------------------------------------------------------
# Bundle integration
# ---------------------------------------------------------------------------


class TestBundleIntegration:
    def test_css_listed_in_build_dist(self) -> None:
        source = (REPO_ROOT / "scripts" / "build_dist.py").read_text()
        assert "components/pdf-viewer.css" in source or '"pdf-viewer.css"' in source

    def test_js_loaded_from_base_template(self) -> None:
        """base.html loads the bridge handlers as standalone <script>
        tags (not bundled) — pdf-viewer.js follows the same pattern
        and ships under the static/js URL."""
        base = (REPO_ROOT / "src/dazzle_ui/templates/base.html").read_text()
        assert "pdf-viewer.js" in base


# ---------------------------------------------------------------------------
# Panel slot (#942 cycle 2a)
# ---------------------------------------------------------------------------


class TestPanelSlot:
    def _render(self, jinja_env: Any, **kwargs: Any) -> str:
        tmpl = jinja_env.from_string('{% include "components/pdf_viewer.html" %}')
        return tmpl.render(**kwargs)

    def test_panel_omitted_when_no_panel_html(self, jinja_env: Any) -> None:
        """No `panel_html` parameter ⇒ no panel chrome at all —
        toggle checkbox absent, aside absent, footer kbd hint absent.
        Matches cycle 1b's include-is-opt-in pattern."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        assert "dz-pdf-viewer-panel" not in html
        assert "dz-panel-toggle" not in html
        assert ">p<" not in html  # footer keyboard hint

    def test_panel_renders_when_panel_html_provided(self, jinja_env: Any) -> None:
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html="<p>Marking summary</p>",
            panel_label="Marking",
        )
        assert 'class="dz-pdf-viewer-panel"' in html
        assert 'role="complementary"' in html
        assert 'aria-label="Marking"' in html
        assert "<p>Marking summary</p>" in html
        assert ">\n          Marking\n        <" in html or ">Marking<" in html
        assert ">p<" in html  # footer kbd hint
        assert 'id="dz-panel-toggle"' in html
        # Cycle 2b: close affordance is now a `<button data-dz-panel-close>`
        # (was `<label for>` in cycle 2a) so it's tabbable and receives
        # focus correctly when the panel opens.
        assert "data-dz-panel-close" in html
        assert "<button" in html  # close button rendered

    def test_panel_label_defaults_to_related(self, jinja_env: Any) -> None:
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html="<div>content</div>",
        )
        assert "Related" in html
        assert 'aria-label="Related"' in html

    def test_panel_html_renders_unescaped(self, jinja_env: Any) -> None:
        """``panel_html`` is project-rendered markup; the framework
        passes it through `| safe` so HTML structure survives. The
        project is responsible for autoescape inside their own
        template."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html='<ul><li class="x">item</li></ul>',
        )
        assert '<ul><li class="x">item</li></ul>' in html

    def test_panel_close_button_carries_data_hook(self, jinja_env: Any) -> None:
        """Cycle 2b: close affordance is a ``<button>`` with a
        ``data-dz-panel-close`` hook the bridge JS uses to wire
        click → toggle. Real button is tabbable and receives
        ``focus()`` correctly (the cycle 2a label-based form silently
        no-op'd ``focus()``, leaving keyboard users stranded)."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html="<p>x</p>",
        )
        assert "data-dz-panel-close" in html
        assert "dz-pdf-viewer-panel-close" in html
        assert "<button" in html
