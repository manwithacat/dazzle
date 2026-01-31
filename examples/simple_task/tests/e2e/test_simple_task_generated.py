"""
Auto-generated E2E tests for simple_task.

Generated from E2ETestSpec by Dazzle playwright_codegen.

This module uses the console logging infrastructure from conftest.py:
- page_diagnostics: Captures all browser console output
- Errors are reported at the end of each test

Test Count: 33
- High Priority: 12
- Medium Priority: 15
- Low Priority: 6
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect

# =============================================================================
# Generated Tests
# =============================================================================


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.crud
@pytest.mark.create
@pytest.mark.user
def test_User_create_valid(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Create a valid User entity

    Entity: User
    Tags: crud, create, user
    """
    fixtures: dict[str, Any] = {
        "User_valid": {
            "email": "Test Email",
            "name": "Test Name",
            "role": "admin",
            "department": "Test Department",
            "avatar_url": "Test Avatar Url",
            "is_active": True,
            "created_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to User list
    page.goto(f"{base_url}/user")
    page.wait_for_load_state("networkidle")

    # Click create User button
    page.locator(
        '[data-dazzle-action="User.create"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Fill email field
    page.locator('[data-dazzle-field="email"], [name="email"]').fill(
        str(fixtures["User_valid"]["email"])
    )

    # Fill name field
    page.locator('[data-dazzle-field="name"], [name="name"]').fill(
        str(fixtures["User_valid"]["name"])
    )

    # Fill role field
    page.locator('[data-dazzle-field="role"], [name="role"]').select_option(
        str(fixtures["User_valid"]["role"])
    )

    # Fill department field
    page.locator('[data-dazzle-field="department"], [name="department"]').fill(
        str(fixtures["User_valid"]["department"])
    )

    # Click save button
    page.locator(
        '[data-dazzle-action="User.save"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert User was created
    # Verify User entity exists
    expect(page.locator("[data-dazzle-row]")).to_have_count(1, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.crud
@pytest.mark.create
@pytest.mark.task
def test_Task_create_valid(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Create a valid Task entity

    Entity: Task
    Tags: crud, create, task
    """
    fixtures: dict[str, Any] = {
        "Task_valid": {
            "title": "Test Title",
            "description": "Sample text content for description.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click create Task button
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Fill title field
    page.locator('[data-dazzle-field="title"], [name="title"]').fill(
        str(fixtures["Task_valid"]["title"])
    )

    # Fill description field
    page.locator('[data-dazzle-field="description"], [name="description"]').fill(
        str(fixtures["Task_valid"]["description"])
    )

    # Fill priority field
    page.locator('[data-dazzle-field="priority"], [name="priority"]').select_option(
        str(fixtures["Task_valid"]["priority"])
    )

    # Fill due_date field
    page.locator('[data-dazzle-field="due_date"], [name="due_date"]').fill(
        str(fixtures["Task_valid"]["due_date"])
    )

    # Click save button
    page.locator(
        '[data-dazzle-action="Task.save"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
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
def test_Task_update_valid(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Update a Task entity

    Entity: Task
    Tags: crud, update, task
    """
    fixtures: dict[str, Any] = {
        "Task_updated": {
            "title": "Test Title_updated",
            "description": "Sample text content for description_updated.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click on a Task row to view details
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Click edit Task button
    page.locator('[data-dazzle-action="Task.edit"], a:has-text("Edit")').click()
    page.wait_for_load_state("networkidle")

    # Update title field
    page.locator('[data-dazzle-field="title"], [name="title"]').fill(
        str(fixtures["Task_updated"]["title"])
    )

    # Click save button
    page.locator('[data-dazzle-action="Task.update"], [data-dazzle-action="update"]').click()
    page.wait_for_load_state("networkidle")

    # Assert Task was updated
    # Verify Task entity exists
    expect(page.locator("[data-dazzle-row]")).to_have_count(1, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_todo_to_in_progress(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'todo' to 'in_progress'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'todo'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'in_progress'
    page.locator(
        '[data-dazzle-action="Task.transition.in_progress"], [data-dazzle-action="transition.in_progress"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'in_progress' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_in_progress_to_review(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'in_progress' to 'review'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'in_progress'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'review'
    page.locator(
        '[data-dazzle-action="Task.transition.review"], [data-dazzle-action="transition.review"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'review' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_in_progress_to_todo(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'in_progress' to 'todo'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'in_progress'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'todo'
    page.locator(
        '[data-dazzle-action="Task.transition.todo"], [data-dazzle-action="transition.todo"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'todo' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_review_to_done(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'review' to 'done'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'review'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'done'
    page.locator(
        '[data-dazzle-action="Task.transition.done"], [data-dazzle-action="transition.done"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'done' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_review_to_in_progress(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'review' to 'in_progress'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'review'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'in_progress'
    page.locator(
        '[data-dazzle-action="Task.transition.in_progress"], [data-dazzle-action="transition.in_progress"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'in_progress' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.state_machine
@pytest.mark.transition
@pytest.mark.task
def test_Task_transition_done_to_todo(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Valid transition: Task from 'done' to 'todo'

    Entity: Task
    Tags: state_machine, transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'done'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Trigger transition to 'todo'
    page.locator(
        '[data-dazzle-action="Task.transition.todo"], [data-dazzle-action="transition.todo"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition to 'todo' succeeded

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.access_control
@pytest.mark.create
@pytest.mark.task
def test_Task_access_create_allowed(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Authenticated user can create Task

    Entity: Task
    Tags: access_control, create, task
    """
    # Execute flow steps
    # Navigate to Task list as authenticated user
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click create button
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert create form is accessible

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.access_control
@pytest.mark.update
@pytest.mark.task
def test_Task_access_update_allowed(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Authenticated user can update Task

    Entity: Task
    Tags: access_control, update, task
    """
    # Execute flow steps
    # Navigate to Task list as authenticated user
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Click update button
    page.locator('[data-dazzle-action="Task.edit"], a:has-text("Edit")').click()
    page.wait_for_load_state("networkidle")

    # Assert update is allowed

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.high_priority
@pytest.mark.reference
@pytest.mark.valid
@pytest.mark.task
def test_Task_ref_assigned_to_valid(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Create Task with valid assigned_to reference

    Entity: Task
    Tags: reference, valid, task
    """
    fixtures: dict[str, Any] = {
        "Task_valid": {
            "title": "Test Title",
            "description": "Sample text content for description.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        },
        "User_valid": {
            "email": "Test Email",
            "name": "Test Name",
            "role": "admin",
            "department": "Test Department",
            "avatar_url": "Test Avatar Url",
            "is_active": True,
            "created_at": "2025-01-15T10:30:00Z",
        },
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click create Task
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Select valid User reference
    page.locator('[data-dazzle-field="assigned_to"], [name="assigned_to"]').select_option(
        str(fixtures["User_valid"]["id"])
    )

    # Fill title
    page.locator('[data-dazzle-field="title"], [name="title"]').fill(
        str(fixtures["Task_valid"]["title"])
    )

    # Save entity
    page.locator(
        '[data-dazzle-action="Task.save"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert assigned_to reference is valid

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.crud
@pytest.mark.delete
@pytest.mark.user
def test_User_delete(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Delete a User entity

    Entity: User
    Tags: crud, delete, user
    """
    # Execute flow steps
    # Navigate to User list
    page.goto(f"{base_url}/user")
    page.wait_for_load_state("networkidle")

    # Click delete User button
    page.locator('[data-dazzle-action="User.delete"], button:has-text("Delete")').click()
    page.wait_for_load_state("networkidle")

    # Confirm deletion
    page.locator('[data-dazzle-action="confirm-delete"]').click()
    page.wait_for_load_state("networkidle")

    # Assert User was deleted
    # Verify User entity was deleted
    expect(page.locator("[data-dazzle-row]")).to_have_count(0, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.validation
@pytest.mark.required
@pytest.mark.user
def test_User_validation_required_email(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Validation error when email is missing

    Entity: User
    Tags: validation, required, user
    """
    # Execute flow steps
    # Navigate to User list
    page.goto(f"{base_url}/user")
    page.wait_for_load_state("networkidle")

    # Click create User button
    page.locator(
        '[data-dazzle-action="User.create"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Click save without filling required field
    page.locator(
        '[data-dazzle-action="User.create"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert validation error on email
    # Verify validation error appears
    expect(page.locator("[data-dazzle-error]")).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.validation
@pytest.mark.required
@pytest.mark.user
def test_User_validation_required_name(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Validation error when name is missing

    Entity: User
    Tags: validation, required, user
    """
    # Execute flow steps
    # Navigate to User list
    page.goto(f"{base_url}/user")
    page.wait_for_load_state("networkidle")

    # Click create User button
    page.locator(
        '[data-dazzle-action="User.create"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Click save without filling required field
    page.locator(
        '[data-dazzle-action="User.create"], [data-dazzle-action="User.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert validation error on name
    # Verify validation error appears
    expect(page.locator("[data-dazzle-error]")).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.crud
@pytest.mark.read
@pytest.mark.task
def test_Task_view_detail(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    View a Task entity detail

    Entity: Task
    Tags: crud, read, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click on a Task row to view details
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Assert Task is accessible
    # Verify Task entity exists
    expect(page.locator("[data-dazzle-row]")).to_have_count(1, timeout=5000)

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.crud
@pytest.mark.delete
@pytest.mark.task
def test_Task_delete(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Delete a Task entity

    Entity: Task
    Tags: crud, delete, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click delete Task button
    page.locator('[data-dazzle-action="Task.delete"], button:has-text("Delete")').click()
    page.wait_for_load_state("networkidle")

    # Confirm deletion
    page.locator('[data-dazzle-action="confirm-delete"]').click()
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
def test_Task_validation_required_title(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Validation error when title is missing

    Entity: Task
    Tags: validation, required, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click create Task button
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Click save without filling required field
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert validation error on title
    # Verify validation error appears
    expect(page.locator("[data-dazzle-error]")).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.validation
@pytest.mark.required
@pytest.mark.taskcomment
def test_TaskComment_validation_required_content(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Validation error when content is missing

    Entity: TaskComment
    Tags: validation, required, taskcomment
    """
    # Execute flow steps
    # Navigate to TaskComment list
    page.goto(f"{base_url}/taskcomment")
    page.wait_for_load_state("networkidle")

    # Click create TaskComment button
    page.locator(
        '[data-dazzle-action="TaskComment.create"], [data-dazzle-action="TaskComment.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Click save without filling required field
    page.locator(
        '[data-dazzle-action="TaskComment.create"], [data-dazzle-action="TaskComment.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert validation error on content
    # Verify validation error appears
    expect(page.locator("[data-dazzle-error]")).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.state_machine
@pytest.mark.invalid_transition
@pytest.mark.task
def test_Task_transition_invalid_todo_to_review(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Invalid transition: Task cannot go from 'todo' to 'review'

    Entity: Task
    Tags: state_machine, invalid_transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'todo'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Attempt invalid transition to 'review'
    page.locator(
        '[data-dazzle-action="Task.transition.review"], [data-dazzle-action="transition.review"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition was blocked, status remains 'todo'

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.state_machine
@pytest.mark.invalid_transition
@pytest.mark.task
def test_Task_transition_invalid_in_progress_to_done(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Invalid transition: Task cannot go from 'in_progress' to 'done'

    Entity: Task
    Tags: state_machine, invalid_transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'in_progress'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Attempt invalid transition to 'done'
    page.locator(
        '[data-dazzle-action="Task.transition.done"], [data-dazzle-action="transition.done"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition was blocked, status remains 'in_progress'

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.state_machine
@pytest.mark.invalid_transition
@pytest.mark.task
def test_Task_transition_invalid_review_to_todo(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Invalid transition: Task cannot go from 'review' to 'todo'

    Entity: Task
    Tags: state_machine, invalid_transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'review'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Attempt invalid transition to 'todo'
    page.locator(
        '[data-dazzle-action="Task.transition.todo"], [data-dazzle-action="transition.todo"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition was blocked, status remains 'review'

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.state_machine
@pytest.mark.invalid_transition
@pytest.mark.task
def test_Task_transition_invalid_done_to_review(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Invalid transition: Task cannot go from 'done' to 'review'

    Entity: Task
    Tags: state_machine, invalid_transition, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task in state 'done'
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Attempt invalid transition to 'review'
    page.locator(
        '[data-dazzle-action="Task.transition.review"], [data-dazzle-action="transition.review"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert transition was blocked, status remains 'done'

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.computed
@pytest.mark.task
def test_Task_computed_days_overdue(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Verify computed field 'days_overdue' on Task

    Entity: Task
    Tags: computed, task
    """
    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Select Task to view details
    page.locator('[data-dazzle-row="Task"], tbody tr').click()
    page.wait_for_load_state("networkidle")

    # Assert computed field 'days_overdue' is visible
    expect(
        page.locator('[data-dazzle-field="days_overdue"], [name="days_overdue"]')
    ).to_be_visible()

    # Assert computed field 'days_overdue' has expected value

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.access_control
@pytest.mark.denied
@pytest.mark.task
def test_Task_access_create_denied_anon(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Anonymous user cannot create Task

    Entity: Task
    Tags: access_control, denied, task
    """
    # Execute flow steps
    # Navigate to Task list as anonymous user
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Attempt create without authentication
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert create is denied for anonymous user

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.access_control
@pytest.mark.denied
@pytest.mark.task
def test_Task_access_update_denied_anon(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Anonymous user cannot update Task

    Entity: Task
    Tags: access_control, denied, task
    """
    # Execute flow steps
    # Navigate to Task list as anonymous user
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Attempt update without authentication
    page.locator('[data-dazzle-action="Task.edit"], a:has-text("Edit")').click()
    page.wait_for_load_state("networkidle")

    # Assert update is denied for anonymous user

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.reference
@pytest.mark.invalid
@pytest.mark.task
def test_Task_ref_assigned_to_invalid(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Create Task with invalid assigned_to reference fails

    Entity: Task
    Tags: reference, invalid, task
    """
    fixtures: dict[str, Any] = {
        "Task_valid": {
            "title": "Test Title",
            "description": "Sample text content for description.",
            "status": "todo",
            "priority": "low",
            "due_date": "2025-01-15",
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }

    # Execute flow steps
    # Navigate to Task list
    page.goto(f"{base_url}/task")
    page.wait_for_load_state("networkidle")

    # Click create Task
    page.locator(
        '[data-dazzle-action="Task.create"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Enter invalid User reference
    page.locator('[data-dazzle-field="assigned_to"], [name="assigned_to"]').select_option(
        "00000000-0000-0000-0000-000000000000"
    )

    # Fill title
    page.locator('[data-dazzle-field="title"], [name="title"]').fill(
        str(fixtures["Task_valid"]["title"])
    )

    # Attempt to save with invalid reference
    page.locator(
        '[data-dazzle-action="Task.save"], [data-dazzle-action="Task.create"], button[type="submit"]'
    ).click()
    page.wait_for_load_state("networkidle")

    # Assert assigned_to reference validation failed

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.task_list
def test_navigate_task_list(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Task List

    Entity: Task
    Tags: navigation, task_list
    """
    # Execute flow steps
    # Navigate to Task List
    page.goto(f"{base_url}/task")
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
def test_navigate_task_detail(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Task Detail

    Entity: Task
    Tags: navigation, task_detail
    """
    # Execute flow steps
    # Navigate to Task Detail
    page.goto(f"{base_url}/task/test-id")
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
def test_navigate_task_create(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Create Task

    Entity: Task
    Tags: navigation, task_create
    """
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
def test_navigate_task_edit(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Edit Task

    Entity: Task
    Tags: navigation, task_edit
    """
    # Execute flow steps
    # Navigate to Edit Task
    page.goto(f"{base_url}/task/test-id/edit")
    page.wait_for_load_state("networkidle")

    # Assert task_edit view is visible
    expect(page.locator('[data-dazzle-view="task_edit"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.user_list
def test_navigate_user_list(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Team Members

    Entity: User
    Tags: navigation, user_list
    """
    # Execute flow steps
    # Navigate to Team Members
    page.goto(f"{base_url}/user")
    page.wait_for_load_state("networkidle")

    # Assert user_list view is visible
    expect(page.locator('[data-dazzle-view="user_list"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")


@pytest.mark.e2e
@pytest.mark.navigation
@pytest.mark.user_create
def test_navigate_user_create(
    page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str
) -> None:
    """
    Navigate to Add Team Member

    Entity: User
    Tags: navigation, user_create
    """
    # Execute flow steps
    # Navigate to Add Team Member
    page.goto(f"{base_url}/user/create")
    page.wait_for_load_state("networkidle")

    # Assert user_create view is visible
    expect(page.locator('[data-dazzle-view="user_create"]')).to_be_visible()

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {errors}")
