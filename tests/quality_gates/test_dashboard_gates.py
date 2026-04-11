"""
Dashboard Quality Gate Tests — ux-architect/components/dashboard-grid.md

Automated verification of the 5 quality gates from the dashboard component contract.
Runs against a static test harness (no backend needed).

Usage:
    python -m pytest tests/quality_gates/test_dashboard_gates.py -v
"""

import subprocess
import time

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module")
def server():
    """Start a simple HTTP server for the test harness."""
    static_dir = "src/dazzle_ui/runtime/static"
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", "8766", "--directory", static_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    yield "http://localhost:8766/test-dashboard.html"
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser_page(server):
    """Launch headless browser and navigate to test harness."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(server)
        # Wait for Alpine to load and initialize the dashboard component
        page.wait_for_function(
            "typeof Alpine !== 'undefined' && document.querySelector('[data-card-id]') !== null",
            timeout=10000,
        )
        yield page
        browser.close()


class TestDashboardQualityGates:
    """5 quality gates from ux-architect/components/dashboard-grid.md"""

    def test_gate1_drag_threshold(self, browser_page):
        """Gate 1: Click without moving stays put. 3px stays put. 5px lifts."""
        result = browser_page.evaluate("window.qualityGates.testDragThreshold()")
        assert result is True, (
            f"Drag threshold failed: {browser_page.evaluate('window.qualityGates.results.dragThreshold')}"
        )

    def test_gate2_drag_uses_transform(self, browser_page):
        """Gate 2: Drag uses transform:translate(), not left/top. Has scale, opacity, shadow, z-index."""
        result = browser_page.evaluate("window.qualityGates.testDragTransform()")
        details = browser_page.evaluate("window.qualityGates.results.dragTransform")
        assert result is True, f"Drag transform failed: {details}"

    def test_gate3_save_lifecycle(self, browser_page):
        """Gate 3: Save button transitions through clean → dirty states."""
        result = browser_page.evaluate("window.qualityGates.testSaveLifecycle()")
        details = browser_page.evaluate("window.qualityGates.results.saveLifecycle")
        assert result is True, f"Save lifecycle failed: {details}"

    def test_gate4_persistence_boundary(self, browser_page):
        """Gate 4: Cards match data island on load (unsaved changes don't persist)."""
        result = browser_page.evaluate("window.qualityGates.testPersistenceBoundary()")
        details = browser_page.evaluate("window.qualityGates.results.persistenceBoundary")
        assert result is True, f"Persistence boundary failed: {details}"

    def test_gate5_keyboard_accessibility(self, browser_page):
        """Gate 5: Keyboard move mode works. Live region with aria-live exists."""
        result = browser_page.evaluate("window.qualityGates.testKeyboardAccessibility()")
        details = browser_page.evaluate("window.qualityGates.results.keyboardAccessibility")
        assert result is True, f"Keyboard accessibility failed: {details}"

    def test_all_gates_pass(self, browser_page):
        """Meta-gate: all 5 gates pass together."""
        result = browser_page.evaluate("window.qualityGates.runAll()")
        assert result["allPass"] is True, "Not all gates passed: " + ", ".join(
            f"{name}: {'PASS' if r['pass'] else 'FAIL'}" for name, r in result["results"].items()
        )
