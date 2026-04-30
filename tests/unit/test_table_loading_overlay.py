"""Tests for #972 — table loading overlay uses CSS, not Alpine x-show.

Background: pre-#972 the `.dz-table-loading` overlay used
`x-show="loading"` against the ancestor `dzTable()` x-data scope. On
htmx morph or Alpine init-order edge cases, the binding evaluated
before the parent scope was established, throwing
`loading is not defined` — same failure mode as #970.

Fix per ADR-0022: replace Alpine binding with pure CSS keyed off
htmx's `.htmx-request` class. htmx applies that class to the
`hx-indicator` element (the SR-only `#{table_id}-loading-sr` inside
`.dz-table`); the `:has()` selector lets us show the overlay from any
descendant trigger.

Also pinning the `display: none` default — without it, the overlay
flashes on initial paint before Alpine x-cloak previously suppressed
it.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "components" / "filterable_table.html"
CSS = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css" / "components" / "table.css"


def test_overlay_no_alpine_x_show() -> None:
    """The .dz-table-loading element must not carry x-show / x-cloak / x-transition."""
    html = TEMPLATE.read_text()
    # Locate the loading overlay div.
    idx = html.find('class="dz-table-loading"')
    assert idx >= 0, "missing .dz-table-loading element"
    # Walk back to the opening <div for that element.
    open_idx = html.rfind("<div", 0, idx)
    assert open_idx >= 0
    # Slice the opening tag.
    close_idx = html.find(">", open_idx)
    overlay_tag = html[open_idx : close_idx + 1]
    forbidden = ("x-show", "x-cloak", "x-transition")
    for attr in forbidden:
        assert attr not in overlay_tag, (
            f".dz-table-loading carries `{attr}` — this re-introduces the "
            f"#972 morph race. Use pure CSS keyed off `.htmx-request` "
            f"instead.\nOffending tag: {overlay_tag!r}"
        )


def test_css_default_hidden() -> None:
    """`.dz-table-loading` rule must default to `display: none`."""
    css = CSS.read_text()
    start = css.find(".dz-table-loading {")
    assert start >= 0
    end = css.find("}", start)
    block = css[start:end]
    assert "display: none" in block, (
        ".dz-table-loading must default to `display: none` so it doesn't "
        "flash on initial paint (#972 / replaces Alpine's x-cloak guard)."
    )


def test_css_reveals_on_htmx_request() -> None:
    """A rule keyed off `.htmx-request` must reveal the overlay."""
    css = CSS.read_text()
    # Look for `.dz-table:has(.htmx-request) .dz-table-loading` (or a
    # close variant — the test is intentionally tolerant on the exact
    # selector form, just requires the htmx-request hook).
    has_rule = ":has(.htmx-request)" in css and ".dz-table-loading" in css
    assert has_rule, (
        "Missing the `.dz-table:has(.htmx-request) .dz-table-loading` "
        "(or equivalent) rule that reveals the overlay during in-flight "
        "htmx requests (#972)."
    )
    # And the rule must set display: flex (or block) — i.e. something
    # that makes the overlay visible.
    rule_start = css.find(":has(.htmx-request)")
    rule_end = css.find("}", rule_start)
    rule_body = css[rule_start:rule_end]
    assert "display: flex" in rule_body or "display: block" in rule_body, (
        "The .htmx-request rule must set the overlay to display: flex "
        "(or block) to reveal it (#972)."
    )
