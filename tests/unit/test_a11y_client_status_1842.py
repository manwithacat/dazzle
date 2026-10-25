"""#1842 client-side a11y (cyfuture WCAG 2.2 audit), driven in Chromium.

* Rich-text toolbar (1.1.1 / 4.1.2): every button is named by a word via
  ``aria-label``, its glyph is ``aria-hidden``, ``title`` leads with the
  same word (not the raw command name), and the roving tabindex holds.
* Workspace Save (4.1.3): "Saving…", "Saved" and the failure reason are
  announced through the builder's live region; the button turns
  ``aria-disabled`` (never ``disabled``) so it keeps focus; a second click
  while saving does not PUT again; the error is visible text the button
  references with ``aria-describedby``.
* Two-factor sign-in timeout (2.2.1): the warning is announced through a
  ``role="alert"`` region without taking focus from the code field; "More
  time" posts with the CSRF echo, hides itself and hands focus back to the
  code field; when time is up the page says so and offers "Sign in again".

The scripts run against real SSR markup (``WorkspaceToolbar``,
``build_code_entry_view``) on a ``set_content`` page or a routed origin.
Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dazzle.http.runtime.auth.two_factor_views import (  # noqa: E402
    ChallengeTimeout,
    build_code_entry_view,
)
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
    "h2": "Heading 2, H2",
    "h3": "Heading 3, H3",
    "ul": "Bulleted list",
    "ol": "Numbered list, 1.",
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
            glyph: b.textContent,
            title: b.title,
            tabindex: b.getAttribute("tabindex"),
            glyphHidden: [...b.childNodes].every(
                n => n.nodeType === 1 && n.getAttribute("aria-hidden") === "true"),
        }))""",
    )
    assert {b["cmd"]: b["label"] for b in buttons} == _EXPECTED_NAMES
    for b in buttons:
        assert b["glyphHidden"], f"{b['cmd']}: glyph must be aria-hidden"
        # WCAG 2.5.3 Label in Name: visible letters/digits are in the name.
        if any(c.isalnum() for c in b["glyph"]):
            assert b["glyph"].lower() in b["label"].lower(), b
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


# ── 2.2.1: the two-factor challenge warns before it times out ──────────


def _challenge_page(expires_in: int) -> str:
    html = FragmentRenderer().render(
        build_code_entry_view(
            product_name="Acme",
            heading="Verify",
            mode="totp",
            methods=("totp",),
            verify_action="/auth/2fa/verify/submit",
            send_action="/auth/2fa/email-otp-send/submit",
            page_path="/2fa/challenge",
            timeout=ChallengeTimeout(expires_in, "/auth/2fa/challenge/extend?method=totp", 5),
            js_scripts=(),
        )
    )
    # The script is injected by the test, not fetched from /static.
    return html.replace('<script defer src="/static/js/dz-2fa-timeout.js"></script>', "")


def _open_challenge(page: Any, expires_in: int, extend: dict[str, Any]) -> list[dict[str, str]]:
    """Serve the page from a real origin (the script fetches) and record extend posts."""
    posts: list[dict[str, str]] = []

    def on_extend(route: Any) -> None:
        posts.append(route.request.headers)
        route.fulfill(status=200, content_type="application/json", json=extend)

    page.unroute("**/*")
    page.route(
        "http://dz.test/2fa/challenge",
        lambda r: r.fulfill(
            status=200,
            content_type="text/html",
            headers={"set-cookie": "dazzle_csrf=tok; Path=/"},
            body=_challenge_page(expires_in),
        ),
    )
    page.route("http://dz.test/auth/2fa/challenge/extend*", on_extend)
    page.goto("http://dz.test/2fa/challenge")
    page.focus("input[name='code']")
    page.add_script_tag(path=str(JS / "dz-2fa-timeout.js"))
    return posts


_TIMEOUT_STATE = """() => {
  const msg = document.querySelector('[data-dz-2fa-timeout-message]');
  return {
    text: msg.textContent,
    role: msg.getAttribute('role'),
    actionsHidden: document.querySelector('[data-dz-2fa-timeout-actions]').hidden,
    restartHidden: document.querySelector('[data-dz-2fa-timeout-restart]').hidden,
    focused: document.activeElement && document.activeElement.name,
  };
}"""


def test_two_factor_timeout_warns_and_more_time_extends(page: Any) -> None:
    # 30s left, warned 60s ahead: the warning shows at once.
    posts = _open_challenge(page, 30, {"expires_in": 600, "extendable": True})
    s = page.evaluate(_TIMEOUT_STATE)
    assert s["role"] == "alert" and s["text"].startswith("Your sign-in times out")
    assert s["actionsHidden"] is False and s["restartHidden"] is True
    assert s["focused"] == "code", "the warning must not steal focus from the code field"

    page.click("[data-dz-2fa-extend] button")
    page.wait_for_function("document.querySelector('[data-dz-2fa-timeout-actions]').hidden")
    s = page.evaluate(_TIMEOUT_STATE)
    assert s["text"] == "You have more time to enter your code."
    assert s["focused"] == "code", "focus returns to the code field after More time"
    assert len(posts) == 1
    assert posts[0]["accept"] == "application/json" and posts[0]["x-csrf-token"] == "tok"


def test_two_factor_timeout_says_when_time_is_up(page: Any) -> None:
    _open_challenge(page, 1, {})
    page.wait_for_function("!document.querySelector('[data-dz-2fa-timeout-restart]').hidden")
    s = page.evaluate(_TIMEOUT_STATE)
    assert s["text"] == "Your sign-in timed out. Sign in again to get a new code."
    assert s["actionsHidden"] is True
