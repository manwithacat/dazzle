"""
UX Coverage Measurement for the Dazzle runtime.

This module provides a system for measuring "UX Coverage" - the percentage of
UI surface area that is exercised by our E2E tests.

Coverage Categories:
1. Route Coverage: What percentage of UISpec routes are visited?
2. Component Coverage: What percentage of components are rendered and tested?
3. Entity Coverage: For each entity, are all CRUD operations tested?
4. Interaction Coverage: What user actions (click, type, etc.) are exercised?

Usage:
    from ux_coverage import UXCoverageTracker

    tracker = UXCoverageTracker(ui_spec)

    # In your test:
    tracker.visit_route("/task/list")
    tracker.test_component("TaskList", aspects=["renders", "displays_data"])
    tracker.test_crud("Task", "create")

    # After tests:
    report = tracker.get_report()
    print(report.summary())
"""

import json
import os
from dataclasses import dataclass, field

import httpx


@dataclass
class EntityCoverage:
    """Track CRUD coverage for a single entity."""

    name: str
    operations_expected: set[str] = field(
        default_factory=lambda: {"create", "read", "update", "delete", "list"}
    )
    operations_tested: set[str] = field(default_factory=set)
    ui_views_expected: set[str] = field(default_factory=set)  # list, detail, create, edit
    ui_views_tested: set[str] = field(default_factory=set)

    @property
    def crud_coverage(self) -> float:
        if not self.operations_expected:
            return 100.0
        return (
            len(self.operations_tested & self.operations_expected)
            / len(self.operations_expected)
            * 100
        )

    @property
    def ui_coverage(self) -> float:
        if not self.ui_views_expected:
            return 100.0
        return (
            len(self.ui_views_tested & self.ui_views_expected) / len(self.ui_views_expected) * 100
        )


@dataclass
class ComponentCoverage:
    """Track coverage for a single UI component."""

    name: str
    aspects_expected: set[str] = field(
        default_factory=lambda: {"renders", "displays_data", "interactive"}
    )
    aspects_tested: set[str] = field(default_factory=set)

    @property
    def coverage(self) -> float:
        if not self.aspects_expected:
            return 100.0
        return len(self.aspects_tested & self.aspects_expected) / len(self.aspects_expected) * 100


@dataclass
class UXCoverageReport:
    """Final coverage report."""

    routes_total: int
    routes_visited: int
    components_total: int
    components_tested: int
    entities: dict[str, EntityCoverage]
    components: dict[str, ComponentCoverage]
    interactions_tested: set[str]

    @property
    def route_coverage(self) -> float:
        if self.routes_total == 0:
            return 100.0
        return self.routes_visited / self.routes_total * 100

    @property
    def component_coverage(self) -> float:
        if self.components_total == 0:
            return 100.0
        return self.components_tested / self.components_total * 100

    @property
    def entity_crud_coverage(self) -> float:
        if not self.entities:
            return 100.0
        coverages = [e.crud_coverage for e in self.entities.values()]
        return sum(coverages) / len(coverages)

    @property
    def entity_ui_coverage(self) -> float:
        if not self.entities:
            return 100.0
        coverages = [e.ui_coverage for e in self.entities.values()]
        return sum(coverages) / len(coverages)

    @property
    def overall_coverage(self) -> float:
        """Weighted average of all coverage types."""
        weights = {
            "routes": 0.2,
            "components": 0.2,
            "entity_crud": 0.3,
            "entity_ui": 0.3,
        }
        return (
            self.route_coverage * weights["routes"]
            + self.component_coverage * weights["components"]
            + self.entity_crud_coverage * weights["entity_crud"]
            + self.entity_ui_coverage * weights["entity_ui"]
        )

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            "=" * 60,
            "UX COVERAGE REPORT",
            "=" * 60,
            "",
            f"Overall Coverage: {self.overall_coverage:.1f}%",
            "",
            "--- Route Coverage ---",
            f"Routes visited: {self.routes_visited}/{self.routes_total} ({self.route_coverage:.1f}%)",
            "",
            "--- Component Coverage ---",
            f"Components tested: {self.components_tested}/{self.components_total} ({self.component_coverage:.1f}%)",
            "",
            "--- Entity CRUD Coverage ---",
            f"Average CRUD coverage: {self.entity_crud_coverage:.1f}%",
        ]

        for name, entity in self.entities.items():
            tested = ", ".join(sorted(entity.operations_tested)) or "none"
            missing = entity.operations_expected - entity.operations_tested
            missing_str = ", ".join(sorted(missing)) if missing else "none"
            lines.append(
                f"  {name}: {entity.crud_coverage:.0f}% (tested: {tested}; missing: {missing_str})"
            )

        lines.extend(
            [
                "",
                "--- Entity UI Coverage ---",
                f"Average UI coverage: {self.entity_ui_coverage:.1f}%",
            ]
        )

        for name, entity in self.entities.items():
            tested = ", ".join(sorted(entity.ui_views_tested)) or "none"
            missing = entity.ui_views_expected - entity.ui_views_tested
            missing_str = ", ".join(sorted(missing)) if missing else "none"
            lines.append(
                f"  {name}: {entity.ui_coverage:.0f}% (tested: {tested}; missing: {missing_str})"
            )

        lines.extend(
            [
                "",
                "--- Interactions ---",
                f"Interaction types tested: {', '.join(sorted(self.interactions_tested)) or 'none'}",
                "",
                "=" * 60,
            ]
        )

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Export as JSON for CI integration."""
        return {
            "overall_coverage": round(self.overall_coverage, 2),
            "route_coverage": round(self.route_coverage, 2),
            "component_coverage": round(self.component_coverage, 2),
            "entity_crud_coverage": round(self.entity_crud_coverage, 2),
            "entity_ui_coverage": round(self.entity_ui_coverage, 2),
            "routes": {
                "total": self.routes_total,
                "visited": self.routes_visited,
            },
            "components": {
                "total": self.components_total,
                "tested": self.components_tested,
            },
            "entities": {
                name: {
                    "crud_coverage": round(e.crud_coverage, 2),
                    "ui_coverage": round(e.ui_coverage, 2),
                    "operations_tested": list(e.operations_tested),
                    "operations_missing": list(e.operations_expected - e.operations_tested),
                    "ui_views_tested": list(e.ui_views_tested),
                    "ui_views_missing": list(e.ui_views_expected - e.ui_views_tested),
                }
                for name, e in self.entities.items()
            },
            "interactions_tested": list(self.interactions_tested),
        }


class UXCoverageTracker:
    """
    Track UX coverage during test execution.

    Initialize with UISpec data to know what to expect,
    then call tracking methods during tests.
    """

    def __init__(self, ui_spec: dict | None = None, api_url: str | None = None):
        """
        Initialize tracker with UISpec.

        Args:
            ui_spec: UISpec dictionary directly
            api_url: URL to fetch UISpec from (e.g., http://localhost:8000)
        """
        self.ui_spec = ui_spec or {}
        self.api_url = api_url

        if not self.ui_spec and api_url:
            self._fetch_ui_spec()

        # Expected surface area
        self._routes: set[str] = set()
        self._components: set[str] = set()
        self._entities: dict[str, EntityCoverage] = {}

        # What we've actually tested
        self._routes_visited: set[str] = set()
        self._components_tested: dict[str, ComponentCoverage] = {}
        self._interactions: set[str] = set()

        # Parse UISpec to set expectations
        self._parse_ui_spec()

    def _fetch_ui_spec(self):
        """Fetch UISpec from the running server."""
        try:
            # Try frontend server first (ui-spec.json)
            ui_url = os.environ.get("DAZZLE_UI_URL", self.api_url)
            response = httpx.get(f"{ui_url}/ui-spec.json", timeout=5)
            if response.status_code == 200:
                self.ui_spec = response.json()
                return
        except Exception:
            pass

        try:
            # Fall back to API server
            response = httpx.get(f"{self.api_url}/api/ui-spec", timeout=5)
            if response.status_code == 200:
                self.ui_spec = response.json()
        except Exception:
            pass

    def _parse_ui_spec(self):
        """Parse UISpec to extract expected routes, components, entities."""
        # Extract routes
        for workspace in self.ui_spec.get("workspaces", []):
            for route in workspace.get("routes", []):
                self._routes.add(route.get("path", ""))

        # Extract components
        for component in self.ui_spec.get("components", []):
            name = component.get("name", "")
            if name:
                self._components.add(name)
                # Determine expected aspects based on component type
                aspects = {"renders"}
                if "List" in name or "Table" in name:
                    aspects.add("displays_data")
                    aspects.add("interactive")
                elif "Form" in name or "Create" in name or "Edit" in name:
                    aspects.add("has_inputs")
                    aspects.add("submittable")
                elif "Detail" in name:
                    aspects.add("displays_data")

                self._components_tested[name] = ComponentCoverage(
                    name=name, aspects_expected=aspects, aspects_tested=set()
                )

        # Extract entities (from component naming convention)
        entity_names: set[str] = set()
        for component in self.ui_spec.get("components", []):
            name = component.get("name", "")
            # Extract entity name from component name (e.g., TaskList -> Task)
            for suffix in ["List", "Detail", "Create", "Edit", "Form"]:
                if name.endswith(suffix):
                    entity_name = name[: -len(suffix)]
                    if entity_name:
                        entity_names.add(entity_name)

        # Create entity coverage trackers
        for entity in entity_names:
            ui_views = set()
            for suffix in ["List", "Detail", "Create", "Edit"]:
                if f"{entity}{suffix}" in self._components:
                    ui_views.add(suffix.lower())

            self._entities[entity] = EntityCoverage(
                name=entity,
                ui_views_expected=ui_views,
            )

    # --- Tracking Methods ---

    def visit_route(self, path: str):
        """Record that a route was visited."""
        # Normalize path (handle dynamic segments)
        normalized = self._normalize_route(path)
        self._routes_visited.add(normalized)

    def _normalize_route(self, path: str) -> str:
        """Normalize a route path for matching."""
        # Convert /task/123 to /task/:id
        import re

        # UUID pattern
        normalized = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/:id", path
        )
        # Numeric ID pattern
        normalized = re.sub(r"/\d+", "/:id", normalized)
        return normalized

    def test_component(self, name: str, aspects: list[str] | None = None):
        """Record that a component was tested with certain aspects."""
        if name not in self._components_tested:
            self._components_tested[name] = ComponentCoverage(name=name)

        if aspects:
            self._components_tested[name].aspects_tested.update(aspects)
        else:
            # Default: mark as rendered
            self._components_tested[name].aspects_tested.add("renders")

    def test_crud(self, entity: str, operation: str):
        """Record that a CRUD operation was tested for an entity."""
        if entity not in self._entities:
            self._entities[entity] = EntityCoverage(name=entity)
        self._entities[entity].operations_tested.add(operation)

    def test_ui_view(self, entity: str, view: str):
        """Record that a UI view was tested for an entity."""
        if entity not in self._entities:
            self._entities[entity] = EntityCoverage(name=entity)
        self._entities[entity].ui_views_tested.add(view)

    def test_interaction(self, interaction_type: str):
        """Record that an interaction type was tested."""
        self._interactions.add(interaction_type)

    # --- Reporting ---

    def get_report(self) -> UXCoverageReport:
        """Generate coverage report."""
        # Count components with at least one aspect tested
        components_tested = sum(1 for c in self._components_tested.values() if c.aspects_tested)

        return UXCoverageReport(
            routes_total=len(self._routes),
            routes_visited=len(self._routes_visited & self._routes),
            components_total=len(self._components),
            components_tested=components_tested,
            entities=self._entities,
            components=self._components_tested,
            interactions_tested=self._interactions,
        )

    def save_report(self, path: str):
        """Save report to JSON file."""
        report = self.get_report()
        with open(path, "w") as f:
            json.dump(report.to_json(), f, indent=2)

    def print_report(self):
        """Print coverage report to stdout."""
        report = self.get_report()
        print(report.summary())


# --- Pytest Plugin ---


class UXCoveragePlugin:
    """
    Pytest plugin to track UX coverage across tests.

    Usage in conftest.py:
        from ux_coverage import UXCoveragePlugin

        def pytest_configure(config):
            config._ux_coverage = UXCoveragePlugin()
            config.pluginmanager.register(config._ux_coverage)
    """

    def __init__(self):
        self.tracker: UXCoverageTracker | None = None

    def pytest_sessionstart(self, session):
        """Initialize tracker at session start."""
        api_url = os.environ.get("DAZZLE_BASE_URL", "http://localhost:8000")
        self.tracker = UXCoverageTracker(api_url=api_url)

    def pytest_sessionfinish(self, session, exitstatus):
        """Print and save coverage report at session end."""
        if self.tracker:
            self.tracker.print_report()

            # Save JSON report
            screenshot_dir = os.environ.get("SCREENSHOT_DIR", "/screenshots")
            report_path = os.path.join(screenshot_dir, "ux_coverage.json")
            self.tracker.save_report(report_path)


# --- Pytest Fixtures ---


def create_coverage_fixtures():
    """
    Create pytest fixtures for UX coverage tracking.

    Add this to your conftest.py:
        from ux_coverage import create_coverage_fixtures, UXCoverageTracker

        # Create fixtures
        ux_tracker, mark_route_visited, ... = create_coverage_fixtures()
    """
    import pytest

    # Global tracker instance
    _tracker: UXCoverageTracker | None = None

    @pytest.fixture(scope="session")
    def ux_tracker():
        """Get or create the UX coverage tracker."""
        nonlocal _tracker
        if _tracker is None:
            api_url = os.environ.get("DAZZLE_BASE_URL", "http://localhost:8000")
            _tracker = UXCoverageTracker(api_url=api_url)
        return _tracker

    @pytest.fixture
    def mark_route_visited(ux_tracker):
        """Fixture to mark routes as visited."""

        def _mark(path: str):
            ux_tracker.visit_route(path)

        return _mark

    @pytest.fixture
    def mark_component_tested(ux_tracker):
        """Fixture to mark components as tested."""

        def _mark(name: str, aspects: list[str] | None = None):
            ux_tracker.test_component(name, aspects)

        return _mark

    @pytest.fixture
    def mark_crud_tested(ux_tracker):
        """Fixture to mark CRUD operations as tested."""

        def _mark(entity: str, operation: str):
            ux_tracker.test_crud(entity, operation)

        return _mark

    @pytest.fixture
    def mark_ui_view_tested(ux_tracker):
        """Fixture to mark UI views as tested."""

        def _mark(entity: str, view: str):
            ux_tracker.test_ui_view(entity, view)

        return _mark

    return (
        ux_tracker,
        mark_route_visited,
        mark_component_tested,
        mark_crud_tested,
        mark_ui_view_tested,
    )


# Example usage / self-test
if __name__ == "__main__":
    # Example UISpec
    example_spec = {
        "components": [
            {"name": "TaskList"},
            {"name": "TaskDetail"},
            {"name": "TaskCreate"},
            {"name": "TaskEdit"},
        ],
        "workspaces": [
            {
                "name": "dashboard",
                "routes": [
                    {"path": "/", "component": "TaskList"},
                    {"path": "/task/list", "component": "TaskList"},
                    {"path": "/task/:id", "component": "TaskDetail"},
                    {"path": "/task/create", "component": "TaskCreate"},
                    {"path": "/task/:id/edit", "component": "TaskEdit"},
                ],
            }
        ],
    }

    # Create tracker
    tracker = UXCoverageTracker(ui_spec=example_spec)

    # Simulate test execution
    tracker.visit_route("/")
    tracker.visit_route("/task/list")
    tracker.visit_route("/task/123e4567-e89b-12d3-a456-426614174000")

    tracker.test_component("TaskList", ["renders", "displays_data"])
    tracker.test_component("TaskDetail", ["renders"])

    tracker.test_crud("Task", "create")
    tracker.test_crud("Task", "read")
    tracker.test_crud("Task", "list")
    tracker.test_crud("Task", "delete")

    tracker.test_ui_view("Task", "list")
    tracker.test_ui_view("Task", "detail")

    tracker.test_interaction("click")
    tracker.test_interaction("type")

    # Generate report
    tracker.print_report()
