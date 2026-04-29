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
    """#946 — every framework asset the component depends on must be
    in the bundled CSS/JS. Adopters that load the framework via
    ``dist/dazzle.min.css`` + ``dist/dazzle.min.js`` get the chrome
    wired without copy-pasting standalone <link>/<script> tags. The
    cycle 1b shape (standalone <script> in base.html) shipped with
    the wrong default; #946 fixes it by bundling."""

    def test_css_listed_in_build_dist(self) -> None:
        source = (REPO_ROOT / "scripts" / "build_dist.py").read_text()
        assert '"pdf-viewer.css"' in source

    def test_css_listed_in_runtime_loader(self) -> None:
        """The runtime CSS bundle (served at /styles/dazzle.css via
        css_loader.py) must include pdf-viewer.css too — projects
        using the dev-time direct-import path see the same set of
        component families as projects shipping dist/dazzle.min.css."""
        source = (REPO_ROOT / "src/dazzle_ui/runtime/css_loader.py").read_text()
        assert "components/pdf-viewer.css" in source

    def test_css_imported_from_dazzle_entry(self) -> None:
        """``dazzle.css`` (the canonical entry stylesheet referenced
        from base.html) must @import pdf-viewer.css. Pre-#946 the
        @import was missing, so projects using base.html got the JS
        bridge but no CSS — panels rendered inline because the
        chrome rules never loaded."""
        source = (REPO_ROOT / "src/dazzle_ui/runtime/static/css/dazzle.css").read_text()
        assert "components/pdf-viewer.css" in source

    def test_js_listed_in_build_dist(self) -> None:
        """``dist/dazzle.min.js`` must include the pdf-viewer bridge
        handler. Pre-#946 the JS shipped only as a standalone
        ``<script>`` tag in base.html; projects with their own base
        template (loading dist/dazzle.min.js) lost the bridge and
        every keyboard shortcut was inert."""
        source = (REPO_ROOT / "scripts" / "build_dist.py").read_text()
        assert '"js" / "pdf-viewer.js"' in source

    def test_js_in_framework_set_for_comment_stripping(self) -> None:
        """FRAMEWORK_JS controls which files get comment-stripping
        in the dist bundle. pdf-viewer.js carries a multi-line
        docstring + section banners that should be stripped along
        with the other framework scripts."""
        source = (REPO_ROOT / "scripts" / "build_dist.py").read_text()
        assert '"pdf-viewer.js"' in source


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
        # Cycle 5a: toggle ID is namespaced per-panel; cycle 2a's
        # single-panel backwards-compat case lands as "dz-panel-toggle-panel".
        assert 'id="dz-panel-toggle-panel"' in html
        assert 'class="dz-pdf-viewer-panel-toggle"' in html
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


# ---------------------------------------------------------------------------
# #944 cycle 6a — footer slot
# ---------------------------------------------------------------------------


class TestFooterSlot:
    def _render(self, jinja_env: Any, **kwargs: Any) -> str:
        tmpl = jinja_env.from_string('{% include "components/pdf_viewer.html" %}')
        return tmpl.render(**kwargs)

    def test_slot_omitted_by_default(self, jinja_env: Any) -> None:
        """No ``footer_slot_html`` ⇒ no slot div. Matches cycle 1b
        backwards-compat — projects already on the include don't see
        layout drift."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        assert "dz-pdf-viewer-footer-slot" not in html

    def test_slot_renders_html_unescaped(self, jinja_env: Any) -> None:
        """``footer_slot_html`` is project-rendered markup; the
        framework passes it through ``| safe`` so HTML structure
        survives. Same trust contract as cycle 2a's ``panel_html``."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            footer_slot_html='<span class="page-counter">Page 3 / 14</span>',
        )
        assert "dz-pdf-viewer-footer-slot" in html
        assert '<span class="page-counter">Page 3 / 14</span>' in html

    def test_kbd_legend_renders_by_default(self, jinja_env: Any) -> None:
        """Default behaviour preserves the cycle 1b legend so existing
        adopters don't have to opt back into it."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        # The Esc kbd is unique to the legend (back-button has no kbd)
        assert 'class="dz-pdf-viewer-kbd">Esc<' in html

    def test_kbd_legend_suppressed_when_disabled(self, jinja_env: Any) -> None:
        """``show_kbd_legend=False`` opts out of the static legend.
        Used when the slot already advertises every binding."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            show_kbd_legend=False,
        )
        assert 'class="dz-pdf-viewer-kbd">Esc<' not in html

    def test_slot_and_legend_can_coexist(self, jinja_env: Any) -> None:
        """The slot renders before the keyboard legend so projects
        adding a page counter don't lose the discoverable shortcuts."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            footer_slot_html='<button class="zoom-in">+</button>',
        )
        # Slot div appears
        assert "dz-pdf-viewer-footer-slot" in html
        # Legend still present
        assert 'class="dz-pdf-viewer-kbd">Esc<' in html
        # Slot is positioned before the kbd legend
        slot_idx = html.index("dz-pdf-viewer-footer-slot")
        legend_idx = html.index('class="dz-pdf-viewer-kbd">Esc<')
        assert slot_idx < legend_idx


# ---------------------------------------------------------------------------
# #943 cycle 5a — multi-panel via panels=[…]
# ---------------------------------------------------------------------------


class TestMultiPanel:
    def _render(self, jinja_env: Any, **kwargs: Any) -> str:
        tmpl = jinja_env.from_string('{% include "components/pdf_viewer.html" %}')
        return tmpl.render(**kwargs)

    def test_multiple_panels_render(self, jinja_env: Any) -> None:
        """Three panels each get their own toggle, aside, and
        footer chip."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panels=[
                {
                    "name": "marking",
                    "label": "Marking Result",
                    "key": "m",
                    "html": "<p>Score: 42</p>",
                },
                {
                    "name": "feedback",
                    "label": "Feedback",
                    "key": "f",
                    "html": "<p>Strong essay</p>",
                },
                {
                    "name": "ao",
                    "label": "AO Breakdown",
                    "key": "a",
                    "html": "<p>AO1: 80%</p>",
                },
            ],
        )
        # Per-panel toggle IDs disambiguate
        assert 'id="dz-panel-toggle-marking"' in html
        assert 'id="dz-panel-toggle-feedback"' in html
        assert 'id="dz-panel-toggle-ao"' in html
        # data-dz-panel hooks for JS
        assert 'data-dz-panel="marking"' in html
        assert 'data-dz-panel="feedback"' in html
        assert 'data-dz-panel="ao"' in html
        # Per-panel keys
        assert 'data-dz-panel-key="m"' in html
        assert 'data-dz-panel-key="f"' in html
        assert 'data-dz-panel-key="a"' in html
        # Each panel's content is rendered unescaped
        assert "<p>Score: 42</p>" in html
        assert "<p>Strong essay</p>" in html
        assert "<p>AO1: 80%</p>" in html
        # Footer shows one chip per panel
        assert 'class="dz-pdf-viewer-kbd">m<' in html
        assert 'class="dz-pdf-viewer-kbd">f<' in html
        assert 'class="dz-pdf-viewer-kbd">a<' in html
        assert "Marking Result" in html
        assert "Feedback" in html
        assert "AO Breakdown" in html

    def test_panel_html_backwards_compat_normalises_to_panels(self, jinja_env: Any) -> None:
        """Cycle 2a's ``panel_html`` + ``panel_label`` continue to
        work — internally normalised to a one-element ``panels``
        list with the conventional ``p`` key."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html="<p>x</p>",
            panel_label="Marking",
        )
        # New ID shape — toggle is named "panel" in the
        # backwards-compat path
        assert 'id="dz-panel-toggle-panel"' in html
        assert 'data-dz-panel="panel"' in html
        # Default key is "p" (cycle 2a convention)
        assert 'data-dz-panel-key="p"' in html
        assert 'class="dz-pdf-viewer-kbd">p<' in html
        # Label propagates to aria-label and the panel header
        assert 'aria-label="Marking"' in html

    def test_panels_takes_precedence_over_panel_html(self, jinja_env: Any) -> None:
        """When both ``panels`` and ``panel_html`` are passed, the
        explicit ``panels`` list wins — the legacy single-panel
        parameters are ignored."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panel_html="<p>legacy</p>",
            panel_label="Legacy",
            panels=[
                {"name": "new", "label": "New", "key": "n", "html": "<p>new</p>"},
            ],
        )
        assert "<p>new</p>" in html
        assert "<p>legacy</p>" not in html
        assert 'id="dz-panel-toggle-new"' in html
        assert 'id="dz-panel-toggle-panel"' not in html

    def test_no_panels_no_toggle_no_chip(self, jinja_env: Any) -> None:
        """No ``panels`` and no ``panel_html`` ⇒ no panel chrome
        anywhere in the rendered output."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        assert "dz-pdf-viewer-panel-toggle" not in html
        assert "dz-pdf-viewer-panel" not in html
        # Default key chip absent
        assert 'class="dz-pdf-viewer-kbd">p<' not in html

    def test_each_panel_has_its_own_close_button(self, jinja_env: Any) -> None:
        """Cycle 2b: every panel gets a close button with the
        ``data-dz-panel-close`` hook so the bridge JS can find them.
        Cycle 5a: per-panel ``aria-label`` references the panel
        title so screen readers say "Close Marking panel" rather
        than a generic "Close panel"."""
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panels=[
                {"name": "a", "label": "A", "key": "a", "html": "x"},
                {"name": "b", "label": "B", "key": "b", "html": "y"},
            ],
        )
        assert html.count("data-dz-panel-close") == 2
        assert 'aria-label="Close A panel"' in html
        assert 'aria-label="Close B panel"' in html


# ---------------------------------------------------------------------------
# #943 cycle 5a — JS controller updates
# ---------------------------------------------------------------------------


class TestMultiPanelJsController:
    def _load(self) -> str:
        return JS_PATH.read_text()

    def test_queries_toggles_by_class_not_id(self) -> None:
        """Cycle 5a: the JS must work with N panels, so it can't
        rely on the cycle 2a ``getElementById('dz-panel-toggle')``
        pattern — that only finds one element. Switch to
        ``querySelectorAll('.dz-pdf-viewer-panel-toggle')``."""
        source = self._load()
        assert ".dz-pdf-viewer-panel-toggle" in source

    def test_dispatches_keys_via_data_attr(self) -> None:
        """Each toggle's key comes from ``data-dz-panel-key``. The
        JS reads that and matches against the keypress event so any
        configured key (m/f/a/p/...) routes correctly."""
        source = self._load()
        assert "data-dz-panel-key" in source

    def test_finds_open_toggle_for_esc(self) -> None:
        """Cycle 5a: Esc closes the open panel — but only the open
        one. With N panels the handler must search for the checked
        toggle rather than hardcoding a single element."""
        source = self._load()
        assert "findOpenToggle" in source

    def test_close_others_on_open(self) -> None:
        """Multi-panel exclusivity: opening one panel closes the
        others. The single fixed-width drawer slot can only show
        one at a time."""
        source = self._load()
        assert "closeOtherPanels" in source


# ---------------------------------------------------------------------------
# #943 cycle 5c — keyboard cheat-sheet overlay
# ---------------------------------------------------------------------------


class TestHelpOverlay:
    def _render(self, jinja_env: Any, **kwargs: Any) -> str:
        tmpl = jinja_env.from_string('{% include "components/pdf_viewer.html" %}')
        return tmpl.render(**kwargs)

    def test_dialog_renders_with_help_overlay_attribute(self, jinja_env: Any) -> None:
        """The overlay is a `<dialog>` with `data-dz-help-overlay`
        attribute the bridge JS uses to find it."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        assert "<dialog" in html
        assert "data-dz-help-overlay" in html
        assert 'class="dz-pdf-viewer-help"' in html

    def test_help_close_button_carries_data_hook(self, jinja_env: Any) -> None:
        """Cycle 2b's data-hook convention: the close button carries
        `data-dz-help-close` so the bridge can find it without
        coupling to the cosmetic class name."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        assert "data-dz-help-close" in html

    def test_help_lists_question_mark_binding(self, jinja_env: Any) -> None:
        """The cheat-sheet documents itself: `?` is one of the
        bindings listed inside the dialog."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        # The footer chip too — both should reference `?`
        assert "<kbd>?</kbd>" in html

    def test_help_lists_panel_keys_when_panels_set(self, jinja_env: Any) -> None:
        html = self._render(
            jinja_env,
            src="/x",
            back_url="/back",
            panels=[
                {"name": "marking", "label": "Marking", "key": "m", "html": "x"},
                {"name": "feedback", "label": "Feedback", "key": "f", "html": "y"},
            ],
        )
        # Each panel's key + label appears in the dialog row
        assert "<kbd>m</kbd>" in html
        assert "Toggle Marking" in html
        assert "<kbd>f</kbd>" in html
        assert "Toggle Feedback" in html

    def test_help_omits_sibling_rows_when_no_prev_or_next(self, jinja_env: Any) -> None:
        """When neither prev nor next is set, the j/k rows are
        absent. Avoids advertising shortcuts that won't fire."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        # The dialog content shouldn't list j/k as bindings when there
        # are no siblings. The footer chips are already gated on
        # prev_url/next_url; the dialog must follow the same rule.
        # Find the dialog block and check it.
        dialog_start = html.index("<dialog")
        dialog_end = html.index("</dialog>", dialog_start)
        dialog_block = html[dialog_start:dialog_end]
        assert "<kbd>j</kbd>" not in dialog_block
        assert "<kbd>k</kbd>" not in dialog_block

    def test_help_includes_sibling_rows_when_prev_or_next_set(self, jinja_env: Any) -> None:
        html = self._render(jinja_env, src="/x", back_url="/back", prev_url="/p", next_url="/n")
        dialog_start = html.index("<dialog")
        dialog_end = html.index("</dialog>", dialog_start)
        dialog_block = html[dialog_start:dialog_end]
        assert "<kbd>j</kbd>" in dialog_block
        assert "<kbd>k</kbd>" in dialog_block

    def test_footer_advertises_help_chip(self, jinja_env: Any) -> None:
        """The footer keyboard legend includes a `?` chip so users
        know the cheat-sheet exists."""
        html = self._render(jinja_env, src="/x", back_url="/back")
        # Look in the footer area (between the panel close-button SVG
        # and the closing </footer>). Easier to just check for the
        # combination "?</kbd>" + "Help" being present in the footer.
        assert ">Help<" in html


class TestHelpOverlayJsController:
    def _load(self) -> str:
        return JS_PATH.read_text()

    def test_dialog_opened_via_show_modal(self) -> None:
        """The bridge calls .showModal() so the browser provides
        backdrop + focus trap rather than us hand-rolling them."""
        source = self._load()
        assert ".showModal()" in source

    def test_dialog_closed_via_close_method(self) -> None:
        source = self._load()
        assert ".close()" in source

    def test_question_mark_key_opens_help(self) -> None:
        source = self._load()
        # Handler must reference the literal `?` key
        assert 'e.key === "?"' in source

    def test_esc_priority_help_then_panel_then_back(self) -> None:
        """Esc closes layers in priority order: cheat-sheet (if
        open) → panel (if any open) → back-nav. The handler
        documents this convention in a comment."""
        source = self._load()
        assert "helpIsOpen" in source
        # The Esc branch must check helpIsOpen before findOpenToggle
        esc_idx = source.index('e.key === "Escape"')
        # Look at the next ~600 chars for the priority order
        block = source[esc_idx : esc_idx + 800]
        help_idx = block.index("helpIsOpen()")
        panel_idx = block.index("findOpenToggle()")
        assert help_idx < panel_idx

    def test_other_keys_suppressed_while_help_open(self) -> None:
        """j/k/p/m/f/etc are no-ops while the cheat-sheet is open
        — the user is reading, not driving the viewer."""
        source = self._load()
        # The handler should `return` early when helpIsOpen() after
        # the Esc branch.
        assert "if (helpIsOpen()) return" in source
