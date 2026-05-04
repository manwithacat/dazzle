"""Tests for #958 cycles 4 + 5 — scroll containment + haptic opt-in.

Cycle 4: a CSS file applying `-webkit-overflow-scrolling: touch` +
`overscroll-behavior: contain` to known scrollable container
classes, plus a `.dz-scroll` utility for adopter-defined
containers.

Cycle 5: `[ui] haptic = true` opts the framework JS into
`navigator.vibrate(...)` calls on key events. Threaded through
manifest → theme module → base.html meta tag → JS reader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CSS_ROOT = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/css"
JS_ROOT = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/js"
SCROLL_CSS = CSS_ROOT / "components/mobile-scroll.css"
DZ_ALPINE_JS = JS_ROOT / "dz-alpine.js"
BASE_HTML = Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/base.html"


@pytest.fixture(scope="module")
def scroll_css() -> str:
    assert SCROLL_CSS.is_file()
    return SCROLL_CSS.read_text()


@pytest.fixture(scope="module")
def js() -> str:
    return DZ_ALPINE_JS.read_text()


@pytest.fixture(scope="module")
def base_html() -> str:
    return BASE_HTML.read_text()


# ---------------------------------------------------------------------------
# Cycle 4 — scroll containment
# ---------------------------------------------------------------------------


class TestScrollContainmentCss:
    @pytest.mark.parametrize(
        "needle",
        [
            "-webkit-overflow-scrolling: touch",
            "overscroll-behavior: contain",
            "overscroll-behavior-x: contain",
            ".dz-scroll",
            "@layer components",
        ],
        ids=[
            "test_uses_webkit_overflow_scrolling_touch",
            "test_uses_overscroll_behavior_contain",
            "test_horizontal_overscroll_contain_for_tables",
            "test_dz_scroll_utility_class_present",
            "test_wraps_in_components_layer",
        ],
    )
    def test_css_contains(self, scroll_css: str, needle: str) -> None:
        assert needle in scroll_css

    @pytest.mark.parametrize(
        "selector",
        [
            ".dz-card-body",
            ".dz-drawer-content",
            ".dz-detail-card-body",
            ".dz-app-content",
            ".dz-app-body",
            ".dz-form-body",
            ".dz-modal",
            ".dz-slideover-content",
            ".dz-pdf-viewer-panel",
        ],
    )
    def test_known_scrollable_selector_present(self, scroll_css: str, selector: str) -> None:
        """Each canonical scroll container must be in the rule.
        Drift here = inconsistent touch ergonomics across surfaces."""
        assert selector in scroll_css

    def test_present_in_dist_bundle(self) -> None:
        dist_css = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.css"
        )
        if not dist_css.is_file():
            pytest.skip("dist not built")
        text = dist_css.read_text()
        assert (
            "-webkit-overflow-scrolling:touch" in text.replace(" ", "")
            or "-webkit-overflow-scrolling: touch" in text
        )
        assert (
            "overscroll-behavior:contain" in text.replace(" ", "")
            or "overscroll-behavior: contain" in text
        )


# ---------------------------------------------------------------------------
# Cycle 5 — haptic opt-in
# ---------------------------------------------------------------------------


class TestHapticManifestField:
    def test_default_off(self) -> None:
        """Off by default — uninvited vibration is jarring."""
        from dazzle.core.manifest import ProjectManifest

        m = ProjectManifest(name="x", version="0", project_root="x", module_paths=[])
        assert m.haptic is False

    def test_loads_from_dazzle_toml(self, tmp_path: Path) -> None:
        """`[ui] haptic = true` in the manifest sets the field."""
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text('[project]\nname = "x"\nversion = "0"\nroot = "x"\n\n[ui]\nhaptic = true\n')
        m = load_manifest(toml)
        assert m.haptic is True


class TestHapticThemeModule:
    def test_configure_haptic_persists(self) -> None:
        from dazzle_ui.runtime.theme import configure_haptic, is_haptic_enabled

        original = is_haptic_enabled()
        try:
            configure_haptic(True)
            assert is_haptic_enabled() is True
            configure_haptic(False)
            assert is_haptic_enabled() is False
        finally:
            configure_haptic(original)


class TestHapticBaseHtml:
    def test_meta_tag_emitted_when_enabled(self, base_html: str) -> None:
        """The meta tag is gated on `haptic_enabled()` — verify the
        Jinja conditional is wired correctly."""
        assert "haptic_enabled()" in base_html
        assert 'meta name="dz-haptic"' in base_html


class TestHapticJsHandler:
    def test_reads_meta_tag_at_boot(self, js: str) -> None:
        """The boot-time enablement check reads the meta tag the
        manifest opt-in emits."""
        assert 'meta[name="dz-haptic"]' in js

    def test_uses_navigator_vibrate(self, js: str) -> None:
        """The Vibration API is the one cross-browser surface for
        haptic on the open web."""
        assert "navigator.vibrate" in js

    def test_exposes_window_dzhaptic(self, js: str) -> None:
        """Adopters who want manual triggers (e.g. inside an Alpine
        handler) need a stable window-level API."""
        assert "window.dzHaptic" in js
        assert "tap" in js
        assert "success" in js
        assert "error" in js
        assert "warning" in js

    def test_honours_prefers_reduced_motion(self, js: str) -> None:
        """Vibration is a motion-adjacent signal — same accessibility
        intent as visual motion. Skip when reduce is set."""
        assert "prefers-reduced-motion: reduce" in js
        # The `reduce` check appears near the haptic boot block.
        haptic_idx = js.find("dz-haptic")
        reduce_idx = js.find("(prefers-reduced-motion: reduce)", haptic_idx)
        assert reduce_idx != -1

    def test_auto_wires_showtoast_event(self, js: str) -> None:
        """Auto-fire on showToast events so adopters don't have to
        manually wire haptic to every toast trigger."""
        assert 'addEventListener("showToast"' in js

    def test_auto_wires_swipe_events(self, js: str) -> None:
        """Cycle-3 swipe events get a haptic tap — confirms the
        gesture commit without competing with the visual snap-back."""
        assert 'addEventListener("swipe-left"' in js
        assert 'addEventListener("swipe-right"' in js

    def test_auto_wires_htmx_error_response(self, js: str) -> None:
        """4xx/5xx responses fire the error pattern."""
        assert 'addEventListener("htmx:afterRequest"' in js
        assert "xhr.status >= 400" in js

    def test_no_op_when_meta_absent(self, js: str) -> None:
        """Without the meta tag, the boot block bails out before
        registering any listeners — no spurious vibration calls
        even in browsers that support the API."""
        # The early-return pattern: `if (!enabled || reduce) return;`
        assert "if (!enabled || reduce) return" in js

    def test_present_in_dist_bundle(self) -> None:
        dist_js = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.js"
        )
        if not dist_js.is_file():
            pytest.skip("dist not built")
        assert "dzHaptic" in dist_js.read_text()
