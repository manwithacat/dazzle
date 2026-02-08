"""Tests for viewport auto-fix suggestions."""

from __future__ import annotations

from dazzle.testing.viewport import ViewportAssertion, ViewportAssertionResult
from dazzle.testing.viewport_suggestions import (
    SUGGESTION_TABLE,
    VIEWPORT_TO_TAILWIND_PREFIX,
    suggest_fix,
    suggest_fixes_for_report,
)


class TestSuggestFix:
    """Tests for suggest_fix()."""

    def test_display_grid_mobile(self) -> None:
        result = suggest_fix(".grid", "display", "grid", "block", "mobile")
        assert result is not None
        assert result.suggested_class == "grid"
        assert result.confidence == "high"

    def test_display_grid_tablet(self) -> None:
        result = suggest_fix(".grid", "display", "grid", "block", "tablet")
        assert result is not None
        assert result.suggested_class == "sm:grid"

    def test_display_grid_desktop(self) -> None:
        result = suggest_fix(".grid", "display", "grid", "block", "desktop")
        assert result is not None
        assert result.suggested_class == "lg:grid"

    def test_display_grid_wide(self) -> None:
        result = suggest_fix(".grid", "display", "grid", "block", "wide")
        assert result is not None
        assert result.suggested_class == "xl:grid"

    def test_display_none(self) -> None:
        result = suggest_fix(".el", "display", "none", "block", "tablet")
        assert result is not None
        assert result.suggested_class == "sm:hidden"

    def test_display_flex(self) -> None:
        result = suggest_fix(".el", "display", "flex", "block", "desktop")
        assert result is not None
        assert result.suggested_class == "lg:flex"

    def test_grid_cols_2(self) -> None:
        result = suggest_fix(
            ".grid",
            "grid-template-columns",
            "repeat(2, minmax(0, 1fr))",
            "1fr",
            "tablet",
        )
        assert result is not None
        assert result.suggested_class == "sm:grid-cols-2"
        assert result.confidence == "medium"

    def test_grid_cols_3(self) -> None:
        result = suggest_fix(
            ".grid",
            "grid-template-columns",
            "repeat(3, minmax(0, 1fr))",
            "1fr",
            "desktop",
        )
        assert result is not None
        assert result.suggested_class == "lg:grid-cols-3"

    def test_flex_direction_column(self) -> None:
        result = suggest_fix(".stats", "flex-direction", "column", "row", "mobile")
        assert result is not None
        assert result.suggested_class == "flex-col"

    def test_flex_direction_row(self) -> None:
        result = suggest_fix(".stats", "flex-direction", "row", "column", "desktop")
        assert result is not None
        assert result.suggested_class == "lg:flex-row"

    def test_visibility_hidden(self) -> None:
        result = suggest_fix(".el", "visibility", "hidden", "visible", "mobile")
        assert result is not None
        assert result.suggested_class == "invisible"
        assert result.confidence == "high"

    def test_visibility_visible(self) -> None:
        result = suggest_fix(".el", "visibility", "visible", "hidden", "desktop")
        assert result is not None
        assert result.suggested_class == "lg:visible"

    def test_no_suggestion_for_unknown_property(self) -> None:
        result = suggest_fix(".el", "font-size", "16px", "14px", "mobile")
        assert result is None

    def test_no_suggestion_when_actual_is_none(self) -> None:
        result = suggest_fix(".el", "display", "grid", None, "mobile")
        assert result is None

    def test_expected_as_list_uses_first(self) -> None:
        result = suggest_fix(".el", "display", ["grid", "inline-grid"], "block", "tablet")
        assert result is not None
        assert result.suggested_class == "sm:grid"


class TestViewportPrefixMapping:
    """Tests for VIEWPORT_TO_TAILWIND_PREFIX."""

    def test_mobile_has_no_prefix(self) -> None:
        assert VIEWPORT_TO_TAILWIND_PREFIX["mobile"] == ""

    def test_tablet_prefix(self) -> None:
        assert VIEWPORT_TO_TAILWIND_PREFIX["tablet"] == "sm:"

    def test_desktop_prefix(self) -> None:
        assert VIEWPORT_TO_TAILWIND_PREFIX["desktop"] == "lg:"

    def test_wide_prefix(self) -> None:
        assert VIEWPORT_TO_TAILWIND_PREFIX["wide"] == "xl:"


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
