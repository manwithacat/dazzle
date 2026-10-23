"""#1845 ``dz:region-loaded``: the host contract for "a region's content swapped in".

Driven in Chromium with the vendored htmx 4 and ``dz-component-bridge.js`` on a
routed origin, so the event comes from a real htmx swap, not a synthetic
``htmx:after:settle``. Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "src/dazzle/page/runtime/static"

_PAGE = """<!doctype html><html><head>
<script src="/vendor/htmx.min.js"></script>
<script src="/js/dz-component-bridge.js"></script>
</head><body>
<div id="tasks-body" data-dz-region data-dz-region-name="open_tasks">
  <button id="load" hx-get="/region" hx-target="#tasks-body" hx-swap="innerHTML">Load</button>
</div>
<div id="queue-body" data-dz-region data-dz-region-name="queue">
  <ul><li id="row">row</li></ul>
  <button id="row-refresh" hx-get="/row" hx-target="#row" hx-swap="outerHTML">Refresh row</button>
</div>
<div id="outside"><button id="plain" hx-get="/row" hx-target="#outside-slot">x</button>
  <span id="outside-slot"></span></div>
<script>
  window.__loaded = [];
  document.addEventListener("dz:region-loaded", function (e) {
    window.__loaded.push({name: e.detail.name, id: e.target.id, bubbles: e.bubbles});
  });
</script>
</body></html>"""


@pytest.fixture(scope="module")
def page() -> Any:
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page()

        def fulfil(route: Any) -> None:
            url = route.request.url
            if url.endswith("/vendor/htmx.min.js") or url.endswith("/js/dz-component-bridge.js"):
                rel = url.split("dz.test/", 1)[1]
                route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=(STATIC / rel).read_text(encoding="utf-8"),
                )
            elif url.endswith("/region"):
                route.fulfill(status=200, content_type="text/html", body="<p>tasks</p>")
            elif url.endswith("/row"):
                route.fulfill(status=200, content_type="text/html", body='<li id="row">new</li>')
            else:
                route.fulfill(status=200, content_type="text/html", body=_PAGE)

        pg.route("http://dz.test/**", fulfil)
        yield pg
        browser.close()


def _click_and_wait(page: Any, selector: str, count: int) -> list[dict[str, Any]]:
    page.click(selector)
    page.wait_for_function(f"window.__loaded.length >= {count}")
    page.wait_for_timeout(150)  # a duplicate dispatch would land here
    return list(page.evaluate("window.__loaded"))


def test_region_loaded_fires_once_on_the_region_after_a_swap(page: Any) -> None:
    page.goto("http://dz.test/workspace")
    loaded = _click_and_wait(page, "#load", 1)
    assert loaded == [{"name": "open_tasks", "id": "tasks-body", "bubbles": True}]
    assert page.inner_text("#tasks-body") == "tasks"


def test_region_loaded_fires_for_a_swap_inside_a_region(page: Any) -> None:
    page.goto("http://dz.test/workspace")
    loaded = _click_and_wait(page, "#row-refresh", 1)
    assert loaded == [{"name": "queue", "id": "queue-body", "bubbles": True}]


def test_region_loaded_does_not_fire_outside_regions(page: Any) -> None:
    page.goto("http://dz.test/workspace")
    page.click("#plain")
    page.wait_for_function("document.querySelector('#outside-slot li') !== null")
    page.wait_for_timeout(150)
    assert page.evaluate("window.__loaded") == []
