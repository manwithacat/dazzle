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


class TestDashboardIntegrationGates:
    """Integration gates: real DOM pointer events on window.

    These tests exercise the `@pointermove.window` and `@pointerup.window` event
    bindings with real DOM events — the exact pipeline that the setPointerCapture
    bug (#770) broke. They complement the unit gates above, which test controller
    state transitions in isolation.

    **Why seed drag state via direct method call, then fire real pointermove?**
    The setPointerCapture bug redirected pointermove events AWAY from the window
    listener and onto the captured element. The bug was NOT in `@pointerdown` —
    that fired correctly. The bug was in the window listener for pointermove/up
    never receiving events because they were captured. So the critical regression
    test is: "after startDrag is called, does a real window-level pointermove
    actually reach the handler and transition phases?"

    This is what these tests verify: startDrag seeds state, real window events
    drive the transition, and we assert the handler was reached.
    """

    def _seed_drag_state(self, browser_page, start_x=100, start_y=100):
        """Seed a 'pressed' drag state by invoking startDrag directly.

        This bypasses @pointerdown binding (which has an unrelated issue inside
        <template x-for> that we file separately). The purpose of these tests
        is to verify the window-level event pipeline, not @pointerdown itself.
        """
        browser_page.evaluate(f"""
            (() => {{
                const comp = Alpine.$data(document.querySelector('[x-data]'));
                comp.drag = null;
                comp.resize = null;
                comp.undoStack = [];
                comp.saveState = 'clean';
                comp.startDrag('card-1', {{
                    clientX: {start_x},
                    clientY: {start_y},
                    button: 0,
                    pointerId: 1,
                    preventDefault: () => {{}},
                }});
            }})()
        """)

    def _fire_window_pointermove(self, browser_page, client_x, client_y):
        """Dispatch a real pointermove event on window."""
        browser_page.evaluate(f"""
            (() => {{
                const evt = new PointerEvent('pointermove', {{
                    bubbles: true,
                    cancelable: true,
                    clientX: {client_x},
                    clientY: {client_y},
                    pointerId: 1,
                    pointerType: 'mouse',
                }});
                window.dispatchEvent(evt);
            }})()
        """)

    def _fire_window_pointerup(self, browser_page, client_x, client_y):
        """Dispatch a real pointerup event on window."""
        browser_page.evaluate(f"""
            (() => {{
                const evt = new PointerEvent('pointerup', {{
                    bubbles: true,
                    cancelable: true,
                    clientX: {client_x},
                    clientY: {client_y},
                    pointerId: 1,
                    pointerType: 'mouse',
                }});
                window.dispatchEvent(evt);
            }})()
        """)

    def _get_phase(self, browser_page):
        return browser_page.evaluate(
            "Alpine.$data(document.querySelector('[x-data]'))?.drag?.phase || null"
        )

    def _get_drag(self, browser_page):
        return browser_page.evaluate(
            "JSON.parse(JSON.stringify(Alpine.$data(document.querySelector('[x-data]'))?.drag || null))"
        )

    def test_pointermove_window_transitions_phase(self, browser_page):
        """Real window pointermove event transitions drag from pressed to dragging.

        This is the key regression test for #770. The setPointerCapture bug
        made pointermove events bypass the @pointermove.window handler.
        Verifying that a real window-level pointermove reaches the handler and
        drives the state machine proves the pipeline is wired correctly.
        """
        self._seed_drag_state(browser_page, start_x=100, start_y=100)

        # Verify initial state is 'pressed'
        assert self._get_phase(browser_page) == "pressed"

        # Fire real window pointermove 50px away — well past 4px threshold
        self._fire_window_pointermove(browser_page, 150, 100)

        # Phase should now be 'dragging'
        phase = self._get_phase(browser_page)
        assert phase == "dragging", (
            f"@pointermove.window handler did not transition phase to dragging "
            f"(got: {phase}). This indicates the window-level event listener is "
            f"not wired — exactly the regression class that #770 identified."
        )

    def test_pointermove_below_threshold_stays_pressed(self, browser_page):
        """Real window pointermove below 4px threshold stays in pressed phase."""
        self._seed_drag_state(browser_page, start_x=100, start_y=100)

        # Fire real window pointermove only 2px away
        self._fire_window_pointermove(browser_page, 102, 100)

        phase = self._get_phase(browser_page)
        assert phase == "pressed", (
            f"Drag should stay in pressed phase below 4px threshold (got: {phase})"
        )

    def test_pointerup_window_clears_drag(self, browser_page):
        """Real window pointerup event clears drag state after drop."""
        self._seed_drag_state(browser_page, start_x=100, start_y=100)

        # Move to dragging phase
        self._fire_window_pointermove(browser_page, 200, 100)
        assert self._get_phase(browser_page) == "dragging"

        # Fire real window pointerup
        self._fire_window_pointerup(browser_page, 200, 100)

        # Drag should be cleared
        drag = self._get_drag(browser_page)
        assert drag is None, f"@pointerup.window handler did not clear drag state (got: {drag})"

    def test_multiple_pointermove_tracks_position(self, browser_page):
        """Real window pointermove events update currentX/currentY correctly."""
        self._seed_drag_state(browser_page, start_x=100, start_y=100)

        # Fire several pointermove events
        self._fire_window_pointermove(browser_page, 120, 110)
        self._fire_window_pointermove(browser_page, 150, 130)
        self._fire_window_pointermove(browser_page, 180, 150)

        drag = self._get_drag(browser_page)
        assert drag is not None, "Drag state was cleared unexpectedly"
        assert drag["currentX"] == 180, (
            f"currentX not updated by pointermove (got: {drag.get('currentX')})"
        )
        assert drag["currentY"] == 150, (
            f"currentY not updated by pointermove (got: {drag.get('currentY')})"
        )

        # Clean up
        self._fire_window_pointerup(browser_page, 180, 150)
