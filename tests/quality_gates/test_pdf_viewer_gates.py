"""PDF viewer quality gates (#942 cycle 1c).

Browser-driven verification of the cycle 1b chrome and keyboard
shortcuts. Runs Playwright (chromium) against a static harness at
``src/dazzle_ui/runtime/static/test-pdf-viewer.html`` served via
Python's ``http.server`` — same pattern as
``test_dashboard_gates.py``.

Three classes of gate:

1. **Layout invariants** — the chrome's geometry has to hold
   regardless of viewport (header anchored top, footer anchored
   bottom, body fills the gap, no overflow).
2. **Keyboard wiring** — Esc / j / k / arrows actually fire
   navigation; modifier and editable suppression behaves as
   advertised.
3. **Visual capture** — screenshots of every variant land in
   ``dev_docs/pdf-viewer-screenshots/`` for human inspection.
   Filenames are deterministic so ``git status`` shows what
   changed when CSS shifts. Not a strict comparison gate (cross-OS
   antialiasing makes pixel-diff brittle); the layout assertions
   above carry the load-bearing checks.

Skipped wholesale when Playwright is unavailable (mirrors the
dashboard-gates skip).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "src/dazzle_ui/runtime/static"
SCREENSHOT_DIR = REPO_ROOT / "dev_docs/pdf-viewer-screenshots"
HARNESS_PORT = 8767  # different from dashboard's 8766 — both can run together


@pytest.fixture(scope="module")
def server() -> Any:
    """Static-files server pointing at the runtime/static dir."""
    proc = subprocess.Popen(
        [
            "python3",
            "-m",
            "http.server",
            str(HARNESS_PORT),
            "--directory",
            str(STATIC_DIR),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    base = f"http://localhost:{HARNESS_PORT}/test-pdf-viewer.html"
    yield base
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser() -> Any:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _new_page(browser: Any, server: str, *, variant: str = "both") -> Any:
    """Open the harness in a fresh page and wait for the bridge to
    register the pdf-viewer widget. Variant query string controls
    sibling-nav presence (see harness markup)."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.goto(f"{server}?variant={variant}")
    # Bridge is loaded `defer`; wait for the registry to be present.
    page.wait_for_function(
        "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
        timeout=5000,
    )
    return page


# ---------------------------------------------------------------------------
# Gate 1 — chrome elements present
# ---------------------------------------------------------------------------


class TestChromeStructure:
    def test_all_chrome_elements_render(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        present = page.evaluate("window.pdfViewerGates.chromePresent()")
        assert present == {
            "host": True,
            "header": True,
            "body": True,
            "footer": True,
            "back": True,
            "title": True,
        }
        page.screenshot(path=str(SCREENSHOT_DIR / "default-both-siblings.png"))
        page.close()

    def test_data_dz_widget_marker_present(self, browser: Any, server: str) -> None:
        """Confirms the bridge's mount point is on the wrapper —
        without it the keyboard handler never installs."""
        page = _new_page(browser, server)
        marker = page.locator("#pdf-viewer-host").get_attribute("data-dz-widget")
        assert marker == "pdf-viewer"
        page.close()


# ---------------------------------------------------------------------------
# Gate 2 — layout invariants
# ---------------------------------------------------------------------------


class TestChromeLayout:
    """Geometric invariants that hold across viewports.

    We check arrangement and bounds rather than exact pixel values
    so the gates survive harmless token tweaks (font-size bumps,
    spacing nudges) but catch real regressions (header overflow,
    footer occlusion, body collapse)."""

    def test_three_band_vertical_stack(self, browser: Any, server: str) -> None:
        """Header above body above footer; all three contiguous."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        host = rects["host"]
        header = rects["header"]
        body = rects["body"]
        footer = rects["footer"]

        # Header anchored at top; footer anchored at bottom; body
        # spans the gap.
        assert header["top"] == pytest.approx(host["top"], abs=1)
        assert header["bottom"] == pytest.approx(body["top"], abs=1)
        assert body["bottom"] == pytest.approx(footer["top"], abs=1)
        assert footer["bottom"] == pytest.approx(host["bottom"], abs=1)
        # Body MUST be the largest band — it's the content area.
        assert body["height"] > header["height"]
        assert body["height"] > footer["height"]
        page.close()

    def test_full_viewport_coverage(self, browser: Any, server: str) -> None:
        """Wrapper fills the viewport — no whitespace gutters above
        the header or below the footer."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        host = rects["host"]
        viewport = page.viewport_size
        assert host["top"] == pytest.approx(0, abs=1)
        assert host["left"] == pytest.approx(0, abs=1)
        assert host["width"] == pytest.approx(viewport["width"], abs=1)
        assert host["height"] == pytest.approx(viewport["height"], abs=1)
        page.close()

    def test_header_chrome_height_reasonable(self, browser: Any, server: str) -> None:
        """Header is compact — between 30 and 80 px on a 1280px-wide
        viewport. Catches regressions where padding tokens balloon
        or font-size tokens shift the chrome to comically tall."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        assert 30 <= rects["header"]["height"] <= 80
        assert 24 <= rects["footer"]["height"] <= 60
        page.close()

    def test_narrow_viewport_hides_back_label(self, browser: Any, server: str) -> None:
        """Below 640px the back-link label hides (icon alone speaks
        the action). Pinned because it's a deliberate responsive
        decision in pdf-viewer.css."""
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.goto(f"{server}?variant=both")
        page.wait_for_function(
            "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
            timeout=5000,
        )
        label = page.locator(".dz-pdf-viewer-back-label")
        assert label.evaluate("el => getComputedStyle(el).display") == "none"
        page.screenshot(path=str(SCREENSHOT_DIR / "narrow-viewport-480.png"))
        page.close()


# ---------------------------------------------------------------------------
# Gate 3 — keyboard wiring
# ---------------------------------------------------------------------------


class TestKeyboardShortcuts:
    """Hash-based assertions: harness uses ``#back`` / ``#prev`` /
    ``#next`` URLs so navigation produces a hashchange we can read
    off ``page.url`` without an actual page load."""

    def _press(self, page: Any, key: str) -> str:
        page.keyboard.press(key)
        # Hashchange fires synchronously after location.href set.
        page.wait_for_timeout(50)
        return str(page.url)

    def test_escape_navigates_to_back(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "Escape")
        assert url.endswith("#back")
        page.close()

    def test_j_key_navigates_to_prev(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "j")
        assert url.endswith("#prev")
        page.close()

    def test_k_key_navigates_to_next(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "k")
        assert url.endswith("#next")
        page.close()

    def test_arrow_left_navigates_to_prev(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "ArrowLeft")
        assert url.endswith("#prev")
        page.close()

    def test_arrow_right_navigates_to_next(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "ArrowRight")
        assert url.endswith("#next")
        page.close()


# ---------------------------------------------------------------------------
# Gate 4 — suppression
# ---------------------------------------------------------------------------


class TestKeyboardSuppression:
    def test_typing_in_input_does_not_navigate(self, browser: Any, server: str) -> None:
        """Critical safety property — without this, every form
        autocompletion that types 'j' or 'k' would yank the user to
        the next manuscript."""
        page = _new_page(browser, server)
        # Park a known hash, focus the harness's text input, then
        # type 'jjkk' — none of the keys should change location.hash.
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.locator("#harness-text-input").click()
        page.locator("#harness-text-input").fill("")  # ensure focus
        page.keyboard.type("jjkk")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), (
            "j/k typed into an input must NOT trigger sibling navigation"
        )
        page.close()

    def test_modifier_keys_pass_through(self, browser: Any, server: str) -> None:
        """Cmd+j / Ctrl+k must NOT navigate — those are typically
        browser shortcuts (downloads, address bar) and shouldn't be
        hijacked."""
        page = _new_page(browser, server)
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("Meta+j")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), (
            "modifier-keyed j/k must pass through, not hijack navigation"
        )
        page.close()


# ---------------------------------------------------------------------------
# Gate 5 — variant rendering (visual capture only)
# ---------------------------------------------------------------------------


class TestVariantRendering:
    """Each variant renders a different chrome shape. We capture
    screenshots for human inspection; the structural assertions
    elsewhere catch the load-bearing regressions."""

    def test_no_siblings_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="none")
        # Sibling nav block is removed entirely when both URLs
        # are unset.
        nav_count = page.locator(".dz-pdf-viewer-nav").count()
        assert nav_count == 0
        page.screenshot(path=str(SCREENSHOT_DIR / "no-siblings.png"))
        page.close()

    def test_prev_only_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="prev")
        # Both buttons render, but next is aria-disabled (so the
        # chrome stays symmetrical even with one direction available).
        next_btn = page.locator("#harness-next")
        assert next_btn.get_attribute("aria-disabled") == "true"
        # j fires; k does NOT (the data-dz-next-url attr was stripped).
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("k")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), "k must no-op when next-url is unset"
        page.screenshot(path=str(SCREENSHOT_DIR / "prev-only.png"))
        page.close()

    def test_next_only_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="next")
        prev_btn = page.locator("#harness-prev")
        assert prev_btn.get_attribute("aria-disabled") == "true"
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("j")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), "j must no-op when prev-url is unset"
        page.screenshot(path=str(SCREENSHOT_DIR / "next-only.png"))
        page.close()
