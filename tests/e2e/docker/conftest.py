"""
Pytest configuration for E2E UX tests.

This configures fixtures for UX coverage tracking.
"""

import os

import pytest
from ux_coverage import UXCoverageTracker

# Global tracker instance (shared across all tests)
_ux_tracker: UXCoverageTracker | None = None


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "docker: mark test as requiring docker")


def pytest_sessionstart(session):
    """Initialize UX coverage tracker at session start."""
    global _ux_tracker
    api_url = os.environ.get("DNR_BASE_URL", "http://localhost:8000")
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
        api_url = os.environ.get("DNR_BASE_URL", "http://localhost:8000")
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
