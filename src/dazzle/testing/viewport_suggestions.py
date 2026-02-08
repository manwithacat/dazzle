"""Auto-fix suggestions for viewport assertion failures.

When a CSS assertion fails, suggests the Tailwind class that would fix it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.testing.viewport import ViewportAssertionResult


@dataclass
class ViewportSuggestion:
    """A suggested Tailwind CSS fix for a failed viewport assertion."""

    selector: str
    current_issue: str  # "display is 'block' but expected 'grid'"
    suggested_class: str  # "sm:grid"
    explanation: str  # "Add responsive grid class at sm breakpoint"
    confidence: str  # "high" | "medium" | "low"


VIEWPORT_TO_TAILWIND_PREFIX: dict[str, str] = {
    "mobile": "",
    "tablet": "sm:",
    "desktop": "lg:",
    "wide": "xl:",
}

SUGGESTION_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("display", "grid"): ("grid", "Add grid display"),
    ("display", "flex"): ("flex", "Add flex display"),
    ("display", "none"): ("hidden", "Hide element"),
    ("display", "block"): ("block", "Show as block"),
    ("grid-template-columns", "repeat(2, minmax(0, 1fr))"): ("grid-cols-2", "Set 2-column grid"),
    ("grid-template-columns", "repeat(3, minmax(0, 1fr))"): ("grid-cols-3", "Set 3-column grid"),
    ("grid-template-columns", "1fr"): ("grid-cols-1", "Set single-column grid"),
    ("flex-direction", "column"): ("flex-col", "Stack vertically"),
    ("flex-direction", "row"): ("flex-row", "Arrange horizontally"),
    ("visibility", "hidden"): ("invisible", "Hide visually"),
    ("visibility", "visible"): ("visible", "Make visible"),
}


def suggest_fix(
    selector: str,
    property: str,
    expected: str | list[str],
    actual: str | None,
    viewport: str,
) -> ViewportSuggestion | None:
    """Suggest a Tailwind class to fix a failed assertion.

    Parameters
    ----------
    selector:
        CSS selector that failed.
    property:
        CSS property name (e.g. "display", "grid-template-columns").
    expected:
        Expected value(s).
    actual:
        Actual computed value (may be ``None`` if element not found).
    viewport:
        Viewport name from VIEWPORT_MATRIX.

    Returns
    -------
    ViewportSuggestion or None
        A suggestion if one can be determined, else ``None``.
    """
    if actual is None:
        return None

    prefix = VIEWPORT_TO_TAILWIND_PREFIX.get(viewport, "")

    # Normalise expected to a single target value for lookup
    target = expected if isinstance(expected, str) else expected[0] if expected else None
    if target is None:
        return None

    key = (property, target)
    entry = SUGGESTION_TABLE.get(key)
    if entry is None:
        return None

    tw_class, explanation = entry
    suggested = f"{prefix}{tw_class}"

    # Determine confidence
    confidence = "high" if property in ("display", "visibility") else "medium"

    return ViewportSuggestion(
        selector=selector,
        current_issue=f"{property} is {actual!r} but expected {target!r}",
        suggested_class=suggested,
        explanation=f"{explanation} at {viewport} breakpoint",
        confidence=confidence,
    )


def suggest_fixes_for_report(
    results: list[ViewportAssertionResult],
) -> list[ViewportSuggestion]:
    """Generate suggestions for all failed assertions in a result list.

    Parameters
    ----------
    results:
        List of assertion results (typically from a single ViewportReport).

    Returns
    -------
    list[ViewportSuggestion]
        Suggestions for each failed assertion where a fix is known.
    """
    suggestions: list[ViewportSuggestion] = []
    for res in results:
        if res.passed:
            continue
        suggestion = suggest_fix(
            selector=res.assertion.selector,
            property=res.assertion.property,
            expected=res.assertion.expected,
            actual=res.actual,
            viewport=res.assertion.viewport,
        )
        if suggestion is not None:
            suggestions.append(suggestion)
    return suggestions
