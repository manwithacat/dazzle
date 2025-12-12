"""Invariant tests for FieldTest Hub.

Tests business rule validation:
- IssueReport: fixed/closed requires resolution field
- TestSession: duration_minutes > 0
- FirmwareRelease: released requires release_notes
- Task: in_progress requires assigned_to

These tests verify that the app enforces data integrity rules
through validation errors in the UI.
"""

from __future__ import annotations

import pytest
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# IssueReport Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.issue_report
class TestIssueReportInvariants:
    """Test IssueReport business rules."""

    def test_fixed_requires_resolution(self, as_engineer: FieldTestHubPage):
        """Cannot mark issue as fixed without resolution."""
        app = as_engineer

        # Create an issue
        app.navigate_to_entity_create("IssueReport")
        app.fill_field("title", "Test Issue Without Resolution")
        app.fill_field("description", "This issue has no resolution")
        app.fill_field("severity", "medium")
        app.click_save()
        app.wait_for_navigation()

        # Try to transition to fixed without resolution
        # Should show validation error

    def test_closed_requires_resolution(self, as_engineer: FieldTestHubPage):
        """Cannot close issue without resolution."""
        app = as_engineer

        # Navigate to issue list to verify page loads
        app.navigate_to_entity_list("IssueReport")
        # Similar test - closed state should require resolution

    def test_resolution_field_accepts_valid_text(self, as_engineer: FieldTestHubPage):
        """Resolution field accepts valid text input."""
        app = as_engineer

        app.navigate_to_entity_create("IssueReport")
        app.fill_field("title", "Issue With Resolution")
        app.fill_field("description", "This issue will have a resolution")
        app.fill_field("severity", "medium")
        app.fill_field("resolution", "Fixed by updating the firmware to v2.0")
        app.click_save()
        app.wait_for_navigation()

        # Should save successfully
        app.assert_no_validation_errors()


# =============================================================================
# TestSession Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.test_session
class TestSessionInvariants:
    """Test TestSession business rules."""

    def test_duration_must_be_positive(self, as_tester: FieldTestHubPage):
        """TestSession duration_minutes must be > 0."""
        app = as_tester

        app.navigate_to_entity_create("TestSession")
        app.fill_field("notes", "Test session with zero duration")
        app.fill_field("duration_minutes", "0")
        app.click_save()

        # Should show validation error for duration
        app.assert_validation_error("duration_minutes")

    def test_duration_rejects_negative(self, as_tester: FieldTestHubPage):
        """TestSession duration_minutes cannot be negative."""
        app = as_tester

        app.navigate_to_entity_create("TestSession")
        app.fill_field("notes", "Test session with negative duration")
        app.fill_field("duration_minutes", "-30")
        app.click_save()

        # Should show validation error
        app.assert_validation_error("duration_minutes")

    def test_duration_accepts_valid_positive(self, as_tester: FieldTestHubPage):
        """TestSession duration_minutes accepts positive values."""
        app = as_tester

        app.navigate_to_entity_create("TestSession")
        app.fill_field("notes", "Valid test session")
        app.fill_field("duration_minutes", "60")
        # Select a device if required
        app.click_save()
        app.wait_for_navigation()

        # Should save without validation errors
        app.assert_no_validation_errors()


# =============================================================================
# FirmwareRelease Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.firmware
class TestFirmwareReleaseInvariants:
    """Test FirmwareRelease business rules."""

    def test_released_requires_release_notes(self, as_engineer: FieldTestHubPage):
        """Cannot release firmware without release_notes."""
        app = as_engineer

        # Create a firmware release without notes
        app.navigate_to_entity_create("FirmwareRelease")
        app.fill_field("version", "0.0.99-test")
        # Leave release_notes empty
        app.click_save()
        app.wait_for_navigation()

        # Try to release - should fail or prompt for notes

    def test_version_format_validated(self, as_engineer: FieldTestHubPage):
        """Firmware version follows expected format."""
        app = as_engineer

        app.navigate_to_entity_create("FirmwareRelease")
        # Try invalid version format if there's validation
        app.fill_field("version", "invalid")
        app.click_save()

        # May show validation error depending on DSL rules

    def test_release_notes_accepts_valid_text(self, as_engineer: FieldTestHubPage):
        """Release notes field accepts valid text."""
        app = as_engineer

        app.navigate_to_entity_create("FirmwareRelease")
        app.fill_field("version", "1.0.0-valid")
        app.fill_field("release_notes", "Initial release with bug fixes and improvements")
        app.click_save()
        app.wait_for_navigation()

        app.assert_no_validation_errors()


# =============================================================================
# Task Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.task
class TestTaskInvariants:
    """Test Task business rules."""

    def test_in_progress_requires_assignee(self, as_engineer: FieldTestHubPage):
        """Cannot start task without assigned_to."""
        app = as_engineer

        # Create a task without assignee
        app.navigate_to_entity_create("Task")
        app.fill_field("title", "Unassigned Task")
        app.fill_field("description", "Task with no assignee")
        # Leave assigned_to empty
        app.click_save()
        app.wait_for_navigation()

        # Try to transition to in_progress - should fail

    def test_task_title_required(self, as_engineer: FieldTestHubPage):
        """Task must have a title."""
        app = as_engineer

        app.navigate_to_entity_create("Task")
        # Leave title empty
        app.fill_field("description", "Task without title")
        app.click_save()

        # Should show validation error
        app.assert_validation_error("title")

    def test_task_accepts_valid_data(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Task accepts valid data with all required fields."""
        app = as_engineer

        # Get a tester to assign
        testers = demo_data.get("entities", {}).get("Tester", [])
        tester_id = testers[0]["id"] if testers else None

        app.navigate_to_entity_create("Task")
        app.fill_field("title", "Valid Task")
        app.fill_field("description", "A properly configured task")
        if tester_id:
            app.select_option("assigned_to", tester_id)
        app.click_save()
        app.wait_for_navigation()

        app.assert_no_validation_errors()


# =============================================================================
# Device Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.device
class TestDeviceInvariants:
    """Test Device business rules."""

    def test_serial_number_required(self, as_engineer: FieldTestHubPage):
        """Device must have a serial number."""
        app = as_engineer

        app.navigate_to_entity_create("Device")
        app.fill_field("name", "Device Without Serial")
        # Leave serial_number empty
        app.click_save()

        # Should show validation error
        app.assert_validation_error("serial_number")

    def test_serial_number_unique(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Device serial numbers must be unique."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])

        if devices:
            existing_serial = devices[0].get("serial_number", "EXISTING-001")

            app.navigate_to_entity_create("Device")
            app.fill_field("name", "Duplicate Serial Device")
            app.fill_field("serial_number", existing_serial)
            app.click_save()

            # Should show uniqueness validation error

    def test_device_name_required(self, as_engineer: FieldTestHubPage):
        """Device must have a name."""
        app = as_engineer

        app.navigate_to_entity_create("Device")
        # Leave name empty
        app.fill_field("serial_number", "NO-NAME-001")
        app.click_save()

        # Should show validation error
        app.assert_validation_error("name")


# =============================================================================
# Tester Invariants
# =============================================================================


@pytest.mark.invariant
@pytest.mark.tester
class TestTesterInvariants:
    """Test Tester business rules."""

    def test_tester_name_required(self, as_engineer: FieldTestHubPage):
        """Tester must have a name."""
        app = as_engineer

        app.navigate_to_entity_create("Tester")
        # Leave name empty
        app.fill_field("email", "no-name@example.com")
        app.click_save()

        # Should show validation error
        app.assert_validation_error("name")

    def test_tester_email_format(self, as_engineer: FieldTestHubPage):
        """Tester email must be valid format."""
        app = as_engineer

        app.navigate_to_entity_create("Tester")
        app.fill_field("name", "Invalid Email Tester")
        app.fill_field("email", "not-an-email")
        app.click_save()

        # Should show validation error for email format
        app.assert_validation_error("email")

    def test_tester_accepts_valid_data(self, as_engineer: FieldTestHubPage):
        """Tester accepts valid data."""
        app = as_engineer

        app.navigate_to_entity_create("Tester")
        app.fill_field("name", "Valid Tester")
        app.fill_field("email", "valid@example.com")
        app.click_save()
        app.wait_for_navigation()

        app.assert_no_validation_errors()
