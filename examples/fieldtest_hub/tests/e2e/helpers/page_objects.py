"""Page object helpers using semantic selectors.

Provides a clean interface for interacting with the FieldTest Hub UI
using data-dazzle-* semantic attributes.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class FieldTestHubPage:
    """Page object for FieldTest Hub with semantic selector helpers."""

    def __init__(self, page: Page, base_url: str):
        """Initialize the page object.

        Args:
            page: Playwright page instance
            base_url: Base URL for the UI (e.g., http://localhost:3000)
        """
        self.page = page
        self.base_url = base_url.rstrip("/")

    # =========================================================================
    # Navigation
    # =========================================================================

    def goto(self, path: str = "/") -> None:
        """Navigate to a path.

        Args:
            path: URL path (e.g., "/device/list")
        """
        self.page.goto(f"{self.base_url}{path}")
        self.page.wait_for_load_state("networkidle")

    def navigate_to_view(self, view_name: str) -> None:
        """Navigate to a named view.

        Args:
            view_name: View name (e.g., "device_list", "issue_report_create")
        """
        # Convert view name to path (e.g., device_list -> /device/list)
        parts = view_name.rsplit("_", 1)
        if len(parts) == 2:
            entity, mode = parts
            path = f"/{entity}/{mode}"
        else:
            path = f"/{view_name}"
        self.goto(path)

    def navigate_to_entity_list(self, entity: str) -> None:
        """Navigate to an entity's list view.

        Args:
            entity: Entity name (e.g., "Device", "IssueReport")
        """
        # Convert CamelCase to snake_case path
        path = self._entity_to_path(entity)
        self.goto(f"/{path}/list")

    def navigate_to_entity_create(self, entity: str) -> None:
        """Navigate to an entity's create form.

        Args:
            entity: Entity name
        """
        path = self._entity_to_path(entity)
        self.goto(f"/{path}/create")

    def navigate_to_entity_detail(self, entity: str, entity_id: str) -> None:
        """Navigate to an entity's detail view.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        path = self._entity_to_path(entity)
        self.goto(f"/{path}/{entity_id}")

    def navigate_to_entity_edit(self, entity: str, entity_id: str) -> None:
        """Navigate to an entity's edit form.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        path = self._entity_to_path(entity)
        self.goto(f"/{path}/{entity_id}/edit")

    def _entity_to_path(self, entity: str) -> str:
        """Convert entity name to URL path segment.

        Args:
            entity: Entity name (e.g., "IssueReport")

        Returns:
            Path segment (e.g., "issue_report")
        """
        # Convert CamelCase to snake_case
        import re

        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", entity)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    # =========================================================================
    # Semantic Selectors
    # =========================================================================

    def view(self, view_name: str) -> Locator:
        """Get a view container by name.

        Note: Uses form[data-dazzle-view] to target forms specifically,
        falling back to the first element with the view attribute.

        Args:
            view_name: View name

        Returns:
            Locator for the view
        """
        # Target forms specifically (most common case for create/edit views)
        # or use :first-child pattern to get the container, not children
        return self.page.locator(
            f'form[data-dazzle-view="{view_name}"], '
            f'div[data-dazzle-view="{view_name}"]'
        ).first

    def field(self, field_name: str, entity: str | None = None) -> Locator:
        """Get a form field by name.

        The DNR emits field names in format "Entity.field" (e.g., "Device.name").
        This method supports both:
        - Simple names: "name" -> matches "[data-dazzle-field$='.name']" or exact
        - Full names: "Device.name" -> exact match

        Args:
            field_name: Field name (e.g., "name", "Device.name")
            entity: Optional entity name to construct full field path

        Returns:
            Locator for the field input
        """
        if entity:
            # Build full field path
            full_field = f"{entity}.{field_name}"
            return self.page.locator(f'[data-dazzle-field="{full_field}"]')
        elif "." in field_name:
            # Full field path provided
            return self.page.locator(f'[data-dazzle-field="{field_name}"]')
        else:
            # Simple field name - match suffix (e.g., ".name") or exact match
            # This handles both "Entity.name" and standalone "name"
            return self.page.locator(
                f'[data-dazzle-field$=".{field_name}"], [data-dazzle-field="{field_name}"]'
            )

    def action(self, action_name: str, entity: str | None = None) -> Locator:
        """Get an action button by name.

        The DNR emits action names in format "Entity.action" (e.g., "Device.create").
        This method supports both:
        - Simple names: "create" -> matches "[data-dazzle-action$='.create']" or exact
        - Full names: "Device.create" -> exact match

        Args:
            action_name: Action name (e.g., "create", "Device.create")
            entity: Optional entity name to construct full action

        Returns:
            Locator for the action button
        """
        if entity:
            # Build full action name
            full_action = f"{entity}.{action_name}"
            return self.page.locator(f'[data-dazzle-action="{full_action}"]')
        elif "." in action_name:
            # Full action name provided
            return self.page.locator(f'[data-dazzle-action="{action_name}"]')
        else:
            # Simple action name - match suffix (e.g., ".create") or exact match
            # This handles both "Entity.create" and standalone "create"
            return self.page.locator(
                f'[data-dazzle-action$=".{action_name}"], [data-dazzle-action="{action_name}"]'
            )

    def row(self, entity: str, entity_id: str | None = None) -> Locator:
        """Get a table row.

        Args:
            entity: Entity name
            entity_id: Optional specific row ID

        Returns:
            Locator for the row(s)
        """
        if entity_id:
            return self.page.locator(
                f'[data-dazzle-row="{entity}"][data-dazzle-entity-id="{entity_id}"]'
            )
        return self.page.locator(f'[data-dazzle-row="{entity}"]')

    def component(self, component_name: str) -> Locator:
        """Get a component by name.

        Args:
            component_name: Component name

        Returns:
            Locator for the component
        """
        return self.page.locator(f'[data-dazzle-component="{component_name}"]')

    def error_message(self, field_name: str | None = None) -> Locator:
        """Get validation error messages.

        Args:
            field_name: Optional specific field

        Returns:
            Locator for error message(s)
        """
        if field_name:
            return self.page.locator(f'[data-dazzle-error][data-dazzle-field="{field_name}"]')
        return self.page.locator("[data-dazzle-error]")

    # =========================================================================
    # Form Interactions
    # =========================================================================

    def fill_field(self, field_name: str, value: str) -> None:
        """Fill a text input field.

        Args:
            field_name: Field name
            value: Value to fill
        """
        self.field(field_name).fill(value)

    def select_option(self, field_name: str, value: str) -> None:
        """Select a dropdown option.

        Args:
            field_name: Field name
            value: Option value to select
        """
        self.field(field_name).select_option(value)

    def check_field(self, field_name: str, checked: bool = True) -> None:
        """Check or uncheck a checkbox.

        Args:
            field_name: Field name
            checked: Whether to check (True) or uncheck (False)
        """
        if checked:
            self.field(field_name).check()
        else:
            self.field(field_name).uncheck()

    def get_field_value(self, field_name: str) -> str:
        """Get the current value of a field.

        Args:
            field_name: Field name

        Returns:
            Current field value
        """
        return self.field(field_name).input_value()

    # =========================================================================
    # Actions
    # =========================================================================

    def click_action(self, action_name: str) -> None:
        """Click an action button.

        Args:
            action_name: Action name (e.g., "create", "save", "edit", "delete")
        """
        self.action(action_name).click()

    def click_create(self) -> None:
        """Click the create button."""
        self.click_action("create")

    def click_save(self) -> None:
        """Click the save button."""
        self.click_action("save")

    def click_edit(self) -> None:
        """Click the edit button."""
        self.click_action("edit")

    def click_delete(self) -> None:
        """Click the delete button."""
        self.click_action("delete")

    def click_row(self, entity: str, entity_id: str) -> None:
        """Click a table row to view details.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        self.row(entity, entity_id).click()

    # =========================================================================
    # Assertions
    # =========================================================================

    def assert_view_visible(self, view_name: str) -> None:
        """Assert a view is visible.

        Args:
            view_name: View name
        """
        expect(self.view(view_name)).to_be_visible()

    def assert_field_visible(self, field_name: str) -> None:
        """Assert a field is visible.

        Args:
            field_name: Field name
        """
        expect(self.field(field_name)).to_be_visible()

    def assert_action_visible(self, action_name: str) -> None:
        """Assert an action button is visible.

        Args:
            action_name: Action name
        """
        expect(self.action(action_name)).to_be_visible()

    def assert_action_hidden(self, action_name: str) -> None:
        """Assert an action button is hidden.

        Args:
            action_name: Action name
        """
        expect(self.action(action_name)).to_be_hidden()

    def assert_action_disabled(self, action_name: str) -> None:
        """Assert an action button is disabled.

        Args:
            action_name: Action name
        """
        expect(self.action(action_name)).to_be_disabled()

    def assert_row_exists(self, entity: str, entity_id: str) -> None:
        """Assert a row exists in the list.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        expect(self.row(entity, entity_id)).to_be_visible()

    def assert_row_not_exists(self, entity: str, entity_id: str) -> None:
        """Assert a row does not exist in the list.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        expect(self.row(entity, entity_id)).to_be_hidden()

    def assert_row_count(self, entity: str, expected_count: int) -> None:
        """Assert the number of rows in the list.

        Args:
            entity: Entity name
            expected_count: Expected number of rows
        """
        expect(self.row(entity)).to_have_count(expected_count)

    def assert_field_has_value(self, field_name: str, expected_value: str) -> None:
        """Assert a field has a specific value.

        Args:
            field_name: Field name
            expected_value: Expected value
        """
        expect(self.field(field_name)).to_have_value(expected_value)

    def assert_validation_error(
        self, field_name: str | None = None, message: str | None = None
    ) -> None:
        """Assert a validation error is shown.

        Args:
            field_name: Optional specific field
            message: Optional expected error message
        """
        error_locator = self.error_message(field_name)
        expect(error_locator).to_be_visible()
        if message:
            expect(error_locator).to_contain_text(message)

    def assert_no_validation_errors(self) -> None:
        """Assert no validation errors are shown."""
        expect(self.error_message()).to_have_count(0)

    # =========================================================================
    # Waits
    # =========================================================================

    def wait_for_view(self, view_name: str, timeout: float = 5000) -> None:
        """Wait for a view to be visible.

        Args:
            view_name: View name
            timeout: Timeout in milliseconds
        """
        self.view(view_name).wait_for(state="visible", timeout=timeout)

    def wait_for_navigation(self) -> None:
        """Wait for navigation to complete."""
        self.page.wait_for_load_state("networkidle")

    def wait_for_toast(self, message: str | None = None, timeout: float = 5000) -> None:
        """Wait for a toast notification.

        Args:
            message: Optional expected message
            timeout: Timeout in milliseconds
        """
        toast = self.page.locator('[data-dazzle-component="toast"]')
        toast.wait_for(state="visible", timeout=timeout)
        if message:
            expect(toast).to_contain_text(message)

    # =========================================================================
    # Dazzle Bar Interactions
    # =========================================================================

    def dazzle_bar(self) -> Locator:
        """Get the Dazzle Bar component."""
        return self.page.locator('[data-dazzle-component="dazzle-bar"]')

    def select_persona(self, persona_id: str) -> None:
        """Select a persona from the Dazzle Bar.

        Args:
            persona_id: Persona identifier
        """
        self.page.locator('[data-dazzle-control="persona-select"]').select_option(persona_id)
        self.wait_for_navigation()

    def click_reset_data(self) -> None:
        """Click the reset data button in the Dazzle Bar."""
        self.page.locator('[data-dazzle-action="reset"]').click()
        self.wait_for_navigation()

    def click_regenerate_data(self) -> None:
        """Click the regenerate data button in the Dazzle Bar."""
        self.page.locator('[data-dazzle-action="regenerate"]').click()
        self.wait_for_navigation()

    # =========================================================================
    # Screenshots
    # =========================================================================

    def screenshot(self, name: str, full_page: bool = False) -> bytes:
        """Take a screenshot.

        Args:
            name: Screenshot name (will be saved as {name}.png)
            full_page: Whether to capture the full page

        Returns:
            Screenshot bytes
        """
        return self.page.screenshot(path=f"screenshots/{name}.png", full_page=full_page)
