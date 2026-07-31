"""L2 layout concordance kit — browser-measured layout properties.

LAYER: L2 (see docs/superpowers/specs/2026-07-21-css-layout-test-architecture.md)

Prefer geometric predicates over CSS-source regex. Chromium is the CSS
grammar for cascade + table + flex; this package loads production CSS +
HTML fixtures and asserts box/style relationships.
"""

from tests.layout_kit.harness import (
    Box,
    LayoutSnapshot,
    LayoutState,
    dazzle_css_path,
    measure_selectors,
    render_layout,
)
from tests.layout_kit.predicates import (
    assert_multiword_chip_wider_than_icon,
    assert_no_ghost_flex_items,
    assert_shared_end,
    assert_strip_flex_end_full_width,
)

__all__ = [
    "Box",
    "LayoutSnapshot",
    "LayoutState",
    "assert_multiword_chip_wider_than_icon",
    "assert_no_ghost_flex_items",
    "assert_shared_end",
    "assert_strip_flex_end_full_width",
    "dazzle_css_path",
    "measure_selectors",
    "render_layout",
]
