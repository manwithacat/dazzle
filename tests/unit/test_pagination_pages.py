"""Tests for the ellipsis-collapsed pagination helper (#984).

`pagination_pages(current, total, window=2)` returns a list of page numbers
interleaved with `None` markers representing ellipses. The output length is
bounded so the rendered pagination row stays narrow regardless of how many
pages a table has.
"""

from __future__ import annotations

from dazzle_ui.runtime.template_renderer import _pagination_pages


class TestSmallTotals:
    """Below the ellipsis threshold, every page is rendered explicitly."""

    def test_zero_pages_returns_empty(self) -> None:
        assert _pagination_pages(1, 0) == []

    def test_one_page_returns_just_one(self) -> None:
        assert _pagination_pages(1, 1) == [1]

    def test_three_pages_no_ellipsis(self) -> None:
        assert _pagination_pages(2, 3) == [1, 2, 3]

    def test_seven_pages_no_ellipsis_default_window(self) -> None:
        # threshold = 2*window+5 = 9 → up to 9 pages render explicit
        assert _pagination_pages(4, 7) == [1, 2, 3, 4, 5, 6, 7]

    def test_nine_pages_at_threshold_no_ellipsis(self) -> None:
        assert _pagination_pages(5, 9) == [1, 2, 3, 4, 5, 6, 7, 8, 9]


class TestEllipsisCollapse:
    """Above the threshold, the helper inserts `None` ellipsis markers."""

    def test_current_in_middle_emits_two_ellipses(self) -> None:
        # current=7, window=2 → window pages 5..9, ellipses on both sides
        assert _pagination_pages(7, 120) == [1, None, 5, 6, 7, 8, 9, None, 120]

    def test_current_near_start_left_window_collapses(self) -> None:
        # current=3, window=2 → window 2..5; left ellipsis suppressed since
        # win_start <= 2 (page 2 is in the window).
        assert _pagination_pages(3, 120) == [1, 2, 3, 4, 5, None, 120]

    def test_current_near_end_right_window_collapses(self) -> None:
        # current=118, window=2, total=120 → window 116..119; right ellipsis
        # suppressed since win_end == total-1 (page 119 already included).
        assert _pagination_pages(118, 120) == [1, None, 116, 117, 118, 119, 120]

    def test_current_is_first_page(self) -> None:
        # current=1 → window clamps to [2, 3]; left ellipsis suppressed.
        assert _pagination_pages(1, 120) == [1, 2, 3, None, 120]

    def test_current_is_last_page(self) -> None:
        # current=120, total=120 → window 118..119; right ellipsis
        # suppressed since 119 == total-1.
        assert _pagination_pages(120, 120) == [1, None, 118, 119, 120]


class TestBoundedOutput:
    """The rendered list length must stay bounded regardless of total pages."""

    def test_thousand_pages_bounded(self) -> None:
        result = _pagination_pages(500, 1000)
        # 1 + ellipsis + (2*window+1 = 5) + ellipsis + 1 = 9 entries max
        assert len(result) == 9
        assert result[0] == 1
        assert result[-1] == 1000
        assert None in result

    def test_million_pages_bounded(self) -> None:
        # The whole point of the helper — rendered width does not grow with
        # total page count. The original bug reported a 5,652px row at 120
        # pages; with this helper, 1,000,000 pages still render the same
        # ~9-entry row.
        result = _pagination_pages(500_000, 1_000_000)
        assert len(result) == 9


class TestWindowParameter:
    """The window parameter widens or narrows the around-current range."""

    def test_window_one_shows_only_immediate_neighbours(self) -> None:
        # window=1 → window of 3 pages around current
        # threshold = 2*1+5 = 7 → 8 pages should already collapse
        assert _pagination_pages(5, 8, window=1) == [1, None, 4, 5, 6, None, 8]

    def test_window_three_widens_visible_range(self) -> None:
        assert _pagination_pages(10, 100, window=3) == [
            1,
            None,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            None,
            100,
        ]
