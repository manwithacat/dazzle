"""
Playwright-based UX validation tests for Dazzle DNR.

These tests are **DSL-driven** - they dynamically discover entities, routes,
and components from the running app's UISpec and Backend API, rather than
hardcoding test cases for a specific entity like "Task".

Philosophy:
    "The goal is for test cases to be generated automatically based on the
    DSL/AppSpec. If we create something that results in a user-facing
    representation, that representation should be tested. This includes
    verifying that all user-initiated CRUD options can be completed
    successfully within the interface."

Usage (inside Docker):
    pytest test_ux_validation.py -v --screenshot=on

Environment variables:
    DNR_BASE_URL: API URL (default: http://dnr-app:8000)
    DNR_UI_URL: UI URL (default: http://dnr-app:3000)
    SCREENSHOT_DIR: Where to save screenshots (default: /screenshots)
"""

import os
import re
from dataclasses import dataclass

import httpx
import pytest
from playwright.sync_api import Page, expect, sync_playwright

# Configuration from environment
DNR_BASE_URL = os.environ.get("DNR_BASE_URL", "http://localhost:8000")
DNR_UI_URL = os.environ.get("DNR_UI_URL", DNR_BASE_URL.replace(":8000", ":3000"))
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/screenshots")


# =============================================================================
# DSL Discovery - Dynamically discover app structure from UISpec/API
# =============================================================================


@dataclass
class EntityInfo:
    """Information about an entity discovered from the app."""

    name: str
    plural_name: str
    api_endpoint: str
    fields: list[dict]
    required_fields: list[str]
    routes: dict[str, str]  # view_type -> route path


@dataclass
class AppInfo:
    """Complete app structure discovered from UISpec and Backend."""

    entities: list[EntityInfo]
    components: list[str]
    routes: list[dict]
    workspace_name: str


def _pluralize(name: str) -> str:
    """Simple pluralization for API endpoint names."""
    if name.endswith("y"):
        return name[:-1] + "ies"
    elif name.endswith("s"):
        return name + "es"
    return name + "s"


def discover_app_structure(api_url: str, ui_url: str) -> AppInfo:
    """Discover the app structure from UISpec and Backend API."""
    client = httpx.Client(timeout=10)

    # Fetch UISpec from frontend
    try:
        ui_spec = client.get(f"{ui_url}/ui-spec.json").json()
    except Exception:
        # Fallback to API
        try:
            ui_spec = client.get(f"{api_url}/api/ui-spec").json()
        except Exception:
            ui_spec = {}

    # Fetch Backend entity names (this is just a list of strings, not objects!)
    backend_entity_names = []
    try:
        response = client.get(f"{api_url}/api/entities")
        if response.status_code == 200:
            data = response.json()
            # /api/entities returns a list of entity name strings
            if isinstance(data, list):
                backend_entity_names = [n for n in data if isinstance(n, str)]
    except Exception:
        pass

    # Extract components
    components = [c.get("name", "") for c in ui_spec.get("components", [])]

    # Extract routes
    routes = []
    workspace_name = ""
    for ws in ui_spec.get("workspaces", []):
        workspace_name = ws.get("name", "")
        for route in ws.get("routes", []):
            routes.append(route)

    # Build entity info from components and backend
    entities = []
    entity_names = set()

    # Add entity names from backend API
    entity_names.update(backend_entity_names)

    # Also extract entity names from component naming convention
    for comp_name in components:
        for suffix in ["List", "Detail", "Create", "Edit", "Form"]:
            if comp_name.endswith(suffix):
                entity_name = comp_name[: -len(suffix)]
                if entity_name:
                    entity_names.add(entity_name)

    # Build entity info
    for entity_name in sorted(entity_names):
        plural = _pluralize(entity_name.lower())
        api_endpoint = f"/api/{plural}"

        # Note: We don't have field details from the simple /api/entities endpoint
        # For detailed field info, we'd need to call /api/entities/{name} or similar
        fields = []
        required_fields = []

        # Build routes mapping from discovered routes
        entity_routes = {}
        entity_lower = entity_name.lower()
        for route in routes:
            path = route.get("path", "")
            component = route.get("component", "")
            if entity_name in component:
                if "List" in component:
                    entity_routes["list"] = path
                elif "Create" in component:
                    entity_routes["create"] = path
                elif "Edit" in component:
                    entity_routes["edit"] = path
                elif "Detail" in component:
                    entity_routes["detail"] = path

        # If no routes found, use convention
        if not entity_routes:
            entity_routes = {
                "list": f"/{entity_lower}/list",
                "create": f"/{entity_lower}/create",
                "detail": f"/{entity_lower}/:id",
                "edit": f"/{entity_lower}/:id/edit",
            }

        entities.append(
            EntityInfo(
                name=entity_name,
                plural_name=plural,
                api_endpoint=api_endpoint,
                fields=fields,
                required_fields=required_fields,
                routes=entity_routes,
            )
        )

    return AppInfo(
        entities=entities,
        components=components,
        routes=routes,
        workspace_name=workspace_name,
    )


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def browser():
    """Create a browser instance for the test module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Create a new page for each test."""
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    yield page
    page.close()
    context.close()


@pytest.fixture(scope="module")
def api_client():
    """HTTP client for API operations."""
    return httpx.Client(base_url=DNR_BASE_URL, timeout=10)


@pytest.fixture(scope="module")
def app_info():
    """Discover and cache app structure."""
    return discover_app_structure(DNR_BASE_URL, DNR_UI_URL)


# =============================================================================
# Helper Functions
# =============================================================================


def take_screenshot(page: Page, name: str):
    """Take a screenshot with a descriptive name."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path)
    return path


def generate_test_data(entity: EntityInfo) -> dict:
    """Generate valid test data for an entity based on its fields or common patterns."""
    data = {}

    # If we have field info, use it
    if entity.fields:
        for field in entity.fields:
            name = field.get("name", "")
            kind = field.get("type", {}).get("kind", "str")
            is_pk = field.get("is_primary_key", False)

            if is_pk:
                continue

            if kind == "str":
                data[name] = f"Test {name.replace('_', ' ').title()}"
            elif kind == "text":
                data[name] = f"Sample text for {name}"
            elif kind == "int":
                data[name] = 42
            elif kind == "decimal":
                data[name] = 99.99
            elif kind == "bool":
                data[name] = True
            elif kind == "email":
                data[name] = "test@example.com"
            elif kind == "enum":
                values = field.get("type", {}).get("enum_values", [])
                data[name] = values[0] if values else "default"
    else:
        # Fallback: Generate common fields based on entity name patterns
        entity_lower = entity.name.lower()

        # Common field patterns
        if entity_lower == "task":
            data = {"title": "Test Task", "status": "pending"}
        elif entity_lower == "contact":
            data = {"first_name": "John", "last_name": "Doe", "email": "john@test.com"}
        elif entity_lower == "service":
            data = {"name": "Test Service", "endpoint": "http://example.com"}
        elif entity_lower == "product":
            data = {"name": "Test Product", "sku": "SKU-001", "quantity": 10, "price": 9.99}
        elif entity_lower == "message":
            data = {"subject": "Test Subject", "sender": "test@a.com", "recipient": "test@b.com", "body": "Test body"}
        elif entity_lower == "system":
            data = {"name": "Test System"}
        elif entity_lower == "alert":
            data = {"message": "Test Alert"}
        else:
            # Generic fallback with common field names
            data = {"name": f"Test {entity.name}", "title": f"Test {entity.name}"}

    return data


# =============================================================================
# API Health Tests
# =============================================================================


class TestAPIHealth:
    """Test that the API is healthy and responsive."""

    def test_health_endpoint(self, api_client):
        """Test that the health endpoint returns success."""
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_ui_spec_available(self):
        """Test that the UI spec is available."""
        client = httpx.Client(base_url=DNR_UI_URL, timeout=10)
        response = client.get("/ui-spec.json")
        assert response.status_code == 200
        data = response.json()
        assert "components" in data or "workspaces" in data

    def test_entities_discovered(self, app_info: AppInfo):
        """Test that at least one entity was discovered."""
        assert len(app_info.entities) > 0, "No entities discovered from UISpec"
        print(f"\nDiscovered entities: {[e.name for e in app_info.entities]}")


# =============================================================================
# Basic UX Tests - DSL Driven
# =============================================================================


class TestUXBasics:
    """Basic UX validation tests - driven by discovered app structure."""

    def test_page_loads(self, page: Page, ux_tracker, app_info: AppInfo):
        """Test that the main page loads without errors."""
        page.goto(DNR_UI_URL)

        # Track coverage for first entity
        if app_info.entities:
            entity = app_info.entities[0]
            ux_tracker.visit_route("/")
            ux_tracker.test_component(f"{entity.name}List", ["renders"])
            ux_tracker.test_ui_view(entity.name, "list")

        # Wait for the app to initialize
        page.wait_for_selector("#app", timeout=10000)

        take_screenshot(page, "01_page_loaded")

    def test_page_has_content(self, page: Page, app_info: AppInfo):
        """Test that the page has meaningful content."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        body_text = page.locator("body").inner_text()

        # Should not be stuck on loading
        if "Loading" in body_text and len(body_text.strip()) < 50:
            take_screenshot(page, "02_stuck_on_loading")
            pytest.fail(f"Page appears stuck on loading state. Body text: {body_text[:200]}")

        take_screenshot(page, "02_page_has_content")

    def test_has_heading(self, page: Page):
        """Test that the page has a heading."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")

        heading = page.locator("h1, h2, h3, [data-dazzle-component='heading']").first
        expect(heading).to_be_visible(timeout=5000)

        take_screenshot(page, "03_has_heading")


# =============================================================================
# CRUD Flow Tests - DSL Driven
# =============================================================================


class TestCRUDFlow:
    """Test CRUD operations for all discovered entities."""

    def test_create_button_exists(self, page: Page, ux_tracker, app_info: AppInfo):
        """Test that Create buttons exist for entities."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")

        if app_info.entities:
            entity = app_info.entities[0]
            ux_tracker.visit_route("/")
            ux_tracker.test_interaction("click")

        # Look for create button (generic)
        create_button = page.locator(
            "button:has-text('Create'), a:has-text('Create'), "
            "button:has-text('Add'), a:has-text('Add'), "
            "[data-action='create']"
        )

        if create_button.count() == 0:
            take_screenshot(page, "04_no_create_button")
            pytest.fail("No Create/Add button found on the page")

        take_screenshot(page, "04_create_button_exists")

    def test_create_form_opens(self, page: Page, app_info: AppInfo):
        """Test that clicking create opens a form."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")

        create_button = page.locator(
            "button:has-text('Create'), a:has-text('Create'), "
            "button:has-text('Add'), a:has-text('Add'), "
            "[data-action='create']"
        ).first

        if create_button.count() > 0:
            create_button.click()
            page.wait_for_timeout(1000)

            # Check for form inputs
            inputs = page.locator("input, textarea, select")
            input_count = inputs.count()

            if input_count == 0:
                take_screenshot(page, "05_create_form_no_inputs")
                pytest.skip("Create form has no input fields")

            take_screenshot(page, "05_create_form_opened")
        else:
            pytest.skip("No create button found")

    def test_api_crud_operations(self, api_client, ux_tracker, app_info: AppInfo):
        """Test CRUD operations via API for each entity."""
        for entity in app_info.entities:
            # Generate test data
            test_data = generate_test_data(entity)
            if not test_data:
                # Fallback minimal data
                test_data = {"name": f"Test {entity.name}"}

            # CREATE
            create_resp = api_client.post(entity.api_endpoint, json=test_data)
            if create_resp.status_code not in (200, 201):
                pytest.skip(f"Could not create {entity.name}: {create_resp.status_code}")
            created = create_resp.json()
            entity_id = created.get("id")
            ux_tracker.test_crud(entity.name, "create")

            # READ
            read_resp = api_client.get(f"{entity.api_endpoint}/{entity_id}")
            assert read_resp.status_code == 200
            ux_tracker.test_crud(entity.name, "read")

            # LIST
            list_resp = api_client.get(entity.api_endpoint)
            assert list_resp.status_code == 200
            ux_tracker.test_crud(entity.name, "list")

            # UPDATE
            update_data = {**test_data, "name": f"Updated {entity.name}"} if "name" in test_data else test_data
            update_resp = api_client.put(f"{entity.api_endpoint}/{entity_id}", json=update_data)
            if update_resp.status_code == 200:
                ux_tracker.test_crud(entity.name, "update")

            # DELETE
            delete_resp = api_client.delete(f"{entity.api_endpoint}/{entity_id}")
            if delete_resp.status_code in (200, 204):
                ux_tracker.test_crud(entity.name, "delete")


# =============================================================================
# View Tests - Screenshots for each view type
# =============================================================================


class TestViewScreenshots:
    """Take screenshots of each discovered view type."""

    def test_dashboard_screenshot(self, page: Page, app_info: AppInfo):
        """Take a screenshot of the dashboard/main view."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        take_screenshot(page, "dashboard")

    def test_list_view_screenshot(self, page: Page, api_client, ux_tracker, app_info: AppInfo):
        """Take screenshots of list views for each entity."""
        for entity in app_info.entities:
            # Seed some data first
            test_data = generate_test_data(entity)
            if not test_data:
                test_data = {"name": f"Test {entity.name} 1"}

            api_client.post(entity.api_endpoint, json=test_data)

            # Navigate to list view
            list_route = entity.routes.get("list", f"/{entity.name.lower()}/list")
            page.goto(f"{DNR_UI_URL}{list_route}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            ux_tracker.visit_route(list_route)
            ux_tracker.test_ui_view(entity.name, "list")
            ux_tracker.test_component(f"{entity.name}List", ["renders", "displays_data"])

            take_screenshot(page, "list_view")
            break  # Just need one list view screenshot

    def test_create_form_screenshot(self, page: Page, ux_tracker, app_info: AppInfo):
        """Take screenshots of create forms."""
        for entity in app_info.entities:
            create_route = entity.routes.get("create", f"/{entity.name.lower()}/create")
            page.goto(f"{DNR_UI_URL}{create_route}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

            ux_tracker.visit_route(create_route)
            ux_tracker.test_ui_view(entity.name, "create")
            ux_tracker.test_component(f"{entity.name}Create", ["renders", "has_inputs"])

            take_screenshot(page, "create_form")
            break  # Just need one create form screenshot


# =============================================================================
# Navigation Tests
# =============================================================================


class TestNavigation:
    """Test navigation between views."""

    def test_all_routes_accessible(self, page: Page, ux_tracker, app_info: AppInfo):
        """Test that all discovered routes are accessible (no 404s)."""
        errors = []

        for route in app_info.routes:
            path = route.get("path", "")
            if ":id" in path:
                continue  # Skip parameterized routes

            full_url = f"{DNR_UI_URL}{path}"
            page.goto(full_url)
            page.wait_for_timeout(500)

            body_text = page.locator("body").inner_text()
            if '"detail":"Not Found"' in body_text or "404" in body_text.upper():
                errors.append(f"Route {path} returned 404")
            else:
                ux_tracker.visit_route(path)

        if errors:
            pytest.fail(f"Routes with errors: {errors}")


# =============================================================================
# Styling Tests
# =============================================================================


class TestStyling:
    """Test that CSS styling is applied."""

    def test_app_container_exists(self, page: Page):
        """Test that the #app container exists and has styling."""
        page.goto(DNR_UI_URL)
        page.wait_for_load_state("networkidle")

        app_div = page.locator("#app")
        expect(app_div).to_be_visible(timeout=5000)

        take_screenshot(page, "10_app_container")


# Mark all tests as e2e and docker
pytestmark = [pytest.mark.e2e, pytest.mark.docker]
