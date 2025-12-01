"""
Semantic Locator Library for Dazzle E2E Testing.

Provides locators that operate on semantic identifiers (data-dazzle-* attributes)
rather than CSS selectors, making tests stack-agnostic.

Usage:
    locators = DazzleLocators(page)

    # Find by view
    await locators.view("task_list").wait_for()

    # Find by entity
    await locators.entity("Task").first.click()
    await locators.entity("Task", entity_id="uuid-123").click()

    # Find by field
    await locators.field("Task.title").fill("New Task")

    # Find by action
    await locators.action("Task.create").click()
    await locators.action("Task.save", role="primary").click()

    # Find messages
    validation_msg = locators.message("Task.title", kind="validation")
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


class DazzleLocators:
    """
    Semantic locators for Dazzle applications.

    Provides methods to locate elements using data-dazzle-* attributes,
    which are emitted by DNR UI components.
    """

    def __init__(self, page: "Page") -> None:
        """
        Initialize locators for a Playwright page.

        Args:
            page: Playwright Page instance
        """
        self.page = page

    def view(self, view_id: str) -> "Locator":
        """
        Locate a view/page by its identifier.

        Args:
            view_id: View identifier (e.g., "task_list", "task_detail")

        Returns:
            Playwright Locator for the view element
        """
        return self.page.locator(f'[data-dazzle-view="{view_id}"]')

    def entity(self, entity_name: str, entity_id: str | None = None) -> "Locator":
        """
        Locate elements for an entity.

        Args:
            entity_name: Entity name (e.g., "Task", "User")
            entity_id: Optional entity instance ID

        Returns:
            Playwright Locator for entity elements
        """
        selector = f'[data-dazzle-entity="{entity_name}"]'
        if entity_id:
            selector += f'[data-dazzle-entity-id="{entity_id}"]'
        return self.page.locator(selector)

    def field(self, field_id: str, field_type: str | None = None) -> "Locator":
        """
        Locate a field input by its identifier.

        Args:
            field_id: Field identifier (e.g., "Task.title", "User.email")
            field_type: Optional field type filter (e.g., "text", "checkbox")

        Returns:
            Playwright Locator for the field element
        """
        selector = f'[data-dazzle-field="{field_id}"]'
        if field_type:
            selector += f'[data-dazzle-field-type="{field_type}"]'
        return self.page.locator(selector)

    def action(self, action_id: str, role: str | None = None) -> "Locator":
        """
        Locate an action button by its identifier.

        Args:
            action_id: Action identifier (e.g., "Task.create", "Task.save")
            role: Optional action role filter (e.g., "primary", "destructive")

        Returns:
            Playwright Locator for the action element
        """
        selector = f'[data-dazzle-action="{action_id}"]'
        if role:
            selector += f'[data-dazzle-action-role="{role}"]'
        return self.page.locator(selector)

    def message(self, target: str, kind: str | None = None) -> "Locator":
        """
        Locate a message element by its target.

        Args:
            target: Message target (e.g., "Task.title", "global")
            kind: Optional message kind (e.g., "validation", "success", "error")

        Returns:
            Playwright Locator for the message element
        """
        selector = f'[data-dazzle-message="{target}"]'
        if kind:
            selector += f'[data-dazzle-message-kind="{kind}"]'
        return self.page.locator(selector)

    def form(self, entity: str | None = None, mode: str | None = None) -> "Locator":
        """
        Locate a form element.

        Args:
            entity: Optional entity name for the form
            mode: Optional form mode (e.g., "create", "edit")

        Returns:
            Playwright Locator for the form element
        """
        if entity:
            selector = f'[data-dazzle-form="{entity}"]'
        else:
            selector = "[data-dazzle-form]"

        if mode:
            selector += f'[data-dazzle-form-mode="{mode}"]'
        return self.page.locator(selector)

    def table(self, entity: str) -> "Locator":
        """
        Locate a data table for an entity.

        Args:
            entity: Entity name for the table

        Returns:
            Playwright Locator for the table element
        """
        return self.page.locator(f'[data-dazzle-table="{entity}"]')

    def row(self, entity: str, entity_id: str | None = None) -> "Locator":
        """
        Locate table rows for an entity.

        Args:
            entity: Entity name
            entity_id: Optional entity instance ID

        Returns:
            Playwright Locator for row elements
        """
        selector = f'[data-dazzle-row="{entity}"]'
        if entity_id:
            selector += f'[data-dazzle-entity-id="{entity_id}"]'
        return self.page.locator(selector)

    def cell(self, field_id: str) -> "Locator":
        """
        Locate table cells for a field.

        Args:
            field_id: Field identifier (e.g., "Task.title")

        Returns:
            Playwright Locator for cell elements
        """
        return self.page.locator(f'[data-dazzle-cell="{field_id}"]')

    def column(self, field_id: str) -> "Locator":
        """
        Locate table column headers for a field.

        Args:
            field_id: Field identifier (e.g., "Task.title")

        Returns:
            Playwright Locator for column header elements
        """
        return self.page.locator(f'[data-dazzle-column="{field_id}"]')

    def dialog(self, dialog_id: str | None = None) -> "Locator":
        """
        Locate a dialog/modal element.

        Args:
            dialog_id: Optional dialog identifier

        Returns:
            Playwright Locator for the dialog element
        """
        if dialog_id:
            return self.page.locator(f'[data-dazzle-dialog="{dialog_id}"]')
        return self.page.locator("[data-dazzle-dialog]")

    def loading(self, context: str | None = None) -> "Locator":
        """
        Locate loading indicators.

        Args:
            context: Optional loading context identifier

        Returns:
            Playwright Locator for loading elements
        """
        if context:
            return self.page.locator(f'[data-dazzle-loading="{context}"]')
        return self.page.locator("[data-dazzle-loading]")

    def nav(self, target: str | None = None) -> "Locator":
        """
        Locate navigation elements.

        Args:
            target: Optional navigation target

        Returns:
            Playwright Locator for navigation elements
        """
        if target:
            return self.page.locator(f'[data-dazzle-nav="{target}"]')
        return self.page.locator("[data-dazzle-nav]")

    def breadcrumb(self) -> "Locator":
        """
        Locate breadcrumb navigation.

        Returns:
            Playwright Locator for breadcrumb element
        """
        return self.page.locator("[data-dazzle-breadcrumb]")

    def breadcrumb_current(self) -> "Locator":
        """
        Locate current breadcrumb item.

        Returns:
            Playwright Locator for current breadcrumb element
        """
        return self.page.locator("[data-dazzle-breadcrumb-current]")

    # =========================================================================
    # Auth Locators - For authentication testing
    # =========================================================================

    def auth_login_button(self) -> "Locator":
        """
        Locate the login button in the header/nav.

        Returns:
            Playwright Locator for the login button
        """
        return self.page.locator('[data-dazzle-auth-action="login"]')

    def auth_logout_button(self) -> "Locator":
        """
        Locate the logout button in the user menu.

        Returns:
            Playwright Locator for the logout button
        """
        return self.page.locator('[data-dazzle-auth-action="logout"]')

    def auth_modal(self) -> "Locator":
        """
        Locate the authentication modal dialog.

        Returns:
            Playwright Locator for the auth modal
        """
        return self.page.locator("#dz-auth-modal")

    def auth_form(self) -> "Locator":
        """
        Locate the authentication form (within modal).

        Returns:
            Playwright Locator for the auth form
        """
        return self.page.locator("#dz-auth-form")

    def auth_field(self, name: str) -> "Locator":
        """
        Locate an auth form field by name.

        Args:
            name: Field name (e.g., "email", "password")

        Returns:
            Playwright Locator for the field
        """
        return self.page.locator(f'#dz-auth-form [name="{name}"]')

    def auth_error(self) -> "Locator":
        """
        Locate the auth error message element.

        Returns:
            Playwright Locator for visible error message
        """
        return self.page.locator("#dz-auth-error:not(.hidden)")

    def auth_submit(self) -> "Locator":
        """
        Locate the auth form submit button.

        Returns:
            Playwright Locator for the submit button
        """
        return self.page.locator("#dz-auth-submit")

    def auth_user_indicator(self) -> "Locator":
        """
        Locate the user indicator (avatar/menu) when logged in.

        Returns:
            Playwright Locator for the user indicator
        """
        return self.page.locator("[data-dazzle-auth-user]")

    def auth_mode_toggle(self, mode: str) -> "Locator":
        """
        Locate auth mode toggle (login vs register).

        Args:
            mode: Mode to toggle to ("login" or "register")

        Returns:
            Playwright Locator for the mode toggle link
        """
        return self.page.locator(f'[data-dazzle-auth-toggle="{mode}"]')


def parse_semantic_target(target: str) -> tuple[str, str]:
    """
    Parse a semantic target string into type and identifier.

    Examples:
        "view:task_list" -> ("view", "task_list")
        "field:Task.title" -> ("field", "Task.title")
        "action:Task.create" -> ("action", "Task.create")
        "row:Task" -> ("row", "Task")

    Args:
        target: Semantic target string

    Returns:
        Tuple of (target_type, identifier)

    Raises:
        ValueError: If target format is invalid
    """
    if ":" not in target:
        raise ValueError(f"Invalid semantic target format: {target}. Expected 'type:identifier'")

    target_type, identifier = target.split(":", 1)
    return target_type, identifier


def get_locator_for_target(locators: DazzleLocators, target: str) -> "Locator":
    """
    Get a Playwright Locator for a semantic target.

    Args:
        locators: DazzleLocators instance
        target: Semantic target string (e.g., "view:task_list", "field:Task.title")

    Returns:
        Playwright Locator for the target

    Raises:
        ValueError: If target type is unknown
    """
    target_type, identifier = parse_semantic_target(target)

    match target_type:
        case "view":
            return locators.view(identifier)
        case "entity":
            return locators.entity(identifier)
        case "field":
            return locators.field(identifier)
        case "action":
            return locators.action(identifier)
        case "message":
            return locators.message(identifier)
        case "form":
            return locators.form(identifier)
        case "table":
            return locators.table(identifier)
        case "row":
            return locators.row(identifier)
        case "cell":
            return locators.cell(identifier)
        case "dialog":
            return locators.dialog(identifier)
        case "nav":
            return locators.nav(identifier)
        case "auth":
            # Auth locators: auth:login_button, auth:logout_button, auth:modal, etc.
            return _get_auth_locator(locators, identifier)
        case _:
            raise ValueError(f"Unknown target type: {target_type}")


def _get_auth_locator(locators: DazzleLocators, identifier: str) -> "Locator":
    """
    Get auth locator by identifier.

    Args:
        locators: DazzleLocators instance
        identifier: Auth element identifier

    Returns:
        Playwright Locator for the auth element

    Raises:
        ValueError: If identifier is unknown
    """
    match identifier:
        case "login_button":
            return locators.auth_login_button()
        case "logout_button":
            return locators.auth_logout_button()
        case "modal":
            return locators.auth_modal()
        case "form":
            return locators.auth_form()
        case "submit":
            return locators.auth_submit()
        case "error":
            return locators.auth_error()
        case "user_indicator":
            return locators.auth_user_indicator()
        case _ if identifier.startswith("field."):
            field_name = identifier[6:]  # Strip "field." prefix
            return locators.auth_field(field_name)
        case _ if identifier.startswith("toggle."):
            mode = identifier[7:]  # Strip "toggle." prefix
            return locators.auth_mode_toggle(mode)
        case _:
            raise ValueError(f"Unknown auth identifier: {identifier}")
