"""
Auto-generated E2E tests for simple_task.

Generated from E2ETestSpec by Dazzle playwright_codegen.

This module uses the console logging infrastructure from conftest.py:
- page_diagnostics: Captures all browser console output
- Errors are reported at the end of each test

Test Count: 12
- High Priority: 4
- Medium Priority: 4
- Low Priority: 4
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect

# =============================================================================
# Test Configuration
# =============================================================================

# Base URL from environment or default
BASE_URL = os.environ.get("DNR_UI_URL", "http://localhost:3000")


@pytest.fixture
def base_url() -> str:
    """Get the base URL for the application under test."""
    return BASE_URL


# =============================================================================
# Generated Tests
# =============================================================================


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.auth
@pytest.mark.login
def test_auth_login(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Login with valid credentials
    Tags: auth, login
    """
    test_name = "test_auth_login"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to login page
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("networkidle")

    # Fill username field
    page.locator('[data-dazzle-field="username"]').fill("testuser")

    # Fill password field
    page.locator('[data-dazzle-field="password"]').fill("testpass123")

    # Click login button
    page.locator('[data-dazzle-action="login"]').click()
    page.wait_for_load_state("networkidle")

    # Assert user menu is visible after login
    expect(page.locator('[data-testid="user_menu"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.auth
@pytest.mark.logout
def test_auth_logout(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Logout after being logged in
    Tags: auth, logout
    """
    test_name = "test_auth_logout"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Open user menu
    page.locator('[data-dazzle-action="user_menu"]').click()
    page.wait_for_load_state("networkidle")

    # Click logout
    page.locator('[data-dazzle-action="logout"]').click()
    page.wait_for_load_state("networkidle")

    # Assert redirected to login page
    expect(page.locator('[data-dazzle-view="login"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.crud
@pytest.mark.create
@pytest.mark.task
def test_Task_create_valid(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Create a valid Task entity

    Entity: Task
    Tags: crud, create, task
    """
    test_name = "test_Task_create_valid"

    # Fixture data
    fixtures = {
        "Task_valid": {
            "title": "Test Title",
            "description": "Sample text content for description.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "assigned_to": "Test Assigned To",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Click create Task button
    page.locator('[data-dazzle-action="create"]').click()
    page.wait_for_load_state("networkidle")

    # Fill title field
    page.locator('[data-dazzle-field="title"]').fill(str(fixtures["Task_valid"]["title"]))

    # Fill description field
    page.locator('[data-dazzle-field="description"]').fill(
        str(fixtures["Task_valid"]["description"])
    )

    # Fill status field
    page.locator('[data-dazzle-field="status"]').fill(str(fixtures["Task_valid"]["status"]))

    # Fill priority field
    page.locator('[data-dazzle-field="priority"]').fill(str(fixtures["Task_valid"]["priority"]))

    # Fill due_date field
    page.locator('[data-dazzle-field="due_date"]').fill(str(fixtures["Task_valid"]["due_date"]))

    # Fill assigned_to field
    page.locator('[data-dazzle-field="assigned_to"]').fill(
        str(fixtures["Task_valid"]["assigned_to"])
    )

    # Click save button
    page.locator('[data-dazzle-action="save"]').click()
    page.wait_for_load_state("networkidle")

    # Assert Task was created
    # Verify Task entity exists
    expect(page.locator("[data-dazzle-row]")).to_have_count(1, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.crud
@pytest.mark.update
@pytest.mark.task
def test_Task_update_valid(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Update a Task entity

    Entity: Task
    Tags: crud, update, task
    """
    test_name = "test_Task_update_valid"

    # Fixture data
    fixtures = {
        "Task_updated": {
            "title": "Test Title_updated",
            "description": "Sample text content for description_updated.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "assigned_to": "Test Assigned To_updated",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Click edit Task button
    page.locator('[data-dazzle-action="edit"]').click()
    page.wait_for_load_state("networkidle")

    # Update title field
    page.locator('[data-dazzle-field="title"]').fill(str(fixtures["Task_updated"]["title"]))

    # Click save button
    page.locator('[data-dazzle-action="save"]').click()
    page.wait_for_load_state("networkidle")

    # Assert Task was updated
    # Verify Task entity exists
    expect(page.locator("[data-dazzle-row]")).to_have_count(1, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.auth
@pytest.mark.protection
def test_auth_protected_route(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Unauthenticated user redirected to login
    Tags: auth, protection
    """
    test_name = "test_auth_protected_route"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to protected task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Assert redirected to login

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.crud
@pytest.mark.read
@pytest.mark.task
def test_Task_view_detail(page, page_diagnostics, track_route, track_crud, base_url):
    """
    View a Task entity detail

    Entity: Task
    Tags: crud, read, task
    """
    test_name = "test_Task_view_detail"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Click on a Task row
    page.locator('[data-dazzle-row="Task"]').click()
    page.wait_for_load_state("networkidle")

    # Assert Task detail view is visible
    expect(page.locator('[data-dazzle-view="task_detail"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.crud
@pytest.mark.delete
@pytest.mark.task
def test_Task_delete(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Delete a Task entity

    Entity: Task
    Tags: crud, delete, task
    """
    test_name = "test_Task_delete"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Click delete Task button
    page.locator('[data-dazzle-action="delete"]').click()
    page.wait_for_load_state("networkidle")

    # Confirm deletion
    page.locator('[data-dazzle-action="confirm"]').click()
    page.wait_for_load_state("networkidle")

    # Assert Task was deleted
    # Verify Task entity was deleted
    expect(page.locator("[data-dazzle-row]")).to_have_count(0, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.validation
@pytest.mark.required
@pytest.mark.task
def test_Task_validation_required_title(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Validation error when title is missing

    Entity: Task
    Tags: validation, required, task
    """
    test_name = "test_Task_validation_required_title"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Click create Task button
    page.locator('[data-dazzle-action="create"]').click()
    page.wait_for_load_state("networkidle")

    # Click save without filling required field
    page.locator('[data-dazzle-action="save"]').click()
    page.wait_for_load_state("networkidle")

    # Assert validation error on title
    # Verify validation error appears
    expect(page.locator("[data-dazzle-error]")).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.task_list
def test_navigate_task_list(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Navigate to Task List

    Entity: Task
    Tags: navigation, task_list
    """
    test_name = "test_navigate_task_list"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Task List
    page.goto(f"{base_url}/task/list")
    page.wait_for_load_state("networkidle")

    # Assert task_list view is visible
    expect(page.locator('[data-dazzle-view="task_list"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.task_detail
def test_navigate_task_detail(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Navigate to Task Detail

    Entity: Task
    Tags: navigation, task_detail
    """
    test_name = "test_navigate_task_detail"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Task Detail
    page.goto(f"{base_url}/task/detail")
    page.wait_for_load_state("networkidle")

    # Assert task_detail view is visible
    expect(page.locator('[data-dazzle-view="task_detail"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.task_create
def test_navigate_task_create(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Navigate to Create Task

    Entity: Task
    Tags: navigation, task_create
    """
    test_name = "test_navigate_task_create"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Create Task
    page.goto(f"{base_url}/task/create")
    page.wait_for_load_state("networkidle")

    # Assert task_create view is visible
    expect(page.locator('[data-dazzle-view="task_create"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.task_edit
def test_navigate_task_edit(page, page_diagnostics, track_route, track_crud, base_url):
    """
    Navigate to Edit Task

    Entity: Task
    Tags: navigation, task_edit
    """
    test_name = "test_navigate_task_edit"

    # Fixture data
    fixtures = {}

    # Execute flow steps
    # Navigate to Edit Task
    page.goto(f"{base_url}/task/edit")
    page.wait_for_load_state("networkidle")

    # Assert task_edit view is visible
    expect(page.locator('[data-dazzle-view="task_edit"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")
