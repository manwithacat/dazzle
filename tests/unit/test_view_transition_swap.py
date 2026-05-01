"""Tests for #974 — view-transition-name strip during htmx swap.

Background: `#main-content` carries `view-transition-name: main-content`
from `dz.css:184`. During an htmx morph swap of `#main-content`, both
the outgoing and incoming `<main id="main-content">` elements briefly
match the CSS rule simultaneously. The View Transitions API requires
unique transition names per snapshot — the duplicate causes the
snapshot to silently bail and Chrome to log a console error.

Fix: in `dz-islands.js`'s existing `htmx:beforeSwap` listener, set
`target.style.viewTransitionName = "none"` if the target is
`#main-content`. In the corresponding `htmx:afterSettle` listener,
restore by setting it back to `""` (empty string hands authority back
to the CSS cascade rule).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_ISLANDS = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-islands.js"


def test_strip_in_before_swap() -> None:
    """beforeSwap listener must clear viewTransitionName for #main-content."""
    js = DZ_ISLANDS.read_text()
    # Locate the beforeSwap listener.
    idx = js.find('"htmx:beforeSwap"')
    assert idx >= 0, "missing htmx:beforeSwap listener in dz-islands.js"
    # Read enough following code to capture the callback body.
    block = js[idx : idx + 2000]
    assert "main-content" in block, (
        "beforeSwap listener must check for #main-content (the target "
        "with the view-transition-name CSS rule)."
    )
    assert "viewTransitionName" in block, (
        "beforeSwap listener must clear `viewTransitionName` to avoid "
        "the duplicate-name collision during swap (#974)."
    )
    # The strip must use "none" — empty string would not actually
    # cancel the inherited CSS rule.
    assert '"none"' in block or "'none'" in block, (
        "beforeSwap must set viewTransitionName to 'none' (empty string "
        "would not override the CSS cascade rule)."
    )


def test_restore_in_after_settle() -> None:
    """afterSettle listener must restore viewTransitionName for #main-content."""
    js = DZ_ISLANDS.read_text()
    idx = js.find('"htmx:afterSettle"')
    assert idx >= 0, "missing htmx:afterSettle listener in dz-islands.js"
    block = js[idx : idx + 2000]
    assert "main-content" in block, (
        "afterSettle listener must check for #main-content to restore the cleared transition name."
    )
    assert "viewTransitionName" in block, (
        "afterSettle listener must reset `viewTransitionName` so the CSS "
        "rule resumes governing the element after the swap settles (#974)."
    )
    # Restoration is via empty string — hands authority back to CSS.
    # Look for `viewTransitionName = ""` (or '').
    assert 'viewTransitionName = ""' in block or "viewTransitionName = ''" in block, (
        'afterSettle must reset viewTransitionName to empty string (`""`) '
        "to hand authority back to the CSS cascade. Setting to 'main-content' "
        "directly would inline-pin it and miss future CSS rule updates."
    )
