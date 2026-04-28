"""Regression tests for `.dz-form-input` height + line-box (issue #930).

The pre-fix style (`height: 2rem` + `padding: 8px 12px` only) left
roughly 16px of vertical content area for a 22px line-box, clipping
descenders on every input + select placeholder. The fix uses
min-height + explicit line-height + padding-block so the line-box
always fits.

Pure CSS source-grep tests — no rendered-pixel comparison. The values
asserted here are what guarantee the line-box fits given the cascade
defaults (--text-sm font-size, line-height: 1.4).
"""

from pathlib import Path

CSS_PATH = Path("src/dazzle_ui/runtime/static/css/components/form.css")


def _read_block(start_marker: str, max_chars: int = 800) -> str:
    """Return the CSS rule body that starts with `start_marker`."""
    css = CSS_PATH.read_text()
    idx = css.index(start_marker)
    return css[idx : idx + max_chars]


class TestFormInputHeight:
    """The canonical input class must size itself to fit a 1.4 line-height."""

    def test_input_uses_min_height_not_fixed_height(self) -> None:
        block = _read_block(".dz-form-input {")
        assert "min-height: 2.5rem" in block
        # Fixed 2rem height was the cause of the descender clip — must be gone.
        # (`height: auto` is fine; `height: 2rem` is not.)
        assert "height: 2rem;" not in block

    def test_input_declares_explicit_line_height(self) -> None:
        block = _read_block(".dz-form-input {")
        assert "line-height: 1.4" in block

    def test_input_has_padding_block(self) -> None:
        """Vertical padding gives the line-box room above + below the
        glyph baseline; without it the descender still kisses the border
        even at 40px height."""
        block = _read_block(".dz-form-input {")
        assert "padding-block:" in block

    def test_money_prefix_aligns_with_input_height(self) -> None:
        """The currency prefix sits flush against the amount input —
        if its height drifts, the visual seam breaks."""
        block = _read_block(".dz-form-money-prefix {")
        assert "min-height: 2.5rem" in block

    def test_money_select_aligns_with_input_height(self) -> None:
        block = _read_block(".dz-form-money-select {")
        assert "min-height: 2.5rem" in block
        assert "line-height: 1.4" in block
