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
    """Boot an example app with ``dazzle serve --local --test-mode``."""

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
                "--local",
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
