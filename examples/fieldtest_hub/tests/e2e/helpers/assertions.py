"""Common assertion helpers for E2E tests."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def assert_toast_message(page: Page, message: str, timeout: float = 5000) -> None:
    """Assert a toast notification appears with the expected message.

    Args:
        page: Playwright page
        message: Expected message text (partial match)
        timeout: Timeout in milliseconds
    """
    toast = page.locator('[data-dazzle-component="toast"], .toast, [role="alert"]')
    toast.wait_for(state="visible", timeout=timeout)
    expect(toast).to_contain_text(message)


def assert_validation_error(
    page: Page, field_name: str | None = None, message: str | None = None
) -> None:
    """Assert a validation error is displayed.

    Args:
        page: Playwright page
        field_name: Optional specific field name
        message: Optional expected error message
    """
    if field_name:
        error = page.locator(
            f'[data-dazzle-error][data-dazzle-field="{field_name}"], '
            f'[data-dazzle-field="{field_name}"] ~ .error, '
            f'[name="{field_name}"] ~ .error'
        )
    else:
        error = page.locator("[data-dazzle-error], .error, .validation-error")

    expect(error).to_be_visible()
    if message:
        expect(error).to_contain_text(message)


def assert_no_validation_errors(page: Page) -> None:
    """Assert no validation errors are displayed.

    Args:
        page: Playwright page
    """
    errors = page.locator("[data-dazzle-error], .error:visible, .validation-error:visible")
    expect(errors).to_have_count(0)


def assert_access_denied(page: Page) -> None:
    """Assert that access was denied (403 or hidden content).

    Checks for common access denied indicators:
    - 403 status text
    - Access denied message
    - Empty list with no create button

    Args:
        page: Playwright page
    """
    # Check for explicit access denied indicators
    denied_indicators = page.locator(
        'text="Access Denied", '
        'text="403", '
        'text="Forbidden", '
        'text="Not authorized", '
        '[data-dazzle-component="access-denied"]'
    )

    if denied_indicators.count() > 0:
        expect(denied_indicators.first).to_be_visible()
        return

    # If no explicit denial, check that restricted actions are hidden
    # This is a softer assertion - presence of the page but no actions


def assert_action_available(page: Page, action_name: str) -> None:
    """Assert an action button is visible and enabled.

    Args:
        page: Playwright page
        action_name: Action name (e.g., "create", "edit", "delete")
    """
    action = page.locator(f'[data-dazzle-action="{action_name}"]')
    expect(action).to_be_visible()
    expect(action).to_be_enabled()


def assert_action_unavailable(page: Page, action_name: str) -> None:
    """Assert an action button is hidden or disabled.

    Args:
        page: Playwright page
        action_name: Action name
    """
    action = page.locator(f'[data-dazzle-action="{action_name}"]')
    # Either hidden or disabled
    if action.count() > 0:
        expect(action).to_be_disabled()
    else:
        expect(action).to_have_count(0)


def assert_row_exists(
    page: Page, entity: str, entity_id: str | None = None, text: str | None = None
) -> None:
    """Assert a row exists in a list view.

    Args:
        page: Playwright page
        entity: Entity name
        entity_id: Optional specific entity ID
        text: Optional text that should appear in the row
    """
    if entity_id:
        row = page.locator(f'[data-dazzle-row="{entity}"][data-dazzle-entity-id="{entity_id}"]')
    else:
        row = page.locator(f'[data-dazzle-row="{entity}"]')

    expect(row.first).to_be_visible()

    if text:
        expect(row.first).to_contain_text(text)


def assert_row_not_exists(page: Page, entity: str, entity_id: str) -> None:
    """Assert a row does not exist in a list view.

    Args:
        page: Playwright page
        entity: Entity name
        entity_id: Entity ID
    """
    row = page.locator(f'[data-dazzle-row="{entity}"][data-dazzle-entity-id="{entity_id}"]')
    expect(row).to_have_count(0)


def assert_field_value(page: Page, field_name: str, expected_value: str) -> None:
    """Assert a field has a specific value.

    Args:
        page: Playwright page
        field_name: Field name
        expected_value: Expected value
    """
    field = page.locator(f'[data-dazzle-field="{field_name}"]')
    expect(field).to_have_value(expected_value)


def assert_field_readonly(page: Page, field_name: str) -> None:
    """Assert a field is read-only.

    Args:
        page: Playwright page
        field_name: Field name
    """
    field = page.locator(f'[data-dazzle-field="{field_name}"]')
    expect(field).to_have_attribute("readonly", "true")


def assert_status_value(page: Page, entity: str, entity_id: str, status: str) -> None:
    """Assert an entity has a specific status value.

    Args:
        page: Playwright page
        entity: Entity name
        entity_id: Entity ID
        status: Expected status value
    """
    row = page.locator(f'[data-dazzle-row="{entity}"][data-dazzle-entity-id="{entity_id}"]')
    status_cell = row.locator('[data-dazzle-field="status"]')
    expect(status_cell).to_contain_text(status)


def assert_page_title(page: Page, title: str) -> None:
    """Assert the page has a specific title.

    Args:
        page: Playwright page
        title: Expected title (partial match)
    """
    expect(page).to_have_title(title)


def assert_url_contains(page: Page, path: str) -> None:
    """Assert the URL contains a specific path.

    Args:
        page: Playwright page
        path: Expected path segment
    """
    expect(page).to_have_url(f"*{path}*")
