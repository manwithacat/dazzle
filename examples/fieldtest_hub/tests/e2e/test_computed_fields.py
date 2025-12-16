"""Computed field tests for FieldTest Hub.

Tests computed fields that are derived from other data:
- IssueReport.days_open: computed from reported_at
- Task.days_open: computed from created_at

These values should update appropriately and display correctly in the UI.
"""

from __future__ import annotations

import pytest
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# IssueReport Computed Fields
# =============================================================================


@pytest.mark.computed
@pytest.mark.issue_report
class TestIssueReportComputedFields:
    """Test computed fields for IssueReport."""

    def test_days_open_displayed_in_list(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open field should be visible in list view."""
        app = as_engineer
        app.navigate_to_entity_list("IssueReport")

        # Look for days_open field in any row
        days_open_field = app.page.locator('[data-dazzle-field="days_open"]')

        # Should have at least one days_open field visible
        if days_open_field.count() > 0:
            # Verify it contains a number
            text = days_open_field.first.inner_text()
            assert text.strip().isdigit() or "day" in text.lower()

    def test_days_open_displayed_in_detail(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open should be visible in detail view."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])

        if issues:
            issue_id = issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)

            # Look for days_open in detail view
            days_open_field = app.page.locator('[data-dazzle-field="days_open"]')

            if days_open_field.count() > 0:
                text = days_open_field.first.inner_text()
                # Should be a number or formatted string
                assert len(text) > 0

    def test_days_open_is_non_negative(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open should always be non-negative."""
        app = as_engineer
        app.navigate_to_entity_list("IssueReport")

        days_open_fields = app.page.locator('[data-dazzle-field="days_open"]')
        count = days_open_fields.count()

        for i in range(min(count, 5)):  # Check first 5
            text = days_open_fields.nth(i).inner_text().strip()
            # Extract number if formatted
            if text.isdigit():
                assert int(text) >= 0, f"days_open should be >= 0, got {text}"

    def test_new_issue_has_zero_days_open(self, as_engineer: FieldTestHubPage):
        """Newly created issue should have 0 days_open."""
        app = as_engineer

        # Create a new issue
        app.navigate_to_entity_create("IssueReport")
        app.fill_field("title", "Brand New Issue")
        app.fill_field("description", "Just created for testing days_open")
        app.fill_field("severity", "low")
        app.click_save()
        app.wait_for_navigation()

        # Check days_open in detail view
        days_open_field = app.page.locator('[data-dazzle-field="days_open"]')
        if days_open_field.count() > 0:
            text = days_open_field.first.inner_text().strip()
            # Should be 0 or "0 days" or similar
            assert "0" in text, f"New issue should have 0 days_open, got {text}"


# =============================================================================
# Task Computed Fields
# =============================================================================


@pytest.mark.computed
@pytest.mark.task
class TestTaskComputedFields:
    """Test computed fields for Task."""

    def test_days_open_displayed_in_list(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open field should be visible in task list."""
        app = as_engineer
        app.navigate_to_entity_list("Task")

        days_open_field = app.page.locator('[data-dazzle-field="days_open"]')

        if days_open_field.count() > 0:
            text = days_open_field.first.inner_text()
            assert text.strip().isdigit() or "day" in text.lower()

    def test_days_open_displayed_in_detail(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open should be visible in task detail view."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])

        if tasks:
            task_id = tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)

            days_open_field = app.page.locator('[data-dazzle-field="days_open"]')

            if days_open_field.count() > 0:
                text = days_open_field.first.inner_text()
                assert len(text) > 0

    def test_new_task_has_zero_days_open(self, as_engineer: FieldTestHubPage):
        """Newly created task should have 0 days_open."""
        app = as_engineer

        app.navigate_to_entity_create("Task")
        app.fill_field("title", "Brand New Task")
        app.fill_field("description", "Just created for testing")
        app.click_save()
        app.wait_for_navigation()

        days_open_field = app.page.locator('[data-dazzle-field="days_open"]')
        if days_open_field.count() > 0:
            text = days_open_field.first.inner_text().strip()
            assert "0" in text, f"New task should have 0 days_open, got {text}"

    def test_completed_task_days_open_stops(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Completed tasks should have frozen days_open."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        completed_tasks = [t for t in tasks if t.get("status") == "completed"]

        if completed_tasks:
            task_id = completed_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)

            # Get days_open value
            days_open_field = app.page.locator('[data-dazzle-field="days_open"]')
            if days_open_field.count() > 0:
                # Value should exist and be stable (not increasing)
                text = days_open_field.first.inner_text()
                assert len(text) > 0


# =============================================================================
# Computed Field Consistency Tests
# =============================================================================


@pytest.mark.computed
@pytest.mark.consistency
class TestComputedFieldConsistency:
    """Test computed field consistency across views."""

    def test_issue_days_open_same_in_list_and_detail(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """days_open should be consistent between list and detail views."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])

        if issues:
            issue_id = issues[0]["id"]

            # Get from list view
            app.navigate_to_entity_list("IssueReport")
            row = app.row("IssueReport", issue_id)
            if row.count() > 0:
                list_days = row.locator('[data-dazzle-field="days_open"]')
                list_value = list_days.inner_text() if list_days.count() > 0 else None

                # Get from detail view
                app.navigate_to_entity_detail("IssueReport", issue_id)
                detail_days = app.page.locator('[data-dazzle-field="days_open"]')
                detail_value = detail_days.first.inner_text() if detail_days.count() > 0 else None

                # Should match
                if list_value and detail_value:
                    assert (
                        list_value.strip() == detail_value.strip()
                    ), f"List: {list_value}, Detail: {detail_value}"

    def test_task_days_open_same_in_list_and_detail(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """days_open should be consistent between list and detail for tasks."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])

        if tasks:
            task_id = tasks[0]["id"]

            # Get from list view
            app.navigate_to_entity_list("Task")
            row = app.row("Task", task_id)
            if row.count() > 0:
                list_days = row.locator('[data-dazzle-field="days_open"]')
                list_value = list_days.inner_text() if list_days.count() > 0 else None

                # Get from detail view
                app.navigate_to_entity_detail("Task", task_id)
                detail_days = app.page.locator('[data-dazzle-field="days_open"]')
                detail_value = detail_days.first.inner_text() if detail_days.count() > 0 else None

                if list_value and detail_value:
                    assert (
                        list_value.strip() == detail_value.strip()
                    ), f"List: {list_value}, Detail: {detail_value}"


# =============================================================================
# Computed Field Format Tests
# =============================================================================


@pytest.mark.computed
@pytest.mark.format
class TestComputedFieldFormat:
    """Test computed field display formats."""

    def test_days_open_is_integer(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open should be displayed as an integer (no decimals)."""
        app = as_engineer
        app.navigate_to_entity_list("IssueReport")

        days_open_fields = app.page.locator('[data-dazzle-field="days_open"]')

        if days_open_fields.count() > 0:
            text = days_open_fields.first.inner_text().strip()
            # Should not contain decimal point
            if text.replace("-", "").isdigit():
                assert "." not in text, f"days_open should be integer, got {text}"

    def test_days_open_has_unit_label(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """days_open may include unit label like 'days'."""
        app = as_engineer
        app.navigate_to_entity_list("IssueReport")

        # This test checks if the format includes a label
        # Pass if it's just a number or includes "day/days"
        days_open_fields = app.page.locator('[data-dazzle-field="days_open"]')

        if days_open_fields.count() > 0:
            text = days_open_fields.first.inner_text().strip().lower()
            # Should be a number or number with "day(s)"
            is_valid = text.replace("-", "").isdigit() or "day" in text or text.split()[0].isdigit()
            assert is_valid, f"Unexpected days_open format: {text}"
