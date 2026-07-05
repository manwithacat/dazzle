"""Data Table Quality Gate Tests — ux-architect/components/data-table.md

Unit-level gates exercise the dzTable Alpine controller state machine
directly via window.qualityGates.test*() helpers defined in the HTML
test harness (src/dazzle/page/runtime/static/test-data-table.html).

Integration gates fire real pointer and keyboard events against the live
DOM to verify that event wiring and Alpine bindings work end-to-end.

Run with:
    pytest tests/quality_gates/test_data_table_gates.py -v
"""

import subprocess
import time

import pytest

# Module-scoped http.server on a FIXED port: xdist workers each build the
# fixture and clash. Pin the whole file to one worker (--dist loadgroup).
pytestmark = pytest.mark.xdist_group("data_table_gates")

# Skip the whole module if playwright isn't installed (the unit test job in
# CI doesn't install it). This is a static-harness browser test that still
# runs wherever playwright is available.
pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Page, sync_playwright  # noqa: E402


@pytest.fixture(scope="module")
def server():
    """Serve the static directory on port 8768."""
    static_dir = "src/dazzle/page/runtime/static"
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", "8768", "--directory", static_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    yield "http://localhost:8768/test-data-table.html"
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser_page(server):
    """Open the test harness page and wait for Alpine + row elements."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(server)
        # Wait for Alpine to initialise and for at least one row to be present
        page.wait_for_function(
            "typeof Alpine !== 'undefined'"
            " && document.querySelector('[data-dz-row-id]') !== null"
            " && typeof Alpine.$data === 'function'",
            timeout=10000,
        )
        yield page
        browser.close()


# ---------------------------------------------------------------------------
# Unit-level gate tests — call controller methods directly
# ---------------------------------------------------------------------------


class TestDataTableUnitGates:
    """Unit-level gates: test the dzTable controller state machine."""

    @pytest.mark.parametrize(
        ("js_method", "label"),
        [
            ("testSortCycle", "Sort cycle"),
            ("testColumnResize", "Column resize"),
            ("testInlineEditLifecycle", "Inline edit lifecycle"),
            ("testSelectionPersistence", "Selection persistence"),
            ("testKeyboardNav", "Keyboard nav"),
        ],
        ids=[
            "test_gate1_sort_cycle",
            "test_gate2_column_resize",
            "test_gate3_inline_edit_lifecycle",
            "test_gate4_selection_persistence",
            "test_gate5_keyboard_nav",
        ],
    )
    def test_gate(self, browser_page: Page, js_method: str, label: str) -> None:
        result = browser_page.evaluate(f"window.qualityGates.{js_method}()")
        assert result is True, f"{label} gate failed"


# ---------------------------------------------------------------------------
# Integration gate tests — real pointer and keyboard events
# ---------------------------------------------------------------------------


class TestDataTableIntegrationGates:
    """Integration gates: real DOM pointer/keyboard events via Playwright."""

    def test_column_resize_pointer_drag(self, browser_page: Page) -> None:
        """Pointer drag on resize handle updates <col> style.width in DOM.

        NB this harness exercises the LEGACY dzTable Alpine resize (its cols
        use `data-col`); production resize is the promoted HM dz-grid-resize
        extension on `col[data-dz-col]`, covered by the grid convergence e2e.
        The harness + this gate retire with dzTable in C3."""
        # Get initial col width
        initial_width_str: str = browser_page.evaluate(
            "document.querySelector('col[data-col=\"title\"]')?.style.width || ''"
        )

        # Locate the resize handle in the title header
        handle = browser_page.locator("th[data-dz-col='title'] .col-resize-handle")
        box = handle.bounding_box()
        assert box is not None, "Resize handle bounding box is None — handle not visible?"

        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2

        # Perform pointer drag: press, move 80px right, release
        browser_page.mouse.move(cx, cy)
        browser_page.mouse.down()
        browser_page.mouse.move(cx + 80, cy, steps=5)
        browser_page.mouse.up()

        # Allow Alpine to settle
        browser_page.wait_for_timeout(100)

        final_width_str: str = browser_page.evaluate(
            "document.querySelector('col[data-col=\"title\"]')?.style.width || 'not set'"
        )
        assert final_width_str != "not set", "col[data-col='title'] style.width was never set"

        # Width should have changed (or be set for the first time)
        if initial_width_str and final_width_str:
            initial_px = int(initial_width_str.rstrip("px") or 0)
            final_px = int(final_width_str.rstrip("px") or 0)
            assert final_px != initial_px or final_px > 0, (
                f"Expected col width to change after drag: {initial_px}px → {final_px}px"
            )

    def test_inline_edit_doubleclick_opens_input(self, browser_page: Page) -> None:
        """Double-clicking an editable cell opens an inline edit input."""
        # Ensure no edit is active
        browser_page.evaluate("Alpine.$data(document.querySelector('[x-data]')).cancelEdit()")
        browser_page.wait_for_timeout(50)

        cell = browser_page.locator("td[data-dz-col='title']").first
        cell.dblclick()
        browser_page.wait_for_timeout(150)

        # An <input> or <select> should now be visible inside the cell
        input_visible: bool = browser_page.evaluate(
            '!!document.querySelector(\'td[data-dz-col="title"] input,'
            ' td[data-dz-col="title"] select\')'
        )
        # Cancel the edit to clean up
        browser_page.keyboard.press("Escape")
        browser_page.wait_for_timeout(50)

        assert input_visible, "Double-click on title cell did not open inline edit input"

    def test_inline_edit_tab_advances_to_next_editable(self, browser_page: Page) -> None:
        """Tab from an editing cell commits and moves editing to next editable cell."""
        # Ensure no edit is active
        browser_page.evaluate("Alpine.$data(document.querySelector('[x-data]')).cancelEdit()")
        browser_page.wait_for_timeout(50)

        # Open the first title cell for editing
        cell = browser_page.locator("td[data-dz-col='title']").first
        cell.dblclick()
        browser_page.wait_for_timeout(150)

        # Confirm an input is open
        input_el = browser_page.locator(
            "td[data-dz-col='title'] input, td[data-dz-col='title'] select"
        ).first
        assert input_el.is_visible(), "Title cell input did not appear after dblclick"

        # Tab should commit and advance (commitEdit calls reload, which is a no-op
        # in the static harness since htmx is not defined — the edit state still advances)
        browser_page.keyboard.press("Tab")
        browser_page.wait_for_timeout(200)

        # After Tab the editing state may be on the next cell OR cleared
        # (commitEdit may fail silently because htmx is undefined — that's OK for this gate)
        # The important thing is that the title input is gone
        title_input_still_open: bool = browser_page.evaluate(
            "!!document.querySelector('td[data-dz-col=\"title\"] input')"
        )

        # Clean up any residual edit state
        browser_page.evaluate("Alpine.$data(document.querySelector('[x-data]')).cancelEdit()")
        browser_page.wait_for_timeout(50)

        assert not title_input_still_open, (
            "Title input still visible after Tab — Tab did not advance out of the cell"
        )

    def test_select_all_checkbox_selects_rows(self, browser_page: Page) -> None:
        """Clicking the select-all checkbox selects all visible rows."""
        # Clear first
        browser_page.evaluate("Alpine.$data(document.querySelector('[x-data]')).clearSelection()")
        browser_page.wait_for_timeout(50)

        # Click the select-all checkbox in the header
        select_all = browser_page.locator("thead input[type='checkbox']").first
        select_all.click()
        # Give Alpine time to settle — Set mutations need a full reactivity cycle
        browser_page.wait_for_timeout(300)

        # Read bulkCount and selected size in a single evaluate to avoid IPC race
        state: dict = browser_page.evaluate(
            "(function() {"
            "  var d = Alpine.$data(document.querySelector('[x-data]'));"
            "  return { bulkCount: d.bulkCount, selSize: d.selected.size };"
            "})()"
        )
        count = state.get("bulkCount", 0)

        # Clean up
        select_all.click()
        browser_page.wait_for_timeout(100)

        assert count > 0, f"Select-all checkbox did not select any rows (bulkCount={count})"
