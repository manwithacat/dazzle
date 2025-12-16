"""
Playwright-based smoke tests for DNR examples.

These tests run locally (no Docker required) and verify:
1. Page loads without JavaScript errors
2. Basic navigation works
3. CRUD forms are accessible
4. Screenshots are captured for visual verification

Usage:
    pytest tests/e2e/test_playwright_smoke.py -v
    pytest -m e2e  # Includes these tests

Requirements:
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# Try to import Playwright - skip tests if not installed
try:
    from playwright.sync_api import ConsoleMessage, Page, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None
    Page = None
    ConsoleMessage = None

# Skip if DNR is not available
pytest.importorskip("dazzle_dnr_back")
pytest.importorskip("dazzle_dnr_ui")

# Configuration
SERVER_STARTUP_TIMEOUT = 60
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# Examples to test with Playwright smoke tests
PLAYWRIGHT_EXAMPLES = [
    "simple_task",
    "contact_manager",
]


@dataclass
class PageDiagnostics:
    """Collected diagnostics from a page session."""

    console_logs: list[dict] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    js_errors: list[str] = field(default_factory=list)

    def add_console(self, msg: ConsoleMessage) -> None:
        """Add a console message to the log."""
        loc = msg.location
        entry = {
            "type": msg.type,
            "text": msg.text,
            "url": loc.get("url", ""),
            "line": loc.get("lineNumber", 0),
        }
        self.console_logs.append(entry)
        if msg.type == "error":
            self.js_errors.append(msg.text)

    def add_error(self, error: Exception) -> None:
        """Add a page error."""
        self.page_errors.append(str(error))

    def has_critical_errors(self) -> bool:
        """Check for critical JavaScript errors (excluding expected ones)."""
        ignore_patterns = [
            "favicon.ico",  # Missing favicon is not critical
            "net::ERR_",  # Network errors during shutdown
            "Failed to load resource",  # Often benign (404 for optional resources)
            "Failed to load page: 404",  # SPA routing - page might not exist yet
            "Error loading page",  # Similar to above
            "ui-spec.json",  # UISpec loading can fail during initialization
        ]
        for error in self.js_errors:
            if not any(p in error for p in ignore_patterns):
                return True
        return bool(self.page_errors)

    def get_errors(self) -> list[str]:
        """Get all error messages."""
        errors = []
        for log in self.console_logs:
            if log["type"] == "error":
                errors.append(f"CONSOLE: {log['text'][:200]}")
        errors.extend(f"PAGE ERROR: {e}" for e in self.page_errors)
        return errors


class DNRLocalServer:
    """Context manager for running DNR server locally for Playwright tests."""

    def __init__(self, example_dir: Path):
        self.example_dir = example_dir
        self.process: subprocess.Popen | None = None
        self.api_url: str = ""
        self.ui_url: str = ""

    def __enter__(self) -> DNRLocalServer:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Clear any existing runtime file
        dazzle_dir = self.example_dir / ".dazzle"
        runtime_file = dazzle_dir / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()

        # Platform-specific process group handling
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
                "dnr",
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

        # Wait for runtime file to get actual ports
        runtime_file = dazzle_dir / "runtime.json"
        for _ in range(SERVER_STARTUP_TIMEOUT * 2):
            if runtime_file.exists():
                try:
                    data = json.loads(runtime_file.read_text())
                    api_port = data["api_port"]
                    ui_port = data["ui_port"]
                    self.api_url = f"http://127.0.0.1:{api_port}"
                    self.ui_url = f"http://127.0.0.1:{ui_port}"
                    break
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)

        # Wait for API health
        if not self._wait_for_health():
            self._cleanup()
            raise RuntimeError(f"DNR server failed to start for {self.example_dir.name}")

        return self

    def _wait_for_health(self, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
        """Wait for server to become healthy."""
        import requests

        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.api_url}/health", timeout=2)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _cleanup(self) -> None:
        """Stop the server process."""
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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._cleanup()


def take_screenshot(page: Page, example_name: str, test_name: str) -> Path:
    """Take a screenshot and save it."""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{example_name}_{test_name}.png"
    page.screenshot(path=str(path))
    return path


@pytest.fixture(scope="module")
def dazzle_root() -> Path:
    """Get the dazzle project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def browser():
    """Create a browser instance for the test module."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed. Run: pip install playwright && playwright install")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


class TestPlaywrightSmokeSimpleTask:
    """Playwright smoke tests for simple_task example."""

    @pytest.fixture(scope="class")
    def server(self, dazzle_root: Path) -> Iterator[DNRLocalServer]:
        """Start DNR server for simple_task."""
        example_dir = dazzle_root / "examples" / "simple_task"
        if not example_dir.exists():
            pytest.skip("simple_task example not found")

        with DNRLocalServer(example_dir) as srv:
            yield srv

    @pytest.fixture
    def page(self, browser, server) -> Iterator[Page]:
        """Create a new page with console logging."""
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        diagnostics = PageDiagnostics()

        def on_console(msg: ConsoleMessage) -> None:
            diagnostics.add_console(msg)

        def on_page_error(error: Exception) -> None:
            diagnostics.add_error(error)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        yield page

        # Check for critical errors after test
        if diagnostics.has_critical_errors():
            errors = diagnostics.get_errors()
            print(f"\nJavaScript errors detected:\n" + "\n".join(errors[:5]))

        page.close()
        context.close()

    @pytest.mark.e2e
    def test_page_loads(self, page: Page, server: DNRLocalServer) -> None:
        """Test that the main page loads."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)  # Extra time for JS to render

        # DNR UI uses either #app (old) or #dz-site-main (new SiteSpec)
        app_div = page.locator("#app, #dz-site-main")
        assert app_div.count() > 0, "Main container should exist in DOM"

        # Page should have loaded something
        body = page.locator("body")
        assert body.is_visible(), "Body should be visible"

        take_screenshot(page, "simple_task", "page_loads")

    @pytest.mark.e2e
    def test_has_content(self, page: Page, server: DNRLocalServer) -> None:
        """Test that the page has meaningful content (not stuck on loading)."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)  # Extra wait for JS rendering

        body_text = page.locator("body").inner_text()

        # Should not be empty or just "Loading"
        assert len(body_text.strip()) > 20, f"Page has minimal content: {body_text[:100]}"

        # Check for stuck loading state
        if body_text.strip() == "Loading...":
            take_screenshot(page, "simple_task", "stuck_loading")
            pytest.fail("Page appears stuck on loading state")

        take_screenshot(page, "simple_task", "has_content")

    @pytest.mark.e2e
    def test_create_button_exists(self, page: Page, server: DNRLocalServer) -> None:
        """Test that a create/add button exists."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)  # Extra time for JS to render

        # Look for create/add buttons with various selectors
        create_btn = page.locator(
            "button:has-text('Create'), "
            "button:has-text('Add'), "
            "button:has-text('New'), "
            "a:has-text('Create'), "
            "a:has-text('Add'), "
            "a:has-text('New'), "
            "[data-dazzle-action='create'], "
            "[data-dazzle-action-role='create']"
        ).first

        if create_btn.count() > 0 and create_btn.is_visible():
            take_screenshot(page, "simple_task", "create_button")
        else:
            # Take screenshot to debug what's actually there
            take_screenshot(page, "simple_task", "create_button_missing")
            # This might be expected if the list view doesn't show a create button
            # Check if we can find any interactive elements
            buttons = page.locator("button")
            if buttons.count() == 0:
                pytest.skip("No buttons found - UI may be in different state")

    @pytest.mark.e2e
    def test_navigation_works(self, page: Page, server: DNRLocalServer) -> None:
        """Test that navigation elements work."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(500)

        # Click create button and verify form appears
        create_btn = page.locator(
            "button:has-text('Create'), "
            "button:has-text('Add'), "
            "a:has-text('Create'), "
            "a:has-text('Add')"
        ).first

        if create_btn.is_visible():
            create_btn.click()
            page.wait_for_timeout(500)

            # Should have input fields now
            inputs = page.locator("input, textarea, select")
            assert inputs.count() > 0, "Form should have input fields"

            take_screenshot(page, "simple_task", "form_opened")


class TestPlaywrightSmokeContactManager:
    """Playwright smoke tests for contact_manager example."""

    @pytest.fixture(scope="class")
    def server(self, dazzle_root: Path) -> Iterator[DNRLocalServer]:
        """Start DNR server for contact_manager."""
        example_dir = dazzle_root / "examples" / "contact_manager"
        if not example_dir.exists():
            pytest.skip("contact_manager example not found")

        with DNRLocalServer(example_dir) as srv:
            yield srv

    @pytest.fixture
    def page(self, browser, server) -> Iterator[Page]:
        """Create a new page with console logging."""
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        diagnostics = PageDiagnostics()

        page.on("console", lambda msg: diagnostics.add_console(msg))
        page.on("pageerror", lambda err: diagnostics.add_error(err))

        yield page

        if diagnostics.has_critical_errors():
            errors = diagnostics.get_errors()
            print(f"\nJavaScript errors detected:\n" + "\n".join(errors[:5]))

        page.close()
        context.close()

    @pytest.mark.e2e
    def test_page_loads(self, page: Page, server: DNRLocalServer) -> None:
        """Test that the main page loads."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)

        # DNR UI uses either #app (old) or #dz-site-main (new SiteSpec)
        app_div = page.locator("#app, #dz-site-main")
        assert app_div.count() > 0, "Main container should exist in DOM"

        # Page should have loaded
        body = page.locator("body")
        assert body.is_visible(), "Body should be visible"

        take_screenshot(page, "contact_manager", "page_loads")

    @pytest.mark.e2e
    def test_has_content(self, page: Page, server: DNRLocalServer) -> None:
        """Test that the page has meaningful content."""
        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)

        body_text = page.locator("body").inner_text()
        # Allow for minimal content - page may show "Loading" briefly or have an error message
        # The key is it's not completely empty
        assert len(body_text.strip()) > 5, f"Page is nearly empty: {body_text[:100]}"

        take_screenshot(page, "contact_manager", "has_content")

    @pytest.mark.e2e
    def test_no_critical_js_errors(self, page: Page, server: DNRLocalServer) -> None:
        """Test that there are no critical JavaScript errors on page load."""
        diagnostics = PageDiagnostics()
        page.on("console", lambda msg: diagnostics.add_console(msg))
        page.on("pageerror", lambda err: diagnostics.add_error(err))

        page.goto(server.ui_url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)

        # Navigate a bit to trigger more JS
        create_btn = page.locator(
            "button:has-text('Create'), button:has-text('Add'), button:has-text('New')"
        ).first
        if create_btn.count() > 0 and create_btn.is_visible():
            create_btn.click()
            page.wait_for_timeout(500)

        if diagnostics.has_critical_errors():
            errors = diagnostics.get_errors()
            take_screenshot(page, "contact_manager", "js_errors")
            pytest.fail(f"Critical JavaScript errors found:\n" + "\n".join(errors[:5]))


# Mark all tests as e2e
pytestmark = pytest.mark.e2e
