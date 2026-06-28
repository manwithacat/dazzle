"""#1493 (UX-maturity 1b) slice 2 part 3 — WCAG colour+icon+text on badges.

A status badge must not convey state by colour alone (WCAG 1.4.1 Use of Color).
Every non-neutral tone now leads with a decorative glyph at all three badge
render seams (the render-layer `_render_status_badge_html`, the page detail
`_render_status_badge`, and the http htmx `_render_cell_display`). Neutral
carries no emphasis, so it stays icon-free — which also keeps the dominant
name-guess-miss badge byte-identical to the pre-#1493 output.
"""

from dazzle.render.filters import (
    badge_icon_html,
    infer_terminal_tone_map,
    resolve_status_icon,
    status_tone_map,
)

# The four non-neutral tones → their leading glyph (numeric HTML entity).
_EXPECTED = {
    "success": "&#10003;",
    "warning": "&#9888;",
    "destructive": "&#10005;",
    "info": "&#8505;",
}


class TestIconHelper:
    def test_each_non_neutral_tone_has_a_glyph(self):
        for tone, glyph in _EXPECTED.items():
            assert resolve_status_icon(tone) == glyph

    def test_neutral_and_unknown_have_no_glyph(self):
        assert resolve_status_icon("neutral") == ""
        assert resolve_status_icon("") == ""
        assert resolve_status_icon(None) == ""
        assert resolve_status_icon("not_a_tone") == ""

    def test_positive_alias_resolves_to_success_glyph(self):
        # `positive` is the declared alias for `success` (core.ir.tones).
        assert resolve_status_icon("positive") == _EXPECTED["success"]

    def test_badge_icon_html_wraps_glyph_in_decorative_span(self):
        html = badge_icon_html("warning")
        assert html == ('<span class="dz-badge-icon" aria-hidden="true">&#9888;</span>')

    def test_badge_icon_html_empty_for_neutral(self):
        assert badge_icon_html("neutral") == ""
        assert badge_icon_html(None) == ""


class TestRenderSeams:
    """All three badge seams emit the icon before the label for non-neutral
    tones, and stay icon-free (byte-unchanged) for neutral."""

    def test_render_shared_badge_html(self):
        from dazzle.render.fragment.region._shared import _render_status_badge_html

        html = _render_status_badge_html("approved")  # name-guess → success
        assert 'data-dz-tone="success"' in html
        # icon span immediately precedes the text label
        assert '<span class="dz-badge-icon" aria-hidden="true">&#10003;</span>Approved' in html

    def test_render_shared_badge_neutral_has_no_icon(self):
        from dazzle.render.fragment.region._shared import _render_status_badge_html

        html = _render_status_badge_html("draft")  # name-guess → neutral
        assert 'data-dz-tone="neutral"' in html
        assert "dz-badge-icon" not in html

    def test_detail_badge(self):
        from dazzle.page.runtime.detail_renderer import _render_status_badge

        html = _render_status_badge("rejected")  # name-guess → destructive
        assert 'data-dz-tone="destructive"' in html
        assert '<span class="dz-badge-icon" aria-hidden="true">&#10005;</span>Rejected' in html

    def test_detail_badge_neutral_unchanged(self):
        from dazzle.page.runtime.detail_renderer import _render_status_badge

        html = _render_status_badge("todo")  # neutral
        assert "dz-badge-icon" not in html

    def test_htmx_cell_badge(self):
        from dazzle.render.fragment.renderer._data_row import _render_cell_display

        html = _render_cell_display({"type": "badge"}, "pending")  # → warning
        assert 'data-dz-tone="warning"' in html
        assert "&#9888;" in html
        assert "dz-badge-icon" in html

    def test_htmx_cell_badge_neutral_unchanged(self):
        from dazzle.render.fragment.renderer._data_row import _render_cell_display

        html = _render_cell_display({"type": "badge"}, "draft")  # neutral
        assert "dz-badge-icon" not in html

    def test_declared_semantic_drives_icon(self):
        """A declared `semantic:` binding that overrides the name guess also
        drives the icon — e.g. a value the name-guess would call neutral but the
        app declares `success` gets the success glyph."""
        from dazzle.render.fragment.renderer._data_row import _render_cell_display

        col = {"type": "badge", "semantic_map": {"shipped": "success"}}
        html = _render_cell_display(col, "shipped")
        assert 'data-dz-tone="success"' in html
        assert "&#10003;" in html


class _FakeSM:
    def __init__(self, terminals):
        self._t = set(terminals)

    def terminal_states(self):
        return self._t


class _FakeKind:
    value = "enum"


class _FakeFieldType:
    kind = _FakeKind()
    enum_values = None
    enum_semantics = None


class TestSMTerminalInference:
    """#1493 slice 2 part 4 — the level-4 step: undeclared, name-guess-miss
    terminal states are inferred from the state-machine graph."""

    def test_unrecognised_terminal_inferred_success(self):
        m = infer_terminal_tone_map(_FakeSM(["archived_custom"]))
        assert m == {"archived_custom": "success"}

    def test_name_guess_terminals_are_skipped(self):
        # `done`/`cancelled` are already classified by the name guess (which
        # precedes inference), so the SM layer leaves them out.
        m = infer_terminal_tone_map(_FakeSM(["done", "cancelled", "weird_end"]))
        assert m == {"weird_end": "success"}

    def test_none_machine_is_empty(self):
        assert infer_terminal_tone_map(None) == {}

    def test_keys_normalised(self):
        m = infer_terminal_tone_map(_FakeSM(["Final Approval"]))
        assert m == {"final_approval": "success"}

    def test_status_tone_map_merges_declared_over_inference(self):
        # A declared binding always wins the merge, even for a terminal state.
        ft = _FakeFieldType()
        ft.enum_semantics = {"weird_end": "warning"}
        merged = status_tone_map(ft, None, _FakeSM(["weird_end"]))
        assert merged["weird_end"] == "warning"  # declared, not the SM `success`

    def test_status_tone_map_inference_only_when_undeclared(self):
        ft = _FakeFieldType()  # no enum_semantics declared
        merged = status_tone_map(ft, None, _FakeSM(["weird_end"]))
        assert merged == {"weird_end": "success"}

    def test_status_tone_map_no_machine_is_declared_only(self):
        ft = _FakeFieldType()
        ft.enum_semantics = {"open": "info"}
        assert status_tone_map(ft, None, None) == {"open": "info"}
