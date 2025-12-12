"""Pytest configuration for FieldTest Hub E2E tests.

Provides fixtures for browser automation, API access, persona switching,
and demo data management.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add helpers to path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from helpers.api_client import APIClient, ControlPlaneClient
from helpers.page_objects import FieldTestHubPage
from playwright.sync_api import Browser, ConsoleMessage, Page, sync_playwright

# =============================================================================
# Configuration
# =============================================================================

# Default URLs (can be overridden via environment variables or runtime.json)
DEFAULT_UI_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://localhost:8000"

# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Project root (for runtime file discovery)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _load_runtime_ports() -> tuple[str, str]:
    """
    Load port configuration from runtime.json if available.

    The DNR serve command writes a runtime.json file with the actual
    ports being used. This allows E2E tests to discover the correct
    ports automatically, even when using auto-allocated ports.

    Returns:
        Tuple of (ui_url, api_url)
    """
    runtime_file = PROJECT_ROOT / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            data = json.load(open(runtime_file))
            return data.get("ui_url", DEFAULT_UI_URL), data.get("api_url", DEFAULT_API_URL)
        except (json.JSONDecodeError, KeyError):
            pass
    return DEFAULT_UI_URL, DEFAULT_API_URL


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


# =============================================================================
# URL Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def ui_url() -> str:
    """Get the UI base URL.

    Priority:
    1. DNR_UI_URL environment variable
    2. .dazzle/runtime.json (written by `dazzle dnr serve`)
    3. Default localhost:3000
    """
    if "DNR_UI_URL" in os.environ:
        return os.environ["DNR_UI_URL"]
    runtime_ui, _ = _load_runtime_ports()
    return runtime_ui


@pytest.fixture(scope="session")
def api_url() -> str:
    """Get the API base URL.

    Priority:
    1. DNR_BASE_URL environment variable
    2. .dazzle/runtime.json (written by `dazzle dnr serve`)
    3. Default localhost:8000
    """
    if "DNR_BASE_URL" in os.environ:
        return os.environ["DNR_BASE_URL"]
    _, runtime_api = _load_runtime_ports()
    return runtime_api


# =============================================================================
# Browser/Page Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    """Create a browser instance for the test module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page_diagnostics() -> PageDiagnostics:
    """Create a fresh diagnostics collector for each test."""
    return PageDiagnostics()


@pytest.fixture
def page(
    browser: Browser, page_diagnostics: PageDiagnostics, request
) -> Generator[Page, None, None]:
    """Create a new page for each test with console logging enabled."""
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()

    # Set up console message listener
    def on_console(msg: ConsoleMessage) -> None:
        page_diagnostics.add_console(msg)

    def on_page_error(error: Exception) -> None:
        page_diagnostics.add_error(error)

    def on_request_failed(request) -> None:
        failure = request.failure
        if failure:
            page_diagnostics.add_network_failure(request.url, failure)

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)

    yield page

    # Print summary after test if there were issues
    test_name = request.node.name if request else ""
    if page_diagnostics.has_errors():
        page_diagnostics.print_summary(test_name)

    page.close()
    context.close()


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def api_client(api_url: str) -> Generator[APIClient, None, None]:
    """Create an API client for backend operations."""
    client = APIClient(api_url)
    yield client
    client.close()


@pytest.fixture(scope="session")
def control_plane(api_url: str) -> Generator[ControlPlaneClient, None, None]:
    """Create a control plane client for Dazzle Bar operations."""
    client = ControlPlaneClient(api_url)
    yield client
    client.close()


# =============================================================================
# Page Object Fixture
# =============================================================================


@pytest.fixture
def app(page: Page, ui_url: str) -> FieldTestHubPage:
    """Create a FieldTestHubPage instance."""
    return FieldTestHubPage(page, ui_url)


# =============================================================================
# Demo Data Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def demo_data() -> dict[str, Any]:
    """Load the static demo data fixtures.

    Returns:
        Dict containing all entity data and test users
    """
    demo_data_file = FIXTURES_DIR / "demo_data.json"
    if not demo_data_file.exists():
        pytest.skip(
            f"Demo data not found at {demo_data_file}. "
            "Run 'python fixtures/generate_fixtures.py' first."
        )

    with open(demo_data_file) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def test_users(demo_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Get test user configurations.

    Returns:
        Dict mapping persona ID to user data
    """
    return demo_data.get("test_users", {})


# =============================================================================
# Persona Switching Fixtures
# =============================================================================


@pytest.fixture
def as_engineer(
    control_plane: ControlPlaneClient, app: FieldTestHubPage
) -> Generator[FieldTestHubPage, None, None]:
    """Switch to Engineer persona and return the app.

    Use this fixture when a test requires Engineer access.
    """
    control_plane.set_persona("engineer")
    app.goto("/")  # Refresh to apply persona
    yield app


@pytest.fixture
def as_tester(
    control_plane: ControlPlaneClient, app: FieldTestHubPage
) -> Generator[FieldTestHubPage, None, None]:
    """Switch to Field Tester persona and return the app.

    Use this fixture when a test requires Field Tester access.
    """
    control_plane.set_persona("tester")
    app.goto("/")  # Refresh to apply persona
    yield app


@pytest.fixture
def as_manager(
    control_plane: ControlPlaneClient, app: FieldTestHubPage
) -> Generator[FieldTestHubPage, None, None]:
    """Switch to Manager persona and return the app.

    Use this fixture when a test requires Manager access.
    """
    control_plane.set_persona("manager")
    app.goto("/")  # Refresh to apply persona
    yield app


# =============================================================================
# Data Management Fixtures
# =============================================================================


@pytest.fixture
def reset_db(control_plane: ControlPlaneClient) -> None:
    """Reset the database before a test.

    This clears all data from all entities.
    """
    control_plane.reset_data()


@pytest.fixture
def seed_demo_data(
    control_plane: ControlPlaneClient,
    api_client: APIClient,
    demo_data: dict[str, Any],
) -> dict[str, Any]:
    """Reset database and seed with demo data.

    Returns:
        The seeded demo data for reference in tests
    """
    # Reset first
    control_plane.reset_data()

    # Seed each entity in order (respecting foreign key dependencies)
    entity_order = [
        "Tester",
        "Device",
        "FirmwareRelease",
        "IssueReport",
        "TestSession",
        "Task",
    ]

    for entity in entity_order:
        entity_data = demo_data.get("entities", {}).get(entity, [])
        for record in entity_data:
            try:
                api_client.create(entity, record)
            except Exception as e:
                print(f"Warning: Failed to seed {entity}: {e}")

    return demo_data


# =============================================================================
# Story Coverage Tracking
# =============================================================================


@dataclass
class StoryCoverageTracker:
    """Track which user stories have been tested."""

    tested_stories: dict[str, bool] = field(default_factory=dict)

    def mark_tested(self, story_id: str, passed: bool = True) -> None:
        """Mark a story as tested."""
        self.tested_stories[story_id] = passed

    def get_coverage(self) -> dict[str, Any]:
        """Get coverage summary."""
        total = 18  # Total stories in FieldTest Hub
        tested = len(self.tested_stories)
        passed = sum(1 for p in self.tested_stories.values() if p)
        return {
            "total": total,
            "tested": tested,
            "passed": passed,
            "failed": tested - passed,
            "coverage_percent": (tested / total) * 100 if total > 0 else 0,
            "stories": self.tested_stories,
        }


# Global tracker
_story_tracker: StoryCoverageTracker | None = None


@pytest.fixture(scope="session")
def story_tracker() -> StoryCoverageTracker:
    """Get the story coverage tracker."""
    global _story_tracker
    if _story_tracker is None:
        _story_tracker = StoryCoverageTracker()
    return _story_tracker


def pytest_sessionfinish(session, exitstatus):
    """Print story coverage report at session end."""
    global _story_tracker
    if _story_tracker and _story_tracker.tested_stories:
        coverage = _story_tracker.get_coverage()
        print("\n")
        print("=" * 60)
        print("STORY COVERAGE REPORT")
        print("=" * 60)
        print(f"Total Stories: {coverage['total']}")
        print(f"Tested: {coverage['tested']} ({coverage['coverage_percent']:.1f}%)")
        print(f"Passed: {coverage['passed']}")
        print(f"Failed: {coverage['failed']}")
        print("=" * 60)
