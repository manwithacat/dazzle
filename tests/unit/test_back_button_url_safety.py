"""Tests for #981 — Back button onclick guards `new URL(document.referrer)`.

Background: `components/detail_view.html` Back button's inline onclick
called `new URL(document.referrer)` without a try/catch. When
`document.referrer` is empty (BFCache restore, direct page load,
cross-origin nav with referrer policy stripping it) the constructor
throws `TypeError: URL is not a constructor` (Chromium's wording for
"failed to construct URL"). Site-fuzz captured these as page errors.

Fix: wrap the `new URL(...)` call in a try/catch. The catch is a no-op —
fall through to the default `<a href>` navigation which is the right
behaviour when same-origin detection fails.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DETAIL_VIEW = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "components" / "detail_view.html"


def test_back_button_wraps_url_in_try_catch() -> None:
    """The Back button onclick must wrap `new URL(...)` in try/catch."""
    html = DETAIL_VIEW.read_text()
    # Find the Back button's onclick attribute.
    idx = html.find("&larr; Back")
    assert idx >= 0, "missing Back button"
    # Walk back to the surrounding <a> tag.
    open_idx = html.rfind("<a", 0, idx)
    close_idx = html.find(">", open_idx)
    tag = html[open_idx : close_idx + 1]
    assert "new URL(" in tag, "Back button onclick should still use new URL"
    assert "try{" in tag and "catch(" in tag, (
        "Back button's `new URL(document.referrer)` call must be wrapped "
        "in try/catch — empty / opaque referrers throw and surface as "
        "page-error (#981)."
    )


def test_url_call_inside_try_block() -> None:
    """The try{} must actually contain the new URL() call (not be vestigial)."""
    html = DETAIL_VIEW.read_text()
    idx = html.find("&larr; Back")
    open_idx = html.rfind("<a", 0, idx)
    close_idx = html.find(">", open_idx)
    tag = html[open_idx : close_idx + 1]
    # The try{ must come before the new URL( — ordering check, not
    # just presence-check.
    try_idx = tag.find("try{")
    url_idx = tag.find("new URL(")
    catch_idx = tag.find("catch(")
    assert try_idx >= 0 and url_idx >= 0 and catch_idx >= 0
    assert try_idx < url_idx < catch_idx, (
        "Layout must be: try { ... new URL(...) ... } catch(e) { ... }. "
        "Current order doesn't protect the URL call (#981)."
    )
