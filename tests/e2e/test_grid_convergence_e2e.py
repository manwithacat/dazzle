"""Interactive browser proof of the grid convergence (C1.1).

Boots ``examples/acme_billing`` (the one example declaring ``ux:
bulk_actions:``), logs in as the admin persona, and drives the flipped
list surface END TO END in a real Chromium — the things unit pins can't
prove:

- the tbody hydrates and a `[data-dz-grid-sort]` header click re-fetches
  server-ordered rows with `aria-sort` state on the th;
- checking row boxes REVEALS the bulk bar (pre-convergence this never
  happened in production: the count sat on the region <section> while the
  CSS gate keyed on `.dz-table`, so the bar was permanently hidden);
- the bulk Delete posts the grid payload to the C0b ``/bulk`` route behind
  the designed confirm dialog, and `data-dz-grid-bulk-refresh` re-fetches
  the surviving rows (pre-convergence dzTable posted to ``/bulk-delete``,
  a route that was never mounted — a latent 404).

Uses the same subprocess-boot pattern as ``test_fieldtest_hub_screenshots``.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

pytest.importorskip("dazzle.http")
pytest.importorskip("dazzle.page")

SERVER_STARTUP_TIMEOUT = 60

# Boots a subprocess against the repo's examples/acme_billing dir — pin the
# whole module to that directory's xdist cohort (CLAUDE.md test rule).
pytestmark = pytest.mark.xdist_group("acme_billing")


class _AppServer:
    """Boot an example app with ``dazzle serve --test-mode``."""

    def __init__(self, example_dir: Path) -> None:
        self.example_dir = example_dir
        self.process: subprocess.Popen | None = None
        self.api_url = ""
        self.ui_url = ""
        self.test_secret = ""

    def __enter__(self) -> _AppServer:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        runtime_file = self.example_dir / ".dazzle" / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dazzle",
                "serve",
                "--host",
                "127.0.0.1",
                "--test-mode",
            ],
            cwd=self.example_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **kwargs,
        )
        for _ in range(SERVER_STARTUP_TIMEOUT * 2):
            if runtime_file.exists():
                try:
                    data = json.loads(runtime_file.read_text())
                    self.api_url = f"http://127.0.0.1:{data['api_port']}"
                    self.ui_url = f"http://127.0.0.1:{data['ui_port']}"
                    # test-mode guards /__test__/* with this secret (#458/#790)
                    self.test_secret = str(data.get("test_secret", "") or "")
                    break
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)
        if not self._wait_for_health():
            self._cleanup()
            raise RuntimeError("acme_billing server failed to start")
        return self

    def _wait_for_health(self, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
        import requests

        start = time.time()
        while time.time() - start < timeout:
            try:
                if requests.get(f"{self.api_url}/health", timeout=2).status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _cleanup(self) -> None:
        if self.process:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
            except (ProcessLookupError, OSError):
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def __exit__(self, *exc: Any) -> None:
        self._cleanup()


@pytest.fixture(scope="module")
def server() -> Iterator[_AppServer]:
    example_dir = Path(__file__).parent.parent.parent / "examples" / "acme_billing"
    if not example_dir.exists():
        pytest.skip("acme_billing example not found")
    with _AppServer(example_dir) as srv:
        yield srv


@pytest.fixture(scope="module")
def browser():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _seed(server: _AppServer) -> None:
    """Reset (the app auto-seeds demo data on boot), then seed org → project
    → 3 invoices through the test-mode fixture route."""
    import requests

    reset = requests.post(
        f"{server.api_url}/__test__/reset",
        headers={"X-Test-Secret": server.test_secret},
        timeout=30,
    )
    assert reset.status_code == 200, f"reset failed: {reset.status_code} {reset.text[:200]}"

    fixtures = [
        {"id": "org1", "entity": "Organization", "data": {"name": "Acme"}},
        {"id": "proj1", "entity": "Project", "data": {"name": "Apollo"}, "refs": {"org": "org1"}},
        {
            "id": "inv3",
            "entity": "Invoice",
            "data": {"number": "INV-003", "amount": 300},
            "refs": {"project": "proj1"},
        },
        {
            "id": "inv1",
            "entity": "Invoice",
            "data": {"number": "INV-001", "amount": 100},
            "refs": {"project": "proj1"},
        },
        {
            "id": "inv2",
            "entity": "Invoice",
            "data": {"number": "INV-002", "amount": 200},
            "refs": {"project": "proj1"},
        },
    ]
    resp = requests.post(
        f"{server.api_url}/__test__/seed",
        json={"fixtures": fixtures},
        headers={"X-Test-Secret": server.test_secret},
        timeout=10,
    )
    assert resp.status_code == 200, f"seed failed: {resp.status_code} {resp.text[:300]}"


def _login_admin(page: Any, server: _AppServer) -> None:
    """Authenticate as admin via the test-mode session endpoint (#458): it
    returns a real auth-store session; plant its cookie in the browser."""
    import requests

    resp = requests.post(
        f"{server.api_url}/__test__/authenticate",
        json={"role": "admin", "username": "admin"},
        headers={"X-Test-Secret": server.test_secret},
        timeout=10,
    )
    assert resp.status_code == 200, (
        f"test authenticate failed: {resp.status_code} {resp.text[:200]}"
    )
    token = resp.json()["session_token"]
    page.context.add_cookies(
        [
            {
                "name": "dazzle_session",
                "value": token,
                "url": server.ui_url,
            }
        ]
    )


def _invoice_numbers(page: Any) -> list[str]:
    return page.eval_on_selector_all(
        "[data-dz-grid-body] tr td[data-dz-col='number']",
        "tds => tds.map(td => td.textContent.trim())",
    )


@pytest.mark.e2e
def test_grid_sort_select_and_bulk_delete(browser, server) -> None:  # type: ignore[no-untyped-def]
    _seed(server)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _login_admin(page, server)
        page.goto(f"{server.ui_url}/app/invoice")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)

        # Hydration: seeded rows arrive, and the surface's DEFAULT sort
        # (ux: sort: number asc) is REFLECTED on the header — the review-fix
        # invariant: the controller reads sort state off the headers, so the
        # default must be visible there or the first refresh drops it.
        assert set(_invoice_numbers(page)) == {"INV-001", "INV-002", "INV-003"}
        assert (
            page.eval_on_selector(
                "[data-dz-grid-sort='number']", "b => b.closest('th').getAttribute('aria-sort')"
            )
            == "ascending"
        ), "the ux: sort: default must pre-populate the header's aria-sort"

        # SORT: with the header already ascending, ONE click advances to DESC
        # — a visible reorder the default order can't fake.
        page.click("[data-dz-grid-sort='number']")
        page.wait_for_timeout(600)
        assert (
            page.eval_on_selector(
                "[data-dz-grid-sort='number']", "b => b.closest('th').getAttribute('aria-sort')"
            )
            == "descending"
        )
        assert _invoice_numbers(page) == ["INV-003", "INV-002", "INV-001"], (
            "descending sort must reorder the server rows"
        )

        # SELECTION: checking two rows reveals the bulk bar — the reveal that
        # could never happen pre-convergence (count on <section>, gate on
        # .dz-table) — and the count reads 2.
        boxes = page.locator("[data-dz-grid-select]")
        boxes.nth(0).check()
        boxes.nth(1).check()
        page.wait_for_timeout(200)
        root = "[data-dz-grid]"
        assert page.get_attribute(root, "data-dz-bulk-count") == "2"
        assert (
            page.eval_on_selector(".dz-bulk-actions", "e => getComputedStyle(e).display") != "none"
        ), "the bulk bar must REVEAL on selection (the pre-C1.1 permanently-hidden bug)"

        # BULK DELETE: the designed confirm dialog gates the POST to the C0b
        # /bulk route; data-dz-grid-bulk-refresh re-fetches survivors.
        page.click(".dz-bulk-delete")
        page.wait_for_timeout(400)
        assert page.evaluate(
            "!!document.querySelector('dialog.dz-alert-dialog') && "
            "document.querySelector('dialog.dz-alert-dialog').open"
        ), "bulk delete must go through the designed dz-confirm dialog"
        page.click("dialog.dz-alert-dialog [data-dz-confirm-accept]")
        page.wait_for_timeout(1000)
        # Under the descending sort, rows are 003, 002, 001 — boxes 0 and 1
        # selected INV-003 + INV-002, so INV-001 survives.
        remaining = _invoice_numbers(page)
        assert remaining == ["INV-001"], f"the two selected rows must be gone: {remaining}"
        assert page.get_attribute(root, "data-dz-bulk-count") == "0", (
            "the selection (and its bar) clears after the action"
        )
    finally:
        page.close()
    assert not errors, f"page threw JS errors: {errors}"


@pytest.mark.e2e
def test_grid_url_state_and_drill_back(browser, server) -> None:  # type: ignore[no-untyped-def]
    """C1.3: full-page list surfaces are URL-synced (data-dz-grid-url).

    - a sort click lands in the address bar as human-readable params;
    - drilling into a row (hx-push-url detail navigation) and pressing Back
      restores the LIST with the grid state intact — the two history writers
      (the grid's pushState and htmx's push-url) must compose;
    - a deep-link reload WITH grid params applies them (controls + rows).
    """
    _seed(server)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _login_admin(page, server)
        page.goto(f"{server.ui_url}/app/invoice")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)

        # SORT → URL: one click on the ascending default advances to DESC and
        # the query mirrors into the address bar.
        page.click("[data-dz-grid-sort='number']")
        page.wait_for_timeout(600)
        assert _invoice_numbers(page) == ["INV-003", "INV-002", "INV-001"]
        params = page.evaluate(
            "() => Object.fromEntries(new URLSearchParams(location.search).entries())"
        )
        assert params.get("sort") == "number" and params.get("dir") == "desc", (
            f"the sorted state must mirror into the URL: {params}"
        )

        # DRILL + BACK: row click navigates to the detail (hx-push-url); Back
        # must restore the list with the sorted state intact. Dispatch on the
        # <tr> itself — data cells carry stopPropagation (#1511 §3.2), so a
        # cell-centre click deliberately doesn't drill.
        page.eval_on_selector("[data-dz-grid-body] tr", "tr => tr.click()")
        page.wait_for_timeout(1200)
        assert "/app/invoice/" in page.url, f"the drill navigates to the detail: {page.url}"

        page.go_back()
        page.wait_for_timeout(1500)
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)
        assert _invoice_numbers(page) == ["INV-003", "INV-002", "INV-001"], (
            "Back must restore the sorted list (grid pushState + htmx push-url compose)"
        )
        assert (
            page.eval_on_selector(
                "[data-dz-grid-sort='number']", "b => b.closest('th').getAttribute('aria-sort')"
            )
            == "descending"
        ), "the header state survives the drill round-trip"

        # DEEP LINK: a fresh load with grid params applies them.
        page.goto(f"{server.ui_url}/app/invoice?sort=number&dir=desc")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)
        page.wait_for_timeout(400)
        assert _invoice_numbers(page) == ["INV-003", "INV-002", "INV-001"], (
            "a deep link with grid params must render the described state"
        )
        assert (
            page.eval_on_selector(
                "[data-dz-grid-sort='number']", "b => b.closest('th').getAttribute('aria-sort')"
            )
            == "descending"
        ), "the deep-linked sort must reflect on the header (state-in-DOM)"
    finally:
        page.close()
    assert not errors, f"page threw JS errors: {errors}"


@pytest.mark.e2e
def test_grid_column_visibility_extension(browser, server) -> None:  # type: ignore[no-untyped-def]
    """C2.1: column visibility as a delegated extension on the primitive's
    seams — a native <details> menu, toggles that hide header + cells,
    persistence across a swap (re-sort) AND a full reload (localStorage),
    and re-checking restores the column."""
    _seed(server)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _login_admin(page, server)
        page.goto(f"{server.ui_url}/app/invoice")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)

        def col_visible(key: str) -> bool:
            return page.eval_on_selector(
                f"[data-dz-grid-body] td[data-dz-col='{key}']",
                "td => getComputedStyle(td).display !== 'none'",
            )

        # The menu is a native details disclosure.
        assert page.query_selector("details.dz-table-col-menu"), (
            "the column menu is a native <details> (no open/close JS)"
        )
        page.click("details.dz-table-col-menu summary")
        page.wait_for_timeout(200)

        # Hide Amount: header + every cell disappear.
        page.uncheck("[data-dz-grid-col-toggle='amount']")
        page.wait_for_timeout(200)
        assert not col_visible("amount"), "unchecking hides the cells"
        assert page.eval_on_selector(
            "th[data-dz-col='amount']", "th => getComputedStyle(th).display === 'none'"
        ), "the header hides in lock-step"

        # Survives a swap: re-sort re-fetches rows — they arrive hidden.
        page.click("[data-dz-grid-sort='number']")
        page.wait_for_timeout(600)
        assert not col_visible("amount"), "hydrated rows re-apply the hidden set"

        # Survives a full reload (localStorage persistence).
        page.reload()
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)
        page.wait_for_timeout(300)
        assert not col_visible("amount"), "the preference persists across reloads"

        # Re-check restores the column (and the box reflects storage on load).
        page.click("details.dz-table-col-menu summary")
        page.wait_for_timeout(200)
        assert not page.is_checked("[data-dz-grid-col-toggle='amount']"), (
            "the menu box reflects the persisted hidden state"
        )
        page.check("[data-dz-grid-col-toggle='amount']")
        page.wait_for_timeout(200)
        assert col_visible("amount"), "re-checking restores the column"
    finally:
        page.evaluate("localStorage.clear()")
        page.close()
    assert not errors, f"page threw JS errors: {errors}"


@pytest.mark.e2e
def test_grid_column_resize_extension(browser, server) -> None:  # type: ignore[no-untyped-def]
    """C2.2: column resize as a delegated extension — a pointer drag on a
    header handle resizes the column's <col> (snapped to an 8px grid,
    clamped 80..800), and the width persists across a full reload."""
    _seed(server)
    # A LONG invoice number makes the Number column render well over 160px —
    # exposing the col.offsetWidth===0 trap (cols are non-rendered boxes, so
    # a naive baseline defaults to 160px and a first drag on any wide column
    # does nothing / jumps).
    import requests

    wide = requests.post(
        f"{server.api_url}/__test__/seed",
        json={
            "fixtures": [
                # Self-contained chain — refs resolve within one request.
                {"id": "org2", "entity": "Organization", "data": {"name": "Beta"}},
                {
                    "id": "proj2",
                    "entity": "Project",
                    "data": {"name": "Zephyr"},
                    "refs": {"org": "org2"},
                },
                {
                    "id": "inv4",
                    "entity": "Invoice",
                    "data": {"number": "INV-0004-EXTENDED-ALPHANUMERIC-FORMAT", "amount": 400},
                    "refs": {"project": "proj2"},
                },
            ]
        },
        headers={"X-Test-Secret": server.test_secret},
        timeout=10,
    )
    assert wide.status_code == 200, f"wide-row seed failed: {wide.text[:200]}"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _login_admin(page, server)
        page.goto(f"{server.ui_url}/app/invoice")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)

        handle = page.query_selector("[data-dz-grid-resize='number']")
        assert handle, "the number header carries a resize handle"
        assert page.query_selector("colgroup col[data-dz-col='number']"), (
            "the table carries a colgroup with per-column <col> targets"
        )

        # Drag the handle 64px right.
        box = handle.bounding_box()
        start_w = page.eval_on_selector(
            "th[data-dz-col='number']", "th => th.getBoundingClientRect().width"
        )
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 64, box["y"] + box["height"] / 2, steps=4)
        page.mouse.up()
        page.wait_for_timeout(200)

        col_width = page.eval_on_selector("col[data-dz-col='number']", "c => c.style.width")
        assert col_width.endswith("px") and int(col_width[:-2]) % 8 == 0, (
            f"the col width is set and snapped to the 8px grid: {col_width!r}"
        )
        new_w = page.eval_on_selector(
            "th[data-dz-col='number']", "th => th.getBoundingClientRect().width"
        )
        # TIGHT: the drag baselines at the column's ACTUAL rendered width, so
        # +64px of pointer travel lands within a snap-step of start+64. (The
        # col.offsetWidth===0 bug baselined every first drag at 160px — wide
        # columns didn't move at all and narrow ones jumped.)
        assert abs(new_w - (start_w + 64)) <= 16, (
            f"the drag must baseline at the rendered width: {start_w} -> {new_w}"
        )

        # Persists across a reload (localStorage).
        page.reload()
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)
        page.wait_for_timeout(300)
        assert (
            page.eval_on_selector("col[data-dz-col='number']", "c => c.style.width") == col_width
        ), "the width re-applies from storage on load"
    finally:
        page.evaluate("localStorage.clear()")
        page.close()
    assert not errors, f"page threw JS errors: {errors}"


@pytest.mark.e2e
def test_grid_inline_edit_extension(browser, server) -> None:  # type: ignore[no-untyped-def]
    """C2.3: inline edit on the cell-owns-its-affordance seam — a dblclick
    opens an in-cell editor, Enter commits a single-field PUT to the update route
    (pre-convergence dzTable PATCHed /api/{EntityName}/... while the route
    mounts at /{plural}/... — a silent 404, the third dead leg), the grid
    refreshes with the saved value, and Escape cancels."""
    _seed(server)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _login_admin(page, server)
        page.goto(f"{server.ui_url}/app/invoice")
        page.wait_for_selector("[data-dz-grid-body] tr td", timeout=15000)

        # EDIT + COMMIT: dblclick the INV-001 number cell, replace, Enter.
        cell = "[data-dz-grid-body] tr td[data-dz-col='number'] [data-dz-grid-edit]"
        page.dblclick(f"{cell} >> text=INV-001")
        page.wait_for_timeout(300)
        editor = page.query_selector("[data-dz-grid-body] input.dz-inline-edit-input")
        assert editor, "dblclick opens the in-cell editor"
        editor.fill("INV-001-EDITED")
        editor.press("Enter")
        page.wait_for_timeout(1200)
        numbers = _invoice_numbers(page)
        assert "INV-001-EDITED" in numbers, (
            f"the commit must persist and the grid refresh must show it: {numbers}"
        )
        assert "INV-001" not in numbers, f"the old value is gone: {numbers}"

        # ESC cancels without a write.
        page.dblclick(f"{cell} >> text=INV-002")
        page.wait_for_timeout(300)
        editor = page.query_selector("[data-dz-grid-body] input.dz-inline-edit-input")
        assert editor, "second edit opens"
        editor.fill("SHOULD-NOT-PERSIST")
        editor.press("Escape")
        page.wait_for_timeout(600)
        numbers = _invoice_numbers(page)
        assert "INV-002" in numbers and "SHOULD-NOT-PERSIST" not in numbers, (
            f"Escape must discard the buffer: {numbers}"
        )
    finally:
        page.close()
    assert not errors, f"page threw JS errors: {errors}"
