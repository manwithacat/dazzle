"""Cycle 241 — tooltip fragment contract (UX-044).

Tests the canonical markers, design-token compliance, and autoescape
posture of ``fragments/tooltip_rich.html``. Also verifies the framework
CSS ``[x-cloak] { display: none !important; }`` rule exists (added in
cycle 241 so the rich tooltip panel doesn't flash on first paint).
"""

from pathlib import Path

import pytest

pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


class TestTooltipRichFragment:
    """Rich tooltip fragment renders the canonical anatomy."""

    def _render(self, **ctx) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.get_template("fragments/tooltip_rich.html")
        return tmpl.render(**ctx)

    def test_renders_canonical_markers(self) -> None:
        html = self._render(content="Export as CSV", trigger="<button>x</button>")
        # Canonical class + automation markers
        assert "dz-tooltip" in html
        assert 'data-dz-position="top"' in html  # default
        assert "data-dz-tooltip-panel" in html
        # Alpine controller + ARIA
        assert 'x-data="dzTooltip"' in html
        assert 'role="tooltip"' in html
        # x-cloak prevents first-paint flash
        assert "x-cloak" in html
        # Content renders
        assert "Export as CSV" in html

    def test_uses_design_tokens_not_daisyui(self) -> None:
        """v0.62 CSS refactor: panel chrome (foreground bg / background fg /
        shadow) lives on .dz-tooltip-panel rule rather than inline
        `bg-[hsl(var(--foreground))] text-[hsl(var(--background))]` Tailwind."""
        html = self._render(content="Hello")
        # Semantic class on rendered panel
        assert "dz-tooltip-panel" in html
        # Legacy DaisyUI class names MUST NOT appear
        assert "bg-neutral" not in html
        assert "text-neutral-content" not in html
        assert "rounded-box" not in html
        # "shadow-lg" is a DaisyUI shadow helper; modernised to explicit shadow
        assert "shadow-lg" not in html

        # CSS rule carries the inverted colour pair (foreground bg + background fg)
        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        panel_block = css.split(".dz-tooltip-panel {")[1].split("}")[0]
        assert "background: var(--colour-text)" in panel_block
        assert "color: var(--colour-bg)" in panel_block

    def test_position_override(self) -> None:
        html = self._render(content="Help", position="bottom")
        assert 'data-dz-position="bottom"' in html
        assert "x-anchor.bottom=" in html

    def test_delay_parameters(self) -> None:
        html = self._render(content="Hi", show_delay=500, hide_delay=250)
        assert 'data-dz-delay="500"' in html
        assert 'data-dz-hide-delay="250"' in html

    def test_default_delays(self) -> None:
        html = self._render(content="Hi")
        assert 'data-dz-delay="200"' in html
        assert 'data-dz-hide-delay="100"' in html

    def test_both_hover_and_focus_triggers(self) -> None:
        """Gate 5: keyboard accessibility requires focus triggers."""
        html = self._render(content="Label")
        assert '@mouseenter="show()"' in html
        assert '@mouseleave="hide()"' in html
        assert '@focusin="show()"' in html
        assert '@focusout="hide()"' in html

    def test_content_is_autoescaped(self) -> None:
        """Gate 3: content must be HTML-escaped, not passed through | safe.

        Prior to cycle 241 the fragment rendered ``{{ content | safe }}``
        which is an XSS vector if a DSL author passes a value from any
        untrusted source. The modernised fragment drops ``| safe`` and
        Jinja's autoescape handles the rest.
        """
        dangerous = "<script>alert('xss')</script>"
        html = self._render(content=dangerous)
        # The raw <script> tag MUST NOT appear — it should be escaped
        assert "<script>" not in html
        # The escaped form SHOULD appear
        assert "&lt;script&gt;" in html or "&lt;" in html

    def test_trigger_block_allows_html(self) -> None:
        """The trigger IS allowed to pass HTML (via | safe in the block).

        Triggers are intentionally markup (a button with nested icon);
        callers are responsible for the trigger's shape. Only content
        is autoescaped.
        """
        html = self._render(content="Tip", trigger='<button class="icon"><svg></svg></button>')
        assert '<button class="icon">' in html
        assert "<svg>" in html


class TestXCloakCSSRule:
    """Framework CSS has the `[x-cloak] { display: none !important; }` rule.

    Cycle 241 added this to `dazzle-layer.css` so the rich tooltip panel
    (and 4 other x-cloak consumers) don't flash on first paint.
    """

    def test_x_cloak_rule_present_in_framework_css(self) -> None:
        css_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "static"
            / "css"
            / "dazzle-layer.css"
        )
        content = css_path.read_text()
        # Both the selector and the !important declaration must be present
        assert "[x-cloak]" in content
        assert "display: none" in content
