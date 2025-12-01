"""
Domain-Level Assertions for Dazzle E2E Testing.

Provides high-level assertions that operate on semantic concepts
(entities, fields, validation) rather than raw DOM checks.

Usage:
    assertions = DazzleAssertions(page, adapter)

    # Entity assertions
    await assertions.entity_exists("Task", {"title": "New Task"})
    await assertions.entity_not_exists("Task", {"id": "uuid-123"})

    # Validation assertions
    await assertions.validation_error("Task.title")
    await assertions.no_validation_errors()

    # View assertions
    await assertions.view_visible("task_list")
    await assertions.redirected_to("task_detail")
"""

from typing import TYPE_CHECKING, Any

from dazzle_e2e.locators import DazzleLocators

if TYPE_CHECKING:
    from playwright.async_api import Page

    from dazzle_e2e.adapters.base import BaseAdapter


class DazzleAssertions:
    """
    Domain-level assertions for Dazzle E2E tests.

    Provides semantic assertions that work with Dazzle concepts
    rather than raw DOM elements.
    """

    def __init__(self, page: "Page", adapter: "BaseAdapter | None" = None) -> None:
        """
        Initialize assertions.

        Args:
            page: Playwright Page instance
            adapter: Optional stack adapter for API calls
        """
        self.page = page
        self.adapter = adapter
        self.locators = DazzleLocators(page)

    async def entity_exists(
        self,
        entity: str,
        match: dict[str, Any] | None = None,
        timeout: int = 5000,
    ) -> None:
        """
        Assert that an entity exists (in the UI or via API).

        Args:
            entity: Entity name (e.g., "Task")
            match: Optional field values to match
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If entity doesn't exist
        """
        # First try UI-based check
        locator = self.locators.entity(entity)
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)

            # If match criteria provided, check via API
            if match and self.adapter:
                entities = await self.adapter.get_entities(entity)
                matching = [e for e in entities if all(e.get(k) == v for k, v in match.items())]
                if not matching:
                    raise AssertionError(f"Entity {entity} exists but no match for {match}")
        except Exception as e:
            # Try API fallback if adapter available
            if self.adapter:
                entities = await self.adapter.get_entities(entity)
                if not entities:
                    raise AssertionError(f"Entity {entity} does not exist") from e
                if match:
                    matching = [e for e in entities if all(e.get(k) == v for k, v in match.items())]
                    if not matching:
                        raise AssertionError(
                            f"Entity {entity} exists but no match for {match}"
                        ) from e
            else:
                raise AssertionError(f"Entity {entity} not found in UI") from e

    async def entity_not_exists(
        self,
        entity: str,
        match: dict[str, Any] | None = None,
        timeout: int = 2000,
    ) -> None:
        """
        Assert that an entity does not exist.

        Args:
            entity: Entity name (e.g., "Task")
            match: Optional field values that should not exist
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If entity exists
        """
        if self.adapter and match:
            # Use API to check
            entities = await self.adapter.get_entities(entity)
            matching = [e for e in entities if all(e.get(k) == v for k, v in match.items())]
            if matching:
                raise AssertionError(f"Entity {entity} with {match} still exists")
        else:
            # Check UI
            locator = self.locators.entity(entity)
            try:
                await locator.first.wait_for(state="hidden", timeout=timeout)
            except Exception:
                count = await locator.count()
                if count > 0:
                    raise AssertionError(f"Entity {entity} still exists in UI ({count} instances)")

    async def entity_count(
        self,
        entity: str,
        expected: int,
        timeout: int = 5000,
    ) -> None:
        """
        Assert the count of entity instances.

        Args:
            entity: Entity name
            expected: Expected count
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If count doesn't match
        """
        if self.adapter:
            entities = await self.adapter.get_entities(entity)
            actual = len(entities)
        else:
            locator = self.locators.row(entity)
            await locator.first.wait_for(timeout=timeout)
            actual = await locator.count()

        if actual != expected:
            raise AssertionError(f"Expected {expected} {entity} entities, got {actual}")

    async def validation_error(
        self,
        field: str,
        message: str | None = None,
        timeout: int = 3000,
    ) -> None:
        """
        Assert that a validation error exists for a field.

        Args:
            field: Field identifier (e.g., "Task.title")
            message: Optional expected error message
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If validation error doesn't exist
        """
        locator = self.locators.message(field, kind="validation")

        try:
            await locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"No validation error for field {field}") from e

        if message:
            text = await locator.text_content()
            if message not in (text or ""):
                raise AssertionError(f"Validation message '{text}' doesn't contain '{message}'")

    async def no_validation_errors(self, timeout: int = 1000) -> None:
        """
        Assert that no validation errors are visible.

        Args:
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If validation errors exist
        """
        locator = self.page.locator('[data-dazzle-message-kind="validation"]')
        try:
            await locator.first.wait_for(state="hidden", timeout=timeout)
        except Exception:
            count = await locator.count()
            if count > 0:
                raise AssertionError(f"Found {count} validation error(s)")

    async def view_visible(self, view_id: str, timeout: int = 5000) -> None:
        """
        Assert that a view is visible.

        Args:
            view_id: View identifier
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If view is not visible
        """
        locator = self.locators.view(view_id)
        try:
            await locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"View {view_id} is not visible") from e

    async def view_not_visible(self, view_id: str, timeout: int = 2000) -> None:
        """
        Assert that a view is not visible.

        Args:
            view_id: View identifier
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If view is visible
        """
        locator = self.locators.view(view_id)
        try:
            await locator.wait_for(state="hidden", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"View {view_id} is still visible") from e

    async def redirected_to(self, view_id: str, timeout: int = 5000) -> None:
        """
        Assert that navigation resulted in a specific view.

        Args:
            view_id: Expected view identifier
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If not on expected view
        """
        await self.view_visible(view_id, timeout)

    async def text_visible(self, text: str, timeout: int = 5000) -> None:
        """
        Assert that specific text is visible on the page.

        Args:
            text: Text to find
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If text is not visible
        """
        locator = self.page.get_by_text(text)
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"Text '{text}' is not visible") from e

    async def field_value(
        self,
        field: str,
        expected: str | bool,
        timeout: int = 3000,
    ) -> None:
        """
        Assert that a field has a specific value.

        Args:
            field: Field identifier
            expected: Expected value
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If field value doesn't match
        """
        locator = self.locators.field(field)
        await locator.wait_for(state="visible", timeout=timeout)

        if isinstance(expected, bool):
            is_checked = await locator.is_checked()
            if is_checked != expected:
                raise AssertionError(f"Field {field} checked={is_checked}, expected {expected}")
        else:
            value = await locator.input_value()
            if value != expected:
                raise AssertionError(f"Field {field} value='{value}', expected '{expected}'")

    async def dialog_open(self, dialog_id: str | None = None, timeout: int = 3000) -> None:
        """
        Assert that a dialog is open.

        Args:
            dialog_id: Optional dialog identifier
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If dialog is not open
        """
        locator = self.locators.dialog(dialog_id)
        try:
            await locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"Dialog {dialog_id or 'any'} is not open") from e

    async def dialog_closed(self, dialog_id: str | None = None, timeout: int = 2000) -> None:
        """
        Assert that a dialog is closed.

        Args:
            dialog_id: Optional dialog identifier
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If dialog is still open
        """
        locator = self.locators.dialog(dialog_id)
        try:
            await locator.wait_for(state="hidden", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"Dialog {dialog_id or 'any'} is still open") from e

    async def loading_complete(self, context: str | None = None, timeout: int = 10000) -> None:
        """
        Wait for loading to complete.

        Args:
            context: Optional loading context
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If loading doesn't complete
        """
        locator = self.locators.loading(context)
        try:
            await locator.wait_for(state="hidden", timeout=timeout)
        except Exception as e:
            raise AssertionError(f"Loading {context or ''} didn't complete") from e

    async def success_message(self, text: str | None = None, timeout: int = 5000) -> None:
        """
        Assert that a success message is visible.

        Args:
            text: Optional expected message text
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If success message not found
        """
        locator = self.page.locator('[data-dazzle-message-kind="success"]')
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError("No success message visible") from e

        if text:
            content = await locator.first.text_content()
            if text not in (content or ""):
                raise AssertionError(f"Success message '{content}' doesn't contain '{text}'")

    async def error_message(self, text: str | None = None, timeout: int = 5000) -> None:
        """
        Assert that an error message is visible.

        Args:
            text: Optional expected message text
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If error message not found
        """
        locator = self.page.locator('[data-dazzle-message-kind="error"]')
        try:
            await locator.first.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError("No error message visible") from e

        if text:
            content = await locator.first.text_content()
            if text not in (content or ""):
                raise AssertionError(f"Error message '{content}' doesn't contain '{text}'")

    # =========================================================================
    # Auth Assertions - For authentication testing
    # =========================================================================

    async def is_authenticated(self, timeout: int = 3000) -> None:
        """
        Assert that user is authenticated (user indicator visible).

        Args:
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If user is not authenticated
        """
        locator = self.locators.auth_user_indicator()
        try:
            await locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError("User is not authenticated (user indicator not visible)") from e

    async def is_not_authenticated(self, timeout: int = 3000) -> None:
        """
        Assert that user is not authenticated (login button visible).

        Args:
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If user is authenticated
        """
        locator = self.locators.auth_login_button()
        try:
            await locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError(
                "User appears to be authenticated (login button not visible)"
            ) from e

    async def login_succeeded(self, timeout: int = 5000) -> None:
        """
        Assert that login was successful (modal closed, user indicator visible).

        Args:
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If login did not succeed
        """
        # Auth modal should be closed
        modal = self.locators.auth_modal()
        try:
            await modal.wait_for(state="hidden", timeout=timeout)
        except Exception as e:
            raise AssertionError("Auth modal is still open after login") from e

        # User indicator should be visible
        await self.is_authenticated(timeout)

    async def login_failed(
        self,
        expected_error: str | None = None,
        timeout: int = 3000,
    ) -> None:
        """
        Assert that login failed (error message visible).

        Args:
            expected_error: Optional expected error message text
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If login didn't fail or error doesn't match
        """
        error_locator = self.locators.auth_error()
        try:
            await error_locator.wait_for(state="visible", timeout=timeout)
        except Exception as e:
            raise AssertionError("No auth error visible - login may have succeeded") from e

        if expected_error:
            text = await error_locator.text_content()
            if expected_error not in (text or ""):
                raise AssertionError(
                    f"Auth error '{text}' doesn't contain expected '{expected_error}'"
                )

    async def route_protected(self, timeout: int = 3000) -> None:
        """
        Assert that the current route is protected (auth modal shown or redirected).

        Args:
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If route is not protected
        """
        # Either auth modal is shown, or we see login button (redirected to public page)
        modal = self.locators.auth_modal()
        login_button = self.locators.auth_login_button()

        try:
            # Try modal first
            await modal.wait_for(state="visible", timeout=timeout // 2)
            return  # Modal visible = protected
        except Exception:
            pass  # Modal not visible, check for login button

        try:
            await login_button.wait_for(state="visible", timeout=timeout // 2)
            return  # Login button visible = redirected to public page
        except Exception as e:
            raise AssertionError(
                "Route does not appear protected (no auth modal or login button visible)"
            ) from e

    async def has_persona(self, persona: str, timeout: int = 3000) -> None:
        """
        Assert that the current user has a specific persona/role.

        Args:
            persona: Persona identifier to check
            timeout: Timeout in milliseconds

        Raises:
            AssertionError: If user doesn't have the persona
        """
        # Check for persona indicator in user menu or via API
        persona_locator = self.page.locator(f'[data-dazzle-persona="{persona}"]')
        try:
            await persona_locator.wait_for(state="visible", timeout=timeout)
        except Exception:
            # Fallback: check via adapter if available
            if self.adapter:
                try:
                    user_info = await self.adapter.get_current_user()
                    if user_info and user_info.get("persona") == persona:
                        return
                except Exception:
                    pass
            raise AssertionError(f"User does not have persona '{persona}'")
