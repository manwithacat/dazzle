"""#1854 — the feedback widget's review posture in Chromium.

The shipped ``feedback-widget.js`` on a small signed-in page whose body and
elements carry the chrome's hooks (``data-dz-surface``, ``data-dz-region-name``,
``data-dz-row-id``, ``data-dz-action``), with ``/feedbackreports`` intercepted:

* the widget mounts inside the ``<dz-feedback>`` shadow root, the backtick
  opens the panel with focus on the first category and Escape closes it;
* the review chord arms anchor mode, hovering outlines the element, the
  capture-phase click never reaches the page's own handler, the note card
  autofocuses its textarea, Enter POSTs the note with an ``Idempotency-Key``
  header equal to the body field, a ``dz_anchor`` path, a ``css`` selector
  that resolves to exactly that element, the text quote and the context;
* the saved note comes back as a numbered pin at the element, focus returns
  to the element;
* a note whose anchor no longer exists renders an orphaned pin at its
  recorded rect, and Resolve walks ``new → triaged → resolved``.

Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

REPO_ROOT = Path(__file__).resolve().parents[2]
WIDGET_JS = REPO_ROOT / "src/dazzle/page/runtime/static/js/feedback-widget.js"
ORIGIN = "http://app.test"

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="dz-user-email" content="ada@example.test">
<meta name="dz-user-role" content="super_admin">
<meta name="dz-feedback-review" content="1">
<meta name="dz-feedback-categories" content="bug,ux,copy">
<meta name="dz-feedback-severities" content="p1,p2,p3">
<style>:root{--colour-brand:#2563eb;--colour-brand-contrast:#fff;--colour-surface:#fff;--colour-text:#111;
--colour-border:#ddd;--colour-border-control:#777;--danger-600:#dc2626;--warning-600:#d97706;--success-600:#16a34a}
body{margin:0;padding:40px;font:16px sans-serif}</style>
</head>
<body data-dz-surface="tasks" data-dz-entity="Task" data-dz-record="t-7" data-dz-workspace="ops" data-dz-persona="super_admin">
<h1>Tasks</h1>
<input id="search" placeholder="Search">
<section data-dz-region data-dz-region-name="open_tasks">
  <table><tbody>
    <tr data-dz-row-id="7"><td>Write the report</td><td>Mark <button id="done" data-dz-action="complete">Complete</button> now</td></tr>
    <tr data-dz-row-id="8"><td>Call the parents</td><td><button id="done8" data-dz-action="complete">Complete</button></td></tr>
  </tbody></table>
</section>
<script>
  window.__clicks = [];
  document.getElementById("done").addEventListener("click", function () { window.__clicks.push("complete"); });
</script>
<script src="/static/js/feedback-widget.js"></script>
</body></html>"""


@pytest.fixture(scope="module")
def browser() -> Any:
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


class _Server:
    """An in-page fake of ``/feedbackreports`` behind ``page.route``."""

    def __init__(self, reports: list[dict[str, Any]] | None = None) -> None:
        self.reports = list(reports or [])
        self.posts: list[dict[str, Any]] = []
        self.puts: list[tuple[str, dict[str, Any]]] = []

    def handle(self, route: Any) -> None:
        req = route.request
        url = req.url
        if url == f"{ORIGIN}/app/tasks":
            route.fulfill(status=200, content_type="text/html", body=_PAGE)
        elif url.endswith("/static/js/feedback-widget.js"):
            route.fulfill(
                status=200, content_type="application/javascript", body=WIDGET_JS.read_text()
            )
        elif "/feedbackreports" in url and req.method == "POST":
            body = json.loads(req.post_data or "{}")
            self.posts.append({"headers": req.headers, "body": body})
            row = dict(
                body, id=f"r{len(self.posts)}", status="new", created_at="2026-10-25T10:00:00"
            )
            self.reports.append(row)
            route.fulfill(status=201, content_type="application/json", body=json.dumps(row))
        elif "/feedbackreports/" in url and req.method == "PUT":
            rid = url.rsplit("/", 1)[1]
            body = json.loads(req.post_data or "{}")
            self.puts.append((rid, body))
            for r in self.reports:
                if r["id"] == rid:
                    r.update(body)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": rid}))
        elif "/feedbackreports" in url:
            if "page_url=" in url:
                items = [r for r in self.reports if r.get("status") in ("new", "triaged")]
            else:
                items = []
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"items": items})
            )
        else:
            route.fulfill(status=404, body="")


def _open(browser: Any, server: _Server) -> Any:
    page = browser.new_page(viewport={"width": 1100, "height": 700})
    page.route(f"{ORIGIN}/**", server.handle)
    page.goto(f"{ORIGIN}/app/tasks")
    page.wait_for_function("() => !!window.feedbackWidget")
    return page


_SHADOW = "document.querySelector('dz-feedback').shadowRoot"


def _shadow_eval(page: Any, expr: str) -> Any:
    return page.evaluate(f"() => {{ const root = {_SHADOW}; return {expr}; }}")


def test_panel_opens_in_the_shadow_root_from_the_shortcut(browser: Any) -> None:
    server = _Server()
    page = _open(browser, server)
    try:
        assert _shadow_eval(page, "root.querySelectorAll('.dz-feedback-btn').length") == 1
        assert page.evaluate("() => document.querySelectorAll('.dz-feedback-btn').length") == 0
        # The backtick from a focused field belongs to the field (#1842).
        page.focus("#search")
        page.keyboard.press("`")
        assert (
            _shadow_eval(
                page, "root.querySelector('.dz-feedback-panel').classList.contains('open')"
            )
            is False
        )
        page.evaluate("() => document.activeElement.blur()")
        page.keyboard.press("`")
        assert (
            _shadow_eval(
                page, "root.querySelector('.dz-feedback-panel').classList.contains('open')"
            )
            is True
        )
        assert (
            _shadow_eval(
                page, "root.activeElement && root.activeElement.getAttribute('data-category')"
            )
            == "bug"
        )
        assert (
            _shadow_eval(page, "root.querySelector('.dz-feedback-panel').hasAttribute('inert')")
            is False
        )
        assert [b.inner_text() for b in page.locator(".dz-feedback-cat-btn").all()] == [
            "Bug",
            "Ux",
            "Copy",
        ]
        page.keyboard.press("Escape")
        assert (
            _shadow_eval(page, "root.querySelector('.dz-feedback-panel').hasAttribute('inert')")
            is True
        )
        assert (
            _shadow_eval(page, "root.activeElement === root.querySelector('.dz-feedback-btn')")
            is True
        )
    finally:
        page.close()


def test_review_flow_posts_the_anchor_and_renders_the_pin(browser: Any) -> None:
    server = _Server()
    page = _open(browser, server)
    try:
        page.keyboard.press("Alt+Shift+R")
        assert page.evaluate("() => window.feedbackWidget._armed") is True
        page.hover("#done")
        outline = page.locator(".dz-feedback-outline")
        assert outline.evaluate("el => el.classList.contains('visible')") is True
        assert outline.locator("span").inner_text() == "tasks/open_tasks/7/complete"
        button_box = page.locator("#done").bounding_box()
        outline_box = outline.bounding_box()
        assert (
            abs(outline_box["x"] - button_box["x"]) < 3
            and abs(outline_box["y"] - button_box["y"]) < 3
        )

        page.click("#done")
        assert page.evaluate("() => window.__clicks") == []  # the page handler never ran
        assert page.evaluate("() => window.feedbackWidget._armed") is False
        card = page.locator(".dz-feedback-card")
        assert (
            card.evaluate("el => el.classList.contains('open') && !el.hasAttribute('inert')")
            is True
        )
        assert (
            _shadow_eval(page, "root.activeElement && root.activeElement.id")
            == "dz-feedback-note-text"
        )
        assert page.locator(".dz-feedback-path").first.inner_text() == "tasks/open_tasks/7/complete"
        assert page.locator("#dz-feedback-note-category").input_value() == "ux"

        page.keyboard.type("Label is unclear")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("second line")
        with page.expect_request(lambda r: r.method == "POST" and "/feedbackreports" in r.url):
            page.keyboard.press("Enter")
        page.wait_for_function(f"() => {_SHADOW}.querySelectorAll('.dz-feedback-pin').length === 1")

        (post,) = server.posts
        body = post["body"]
        assert post["headers"]["idempotency-key"] == body["idempotency_key"]
        assert body["description"] == "Label is unclear\nsecond line"
        assert (body["category"], body["severity"]) == ("ux", "p1")
        assert body["page_url"] == f"{ORIGIN}/app/tasks"
        assert body["surface"] == "tasks"
        anchor = body["anchor"]
        assert anchor["dz_anchor"] == "tasks/open_tasks/7/complete"
        assert anchor["tag"] == "button"
        assert anchor["text_quote"] == {"exact": "Complete", "prefix": "Mark ", "suffix": " now"}
        assert anchor["rect"]["w"] > 0 and anchor["viewport"] == [1100, 700]
        # The finder selector is unique and names the clicked button, not its twin.
        css = anchor["css"]
        assert (
            page.evaluate(
                "css => { const all = document.querySelectorAll(css); return all.length === 1 && all[0].id === 'done'; }",
                css,
            )
            is True
        )
        ctx = body["context"]
        assert (ctx["surface"], ctx["entity"], ctx["record"], ctx["workspace"], ctx["persona"]) == (
            "tasks",
            "Task",
            "t-7",
            "ops",
            "super_admin",
        )
        assert ctx["url"] == f"{ORIGIN}/app/tasks" and ctx["color_scheme"] in ("light", "dark")
        assert len(ctx["review_session"]) == 15 and body["review_session"] == ctx["review_session"]
        assert body["anchor"]["rect"] == {
            "x": round(button_box["x"]),
            "y": round(button_box["y"]),
            "w": round(button_box["width"]),
            "h": round(button_box["height"]),
        }

        # Focus is back on the element; the pin sits on its top-right corner.
        assert page.evaluate("() => document.activeElement.id") == "done"
        pin = page.locator(".dz-feedback-pin")
        assert pin.inner_text() == "1"
        assert pin.get_attribute("data-orphaned") is None
        assert pin.get_attribute("aria-label") == "Review note 1: Label is unclear\nsecond line"
        pin_box = pin.bounding_box()
        right = button_box["x"] + button_box["width"]
        assert abs(pin_box["x"] + pin_box["width"] / 2 - right) < 3
        assert abs(pin_box["y"] + pin_box["height"] / 2 - button_box["y"]) < 3
    finally:
        page.close()


def test_orphaned_pin_and_resolve_transitions(browser: Any) -> None:
    server = _Server(
        [
            {
                "id": "old",
                "status": "new",
                "created_at": "2026-10-24T09:00:00",
                "description": "Banner is stale",
                "severity": "p2",
                "category": "copy",
                "reported_by": "ada@example.test",
                "anchor": {
                    "dz_anchor": "tasks/banner",
                    "css": "#banner",
                    "text_quote": {"exact": "Old banner", "prefix": "", "suffix": ""},
                    "tag": "div",
                    "rect": {"x": 300, "y": 60, "w": 200, "h": 30},
                    "scroll": {"x": 0, "y": 0},
                },
            }
        ]
    )
    page = _open(browser, server)
    try:
        page.wait_for_function(f"() => {_SHADOW}.querySelectorAll('.dz-feedback-pin').length === 1")
        pin = page.locator(".dz-feedback-pin")
        assert pin.get_attribute("data-orphaned") == ""
        assert (
            pin.get_attribute("aria-label") == "Review note 1 (element not found): Banner is stale"
        )
        box = pin.bounding_box()
        assert (
            abs(box["x"] + box["width"] / 2 - 500) < 3
            and abs(box["y"] + box["height"] / 2 - 60) < 3
        )

        pin.click()
        note = page.locator(".dz-feedback-note")
        assert note.evaluate("el => el.classList.contains('open')") is True
        assert (
            page.locator("#dz-feedback-note-title").inner_text()
            == "Review note 1 — element not found"
        )
        assert "was: “Old banner”" in note.locator(".dz-feedback-path").inner_text()
        assert (
            _shadow_eval(page, "root.activeElement && root.activeElement.textContent") == "Resolve"
        )

        page.locator(".dz-feedback-resolve").click()
        page.wait_for_function(f"() => {_SHADOW}.querySelectorAll('.dz-feedback-pin').length === 0")
        assert server.puts == [("old", {"status": "triaged"}), ("old", {"status": "resolved"})]
        assert note.evaluate("el => el.hasAttribute('inert')") is True
    finally:
        page.close()
