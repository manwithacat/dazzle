"""Tests for viewport auto-fix suggestions."""

from typing import Any

import pytest

from dazzle.testing.viewport import ViewportAssertion, ViewportAssertionResult
from dazzle.testing.viewport_suggestions import (
    SUGGESTION_TABLE,
    VIEWPORT_TO_TAILWIND_PREFIX,
    suggest_fix,
    suggest_fixes_for_report,
)


class TestSuggestFix:
    """Tests for suggest_fix() — verifies suggested Tailwind class and optional confidence."""

    @pytest.mark.parametrize(
        "selector,prop,expected,actual,viewport,suggested_class,confidence",
        [
            # display: grid across viewports
            (".grid", "display", "grid", "block", "mobile", "grid", "high"),
            (".grid", "display", "grid", "block", "tablet", "sm:grid", None),
            (".grid", "display", "grid", "block", "desktop", "lg:grid", None),
            (".grid", "display", "grid", "block", "wide", "xl:grid", None),
            # display: none / flex
            (".el", "display", "none", "block", "tablet", "sm:hidden", None),
            (".el", "display", "flex", "block", "desktop", "lg:flex", None),
            # grid-template-columns
            (
                ".grid",
                "grid-template-columns",
                "repeat(2, minmax(0, 1fr))",
                "1fr",
                "tablet",
                "sm:grid-cols-2",
                "medium",
            ),
            (
                ".grid",
                "grid-template-columns",
                "repeat(3, minmax(0, 1fr))",
                "1fr",
                "desktop",
                "lg:grid-cols-3",
                None,
            ),
            # flex-direction
            (".stats", "flex-direction", "column", "row", "mobile", "flex-col", None),
            (".stats", "flex-direction", "row", "column", "desktop", "lg:flex-row", None),
            # visibility
            (".el", "visibility", "hidden", "visible", "mobile", "invisible", "high"),
            (".el", "visibility", "visible", "hidden", "desktop", "lg:visible", None),
            # expected as list — uses first element
            (".el", "display", ["grid", "inline-grid"], "block", "tablet", "sm:grid", None),
        ],
        ids=[
            "test_display_grid_mobile",
            "test_display_grid_tablet",
            "test_display_grid_desktop",
            "test_display_grid_wide",
            "test_display_none",
            "test_display_flex",
            "test_grid_cols_2",
            "test_grid_cols_3",
            "test_flex_direction_column",
            "test_flex_direction_row",
            "test_visibility_hidden",
            "test_visibility_visible",
            "test_expected_as_list_uses_first",
        ],
    )
    def test_suggest_fix(
        self,
        selector: str,
        prop: str,
        expected: Any,
        actual: str | None,
        viewport: str,
        suggested_class: str,
        confidence: str | None,
    ) -> None:
        """suggest_fix returns the expected Tailwind class (and confidence when specified)."""
        result = suggest_fix(selector, prop, expected, actual, viewport)
        assert result is not None
        assert result.suggested_class == suggested_class
        if confidence is not None:
            assert result.confidence == confidence

    @pytest.mark.parametrize(
        "selector,prop,expected,actual,viewport",
        [
            # Unknown CSS property has no Tailwind mapping
            (".el", "font-size", "16px", "14px", "mobile"),
            # actual=None means no baseline to compare against
            (".el", "display", "grid", None, "mobile"),
        ],
        ids=[
            "test_no_suggestion_for_unknown_property",
            "test_no_suggestion_when_actual_is_none",
        ],
    )
    def test_suggest_fix_returns_none(
        self,
        selector: str,
        prop: str,
        expected: Any,
        actual: str | None,
        viewport: str,
    ) -> None:
        """suggest_fix returns None when no suggestion is available."""
        result = suggest_fix(selector, prop, expected, actual, viewport)
        assert result is None


class TestViewportPrefixMapping:
    """Tests for VIEWPORT_TO_TAILWIND_PREFIX."""

    @pytest.mark.parametrize(
        ("viewport_key", "expected_prefix"),
        [("mobile", ""), ("tablet", "sm:"), ("desktop", "lg:"), ("wide", "xl:")],
        ids=[
            "test_mobile_has_no_prefix",
            "test_tablet_prefix",
            "test_desktop_prefix",
            "test_wide_prefix",
        ],
    )
    def test_viewport_prefix_mapping(self, viewport_key: str, expected_prefix: str) -> None:
        assert VIEWPORT_TO_TAILWIND_PREFIX[viewport_key] == expected_prefix


class TestSuggestFixesForReport:
    """Tests for suggest_fixes_for_report()."""

    def _make_result(
        self,
        passed: bool,
        prop: str = "display",
        expected: str = "grid",
        actual: str | None = "block",
        viewport: str = "mobile",
    ) -> ViewportAssertionResult:
        return ViewportAssertionResult(
            assertion=ViewportAssertion(
                selector=".test",
                property=prop,
                expected=expected,
                viewport=viewport,
                description="test assertion",
            ),
            actual=actual,
            passed=passed,
        )

    def test_skips_passed(self) -> None:
        results = [self._make_result(passed=True)]
        suggestions = suggest_fixes_for_report(results)
        assert suggestions == []

    def test_generates_for_failed(self) -> None:
        results = [self._make_result(passed=False)]
        suggestions = suggest_fixes_for_report(results)
        assert len(suggestions) == 1
        assert suggestions[0].suggested_class == "grid"

    def test_no_suggestion_for_unknown(self) -> None:
        results = [
            self._make_result(passed=False, prop="font-size", expected="16px", actual="14px")
        ]
        suggestions = suggest_fixes_for_report(results)
        assert suggestions == []

    def test_mixed_results(self) -> None:
        results = [
            self._make_result(passed=True),
            self._make_result(passed=False),
            self._make_result(passed=False, prop="visibility", expected="hidden", actual="visible"),
        ]
        suggestions = suggest_fixes_for_report(results)
        assert len(suggestions) == 2


class TestSuggestionTable:
    """Tests for SUGGESTION_TABLE coverage."""

    def test_all_entries_have_class_and_explanation(self) -> None:
        for _key, (tw_class, explanation) in SUGGESTION_TABLE.items():
            assert isinstance(tw_class, str) and tw_class
            assert isinstance(explanation, str) and explanation

    def test_known_entry_count(self) -> None:
        assert len(SUGGESTION_TABLE) == 11
