"""#1842 client-side a11y (cyfuture WCAG 2.2 audit), driven in Chromium.

* Rich-text toolbar (1.1.1 / 4.1.2): every button is named by a word via
  ``aria-label``, its glyph is ``aria-hidden``, ``title`` leads with the
  same word (not the raw command name), and the roving tabindex holds.
* Workspace Save (4.1.3): "Saving…", "Saved" and the failure reason are
  announced through the builder's live region; the button turns
  ``aria-disabled`` (never ``disabled``) so it keeps focus; a second click
  while saving does not PUT again; the error is visible text the button
  references with ``aria-describedby``.

The scripts run against real SSR markup (``WorkspaceToolbar``) on a
``set_content`` page. Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dazzle.render.fragment import FragmentRenderer, WorkspaceToolbar  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
JS = REPO_ROOT / "src/dazzle/page/runtime/static/js"


@pytest.fixture(scope="module")
def page() -> Any:
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page()
        yield pg
        browser.close()


_RICHTEXT_PAGE = """<!doctype html><html><body>
<label><span class="dz-field__label">Notes</span>
<div class="dz-form-richtext" data-host>
  <div data-dz-editor></div>
  <textarea id="notes" name="notes"></textarea>
</div></label>
<script>window.dz = {bridge: {registerWidget: function (n, d) { window.__rt = d; }}};</script>
</body></html>"""

_EXPECTED_NAMES = {
    "bold": "Bold",
    "italic": "Italic",
    "underline": "Underline",
    "h2": "Heading 2",
    "h3": "Heading 3",
    "ul": "Bulleted list",
    "ol": "Numbered list",
    "link": "Link",
    "clear": "Clear formatting",
}


def test_richtext_toolbar_buttons_are_named_by_words(page: Any) -> None:
    page.set_content(_RICHTEXT_PAGE)
    # By path, not inline: the source mentions `</script>` in a comment.
    page.add_script_tag(path=str(JS / "dz-richtext.js"))
    page.evaluate('window.__rt.mount(document.querySelector("[data-host]"), {})')
    buttons = page.eval_on_selector_all(
        "[data-dz-richtext-toolbar] button[data-cmd]",
        """bs => bs.map(b => ({
            cmd: b.dataset.cmd,
            label: b.getAttribute("aria-label"),
            title: b.title,
            tabindex: b.getAttribute("tabindex"),
            glyphHidden: [...b.childNodes].every(
                n => n.nodeType === 1 && n.getAttribute("aria-hidden") === "true"),
        }))""",
    )
    assert {b["cmd"]: b["label"] for b in buttons} == _EXPECTED_NAMES
    for b in buttons:
        assert b["glyphHidden"], f"{b['cmd']}: glyph must be aria-hidden"
        assert b["title"].startswith(b["label"] + " (Ctrl+"), b
    # Roving tabindex: one tab stop, ArrowRight moves it.
    assert [b["tabindex"] for b in buttons].count("0") == 1
    page.focus("[data-dz-richtext-toolbar] button[data-cmd='bold']")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.dataset.cmd") == "italic"
    assert page.get_attribute("button[data-cmd='italic']", "tabindex") == "0"
    assert page.get_attribute("button[data-cmd='bold']", "tabindex") == "-1"


def _builder_page() -> str:
    toolbar = FragmentRenderer().render(WorkspaceToolbar())
    return (
        "<!doctype html><html><body>"
        f'<div data-dz-dashboard-builder data-workspace-name="ops">{toolbar}</div>'
        # A PUT that waits for the test to settle it, and counts calls.
        "<script>window.__puts = 0; window.__settle = null;"
        "window.fetch = function () { window.__puts += 1;"
        " return new Promise(function (res) { window.__settle = res; }); };</script>"
        "</body></html>"
    )


def _state(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const b = document.querySelector(".dz-workspace-save");
            const err = document.querySelector("[data-dz-save-error]");
            const live = document.getElementById("dz-live-region");
            return {
                state: b.getAttribute("data-dz-save-state"),
                disabled: b.disabled,
                ariaDisabled: b.getAttribute("aria-disabled"),
                focused: document.activeElement === b,
                title: b.getAttribute("title"),
                describedby: b.getAttribute("aria-describedby"),
                errId: err && err.id,
                errText: err && err.textContent,
                errVisible: !!err && err.getBoundingClientRect().width > 1,
                live: live && live.textContent,
                liveHidden: !!live && live.getBoundingClientRect().width <= 1,
                puts: window.__puts,
            };
        }"""
    )


def _load_builder(page: Any) -> None:
    page.set_content(_builder_page())
    page.add_script_tag(path=str(JS / "dashboard-builder.js"))


def test_workspace_save_announces_and_keeps_focus(page: Any) -> None:
    _load_builder(page)
    page.add_style_tag(
        content=".visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;"
        "clip-path:inset(50%)}"
    )
    page.evaluate(
        "document.querySelector('[data-dz-dashboard-builder]')._dzBuilder.saveState = 'dirty'"
    )
    page.focus(".dz-workspace-save")
    page.click(".dz-workspace-save")
    s = _state(page)
    assert s["state"] == "saving"
    assert (s["disabled"], s["ariaDisabled"], s["focused"]) == (False, "true", True)
    assert s["live"] == "Saving layout…"
    # Double-submit guard: a second click while saving does not PUT again
    # (force: Playwright itself refuses to click an aria-disabled button).
    page.click(".dz-workspace-save", force=True)
    assert _state(page)["puts"] == 1

    page.evaluate("window.__settle({ok: true, status: 200})")
    page.wait_for_function(
        "document.querySelector('.dz-workspace-save').dataset.dzSaveState === 'saved'"
    )
    s = _state(page)
    assert s["live"] == "Layout saved"
    assert (s["ariaDisabled"], s["focused"]) == ("true", True)
    assert s["liveHidden"], "the live region must be visually hidden"


def test_workspace_save_error_is_visible_and_described(page: Any) -> None:
    _load_builder(page)
    page.evaluate(
        "document.querySelector('[data-dz-dashboard-builder]')._dzBuilder.saveState = 'dirty'"
    )
    page.click(".dz-workspace-save")
    page.evaluate("window.__settle({ok: false, status: 503})")
    page.wait_for_function(
        "document.querySelector('.dz-workspace-save').dataset.dzSaveState === 'error'"
    )
    s = _state(page)
    assert s["ariaDisabled"] == "false" and s["focused"]
    assert s["title"] is None, "the reason is no longer hidden in title"
    assert s["errVisible"] and s["errText"] == "Not saved: Server returned 503"
    assert s["describedby"] == s["errId"]
    assert s["live"] == "Layout not saved: Server returned 503"

    # Retry succeeds: the error text and the reference go away.
    page.click(".dz-workspace-save")
    page.evaluate("window.__settle({ok: true, status: 200})")
    page.wait_for_function(
        "document.querySelector('.dz-workspace-save').dataset.dzSaveState === 'saved'"
    )
    s = _state(page)
    assert s["errId"] is None and s["describedby"] is None
