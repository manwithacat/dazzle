"""Tests for the ellipsis-collapsed pagination helper (#984).

`pagination_pages(current, total, window=2)` returns a list of page numbers
interleaved with `None` markers representing ellipses. The output length is
bounded so the rendered pagination row stays narrow regardless of how many
pages a table has.
"""

from __future__ import annotations

import pytest

from dazzle.render.filters import _pagination_pages


class TestSmallTotals:
    """Below the ellipsis threshold, every page is rendered explicitly."""

    @pytest.mark.parametrize(
        ("current", "total", "expected"),
        [
            (1, 0, []),
            (1, 1, [1]),
            (2, 3, [1, 2, 3]),
            (4, 7, [1, 2, 3, 4, 5, 6, 7]),
            (5, 9, [1, 2, 3, 4, 5, 6, 7, 8, 9]),
        ],
        ids=[
            "test_zero_pages_returns_empty",
            "test_one_page_returns_just_one",
            "test_three_pages_no_ellipsis",
            "test_seven_pages_no_ellipsis_default_window",
            "test_nine_pages_at_threshold_no_ellipsis",
        ],
    )
    def test_small_total(self, current: int, total: int, expected: list) -> None:
        assert _pagination_pages(current, total) == expected


class TestEllipsisCollapse:
    """Above the threshold, the helper inserts `None` ellipsis markers."""

    @pytest.mark.parametrize(
        ("current", "total", "expected"),
        [
            # current=7, window=2 → window pages 5..9, ellipses on both sides
            (7, 120, [1, None, 5, 6, 7, 8, 9, None, 120]),
            # current=3, window=2 → window 2..5; left ellipsis suppressed since win_start <= 2
            (3, 120, [1, 2, 3, 4, 5, None, 120]),
            # current=118, window=2, total=120 → right ellipsis suppressed since win_end==total-1
            (118, 120, [1, None, 116, 117, 118, 119, 120]),
            # current=1 → window clamps to [2, 3]; left ellipsis suppressed
            (1, 120, [1, 2, 3, None, 120]),
            # current=120, total=120 → window 118..119; right ellipsis suppressed
            (120, 120, [1, None, 118, 119, 120]),
        ],
        ids=[
            "test_current_in_middle_emits_two_ellipses",
            "test_current_near_start_left_window_collapses",
            "test_current_near_end_right_window_collapses",
            "test_current_is_first_page",
            "test_current_is_last_page",
        ],
    )
    def test_ellipsis_collapse(self, current: int, total: int, expected: list) -> None:
        assert _pagination_pages(current, total) == expected


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
