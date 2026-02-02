"""
Pytest configuration for E2E UX tests.

This configures fixtures for UX coverage tracking and browser console logging.
"""

import os
from collections.abc import Generator
from dataclasses import dataclass, field

import pytest
from playwright.sync_api import ConsoleMessage, Page, sync_playwright
from ux_coverage import UXCoverageTracker

# =============================================================================
# Console Logging Infrastructure
# =============================================================================


@dataclass
class ConsoleLogEntry:
    """A single browser console log entry."""

    type: str  # log, warning, error, info, debug
    text: str
    url: str
    line_number: int
    timestamp: float = 0.0


@dataclass
class PageDiagnostics:
    """Collected diagnostics from a page session."""

    console_logs: list[ConsoleLogEntry] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    network_failures: list[str] = field(default_factory=list)

    def add_console(self, msg: ConsoleMessage) -> None:
        """Add a console message to the log."""
        loc = msg.location
        self.console_logs.append(
            ConsoleLogEntry(
                type=msg.type,
                text=msg.text,
                url=loc.get("url", ""),
                line_number=loc.get("lineNumber", 0),
            )
        )

    def add_error(self, error: Exception) -> None:
        """Add a page error."""
        self.page_errors.append(str(error))

    def add_network_failure(self, url: str, error: str) -> None:
        """Add a network failure."""
        self.network_failures.append(f"{url}: {error}")

    def has_errors(self) -> bool:
        """Check if any errors were captured."""
        return bool(self.page_errors) or any(log.type == "error" for log in self.console_logs)

    def get_errors(self) -> list[str]:
        """Get all error messages."""
        errors = []
        for log in self.console_logs:
            if log.type == "error":
                errors.append(f"CONSOLE ERROR [{log.url}:{log.line_number}]: {log.text}")
        errors.extend(f"PAGE ERROR: {e}" for e in self.page_errors)
        return errors

    def print_summary(self, test_name: str = "") -> None:
        """Print a summary of all captured diagnostics."""
        prefix = f"[{test_name}] " if test_name else ""

        if self.console_logs:
            print(f"\n{prefix}=== Browser Console Logs ({len(self.console_logs)} entries) ===")
            for log in self.console_logs:
                loc_info = f"{log.url}:{log.line_number}" if log.url else "unknown"
                print(f"  {log.type.upper():8} [{loc_info}] {log.text[:200]}")

        if self.page_errors:
            print(f"\n{prefix}=== Page Errors ({len(self.page_errors)} entries) ===")
            for error in self.page_errors:
                print(f"  ERROR: {error[:200]}")

        if self.network_failures:
            print(f"\n{prefix}=== Network Failures ({len(self.network_failures)} entries) ===")
            for failure in self.network_failures:
                print(f"  FAILED: {failure[:200]}")


# Global tracker instance (shared across all tests)
_ux_tracker: UXCoverageTracker | None = None


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "docker: mark test as requiring docker")


def pytest_sessionstart(session):
    """Initialize UX coverage tracker at session start."""
    global _ux_tracker
    api_url = os.environ.get("DAZZLE_BASE_URL", "http://localhost:8000")
    _ux_tracker = UXCoverageTracker(api_url=api_url)


def pytest_sessionfinish(session, exitstatus):
    """Print and save UX coverage report at session end."""
    global _ux_tracker
    if _ux_tracker:
        print("\n")
        _ux_tracker.print_report()

        # Save JSON report
        screenshot_dir = os.environ.get("SCREENSHOT_DIR", "/screenshots")
        if os.path.exists(screenshot_dir):
            report_path = os.path.join(screenshot_dir, "ux_coverage.json")
            _ux_tracker.save_report(report_path)
            print(f"\nUX Coverage report saved to: {report_path}")


@pytest.fixture(scope="session")
def ux_tracker():
    """Get the shared UX coverage tracker."""
    global _ux_tracker
    if _ux_tracker is None:
        api_url = os.environ.get("DAZZLE_BASE_URL", "http://localhost:8000")
        _ux_tracker = UXCoverageTracker(api_url=api_url)
    return _ux_tracker


@pytest.fixture
def track_route(ux_tracker):
    """Fixture to track route visits."""

    def _track(path: str):
        ux_tracker.visit_route(path)

    return _track


@pytest.fixture
def track_component(ux_tracker):
    """Fixture to track component tests."""

    def _track(name: str, aspects: list[str] | None = None):
        ux_tracker.test_component(name, aspects)

    return _track


@pytest.fixture
def track_crud(ux_tracker):
    """Fixture to track CRUD operation tests."""

    def _track(entity: str, operation: str):
        ux_tracker.test_crud(entity, operation)

    return _track


@pytest.fixture
def track_ui_view(ux_tracker):
    """Fixture to track UI view tests."""

    def _track(entity: str, view: str):
        ux_tracker.test_ui_view(entity, view)

    return _track


@pytest.fixture
def track_interaction(ux_tracker):
    """Fixture to track interaction types."""

    def _track(interaction_type: str):
        ux_tracker.test_interaction(interaction_type)

    return _track


# =============================================================================
# Browser/Page Fixtures with Console Logging
# =============================================================================

# Global browser instance for module-level sharing
_browser_instance = None


@pytest.fixture(scope="module")
def browser():
    """Create a browser instance for the test module."""
    global _browser_instance
    with sync_playwright() as p:
        _browser_instance = p.chromium.launch(headless=True)
        yield _browser_instance
        _browser_instance.close()
        _browser_instance = None


@pytest.fixture
def page_diagnostics() -> PageDiagnostics:
    """Create a fresh diagnostics collector for each test."""
    return PageDiagnostics()


@pytest.fixture
def page(browser, page_diagnostics, request) -> Generator[Page, None, None]:
    """Create a new page for each test with console logging enabled.

    This fixture intercepts all browser console messages, page errors, and
    network failures to help diagnose rendering issues in E2E tests.

    Console messages are printed at the end of each test for debugging.
    """
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    # Set up console message listener
    def on_console(msg: ConsoleMessage) -> None:
        page_diagnostics.add_console(msg)
        # Also print immediately for real-time debugging
        loc = msg.location
        loc_info = f"{loc.get('url', 'unknown')}:{loc.get('lineNumber', 0)}"
        print(f"  BROWSER {msg.type.upper():8} [{loc_info}] {msg.text[:150]}")

    # Set up page error listener
    def on_page_error(error: Exception) -> None:
        page_diagnostics.add_error(error)
        print(f"  PAGE ERROR: {error}")

    # Set up request failure listener
    def on_request_failed(request) -> None:
        failure = request.failure
        if failure:
            page_diagnostics.add_network_failure(request.url, failure)
            print(f"  NETWORK FAIL: {request.url} - {failure}")

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)

    yield page

    # Print summary after test
    test_name = request.node.name if request else ""
    if page_diagnostics.console_logs or page_diagnostics.page_errors:
        page_diagnostics.print_summary(test_name)

    page.close()
    context.close()


@pytest.fixture
def page_with_diagnostics(page, page_diagnostics) -> tuple[Page, PageDiagnostics]:
    """Return both the page and its diagnostics collector.

    Use this fixture when you need to inspect console logs or errors
    programmatically within a test.
    """
    return page, page_diagnostics
