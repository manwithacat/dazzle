"""User Story Tests for FieldTest Hub.

Tests all 18 user stories from dsl/seeds/stories/stories.json.
Each test corresponds to a specific story ID (ST-001 through ST-018).

These tests verify that the generated application correctly implements
the business logic defined in the DSL specifications.
"""

from __future__ import annotations

import pytest
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# Device Stories (ST-001 to ST-004)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestDeviceStories:
    """Tests for Device entity user stories."""

    def test_ST_001_engineer_creates_device(self, as_engineer: FieldTestHubPage, story_tracker):
        """ST-001: Engineer creates a new Device.

        Preconditions:
            - Engineer has permission to create Device

        Expected outcome:
            - New Device is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        # Navigate to device creation form
        app.navigate_to_entity_create("Device")
        app.wait_for_view("device_create")

        # Fill required fields
        app.fill_field("name", "Test Device Alpha")
        app.fill_field("model", "Model X-100")
        app.fill_field("batch_number", "BATCH-2025-001")
        app.fill_field("serial_number", "SN-12345-ALPHA")

        # Submit form
        app.click_save()

        # Verify success
        app.wait_for_navigation()
        # Should redirect to list or detail view
        # assert_toast_message(app.page, "created")

        story_tracker.mark_tested("ST-001", passed=True)

    def test_ST_002_engineer_activates_device(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-002: Engineer changes Device from prototype to active.

        Preconditions:
            - Device.status is 'prototype'

        Expected outcome:
            - Device.status becomes 'active'
        """
        app = as_engineer

        # First, create a device in prototype status via API
        device = api_client.create(
            "Device",
            {
                "name": "Prototype Device",
                "model": "Proto-1",
                "batch_number": "BATCH-PROTO",
                "serial_number": "SN-PROTO-001",
                "status": "prototype",
                "firmware_version": "v1.0.0",  # Required for activation
            },
        )
        device_id = device["id"]

        # Navigate to device edit
        app.navigate_to_entity_edit("Device", device_id)
        app.wait_for_view("device_edit")

        # Change status to active
        app.select_option("status", "active")
        app.click_save()

        # Verify the transition succeeded
        app.wait_for_navigation()
        updated = api_client.get("Device", device_id)
        assert updated["status"] == "active"

        story_tracker.mark_tested("ST-002", passed=True)

    def test_ST_003_engineer_recalls_device(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-003: Engineer changes Device from active to recalled.

        Preconditions:
            - Device.status is 'active'

        Expected outcome:
            - Device.status becomes 'recalled'
        """
        app = as_engineer

        # Create an active device
        device = api_client.create(
            "Device",
            {
                "name": "Active Device",
                "model": "Active-1",
                "batch_number": "BATCH-ACTIVE",
                "serial_number": "SN-ACTIVE-001",
                "status": "active",
            },
        )
        device_id = device["id"]

        # Navigate to device edit
        app.navigate_to_entity_edit("Device", device_id)
        app.wait_for_view("device_edit")

        # Change status to recalled
        app.select_option("status", "recalled")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("Device", device_id)
        assert updated["status"] == "recalled"

        story_tracker.mark_tested("ST-003", passed=True)

    def test_ST_004_engineer_retires_device(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-004: Engineer changes Device from active to retired.

        Preconditions:
            - Device.status is 'active'

        Expected outcome:
            - Device.status becomes 'retired'
        """
        app = as_engineer

        # Create an active device
        device = api_client.create(
            "Device",
            {
                "name": "Retiring Device",
                "model": "Retire-1",
                "batch_number": "BATCH-RETIRE",
                "serial_number": "SN-RETIRE-001",
                "status": "active",
            },
        )
        device_id = device["id"]

        # Navigate to device edit
        app.navigate_to_entity_edit("Device", device_id)
        app.wait_for_view("device_edit")

        # Change status to retired
        app.select_option("status", "retired")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("Device", device_id)
        assert updated["status"] == "retired"

        story_tracker.mark_tested("ST-004", passed=True)


# =============================================================================
# Tester Story (ST-005)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestTesterStories:
    """Tests for Tester entity user stories."""

    def test_ST_005_engineer_creates_tester(self, as_engineer: FieldTestHubPage, story_tracker):
        """ST-005: Engineer creates a new Tester.

        Preconditions:
            - Engineer has permission to create Tester

        Expected outcome:
            - New Tester is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        # Navigate to tester creation form
        app.navigate_to_entity_create("Tester")
        app.wait_for_view("tester_create")

        # Fill required fields
        app.fill_field("name", "Jane Doe")
        app.fill_field("email", "jane.doe@fieldtest.test")
        app.fill_field("location", "San Francisco, CA")
        app.select_option("skill_level", "enthusiast")

        # Submit form
        app.click_save()

        # Verify success
        app.wait_for_navigation()

        story_tracker.mark_tested("ST-005", passed=True)


# =============================================================================
# Issue Report Stories (ST-006 to ST-009)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestIssueReportStories:
    """Tests for IssueReport entity user stories."""

    def test_ST_006_engineer_creates_issue_report(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-006: Engineer creates a new Issue Report.

        Preconditions:
            - Engineer has permission to create IssueReport

        Expected outcome:
            - New IssueReport is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        # Get a device and tester from demo data for references
        devices = demo_data["entities"].get("Device", [])
        testers = demo_data["entities"].get("Tester", [])

        if not devices or not testers:
            pytest.skip("Demo data required for this test")

        device_id = devices[0]["id"]
        tester_id = testers[0]["id"]

        # Navigate to issue report creation form
        app.navigate_to_entity_create("IssueReport")
        app.wait_for_view("issue_report_create")

        # Fill required fields
        app.select_option("device_id", device_id)
        app.select_option("reported_by_id", tester_id)
        app.select_option("category", "battery")
        app.select_option("severity", "high")
        app.fill_field("description", "Battery draining faster than expected")

        # Submit form
        app.click_save()

        # Verify success
        app.wait_for_navigation()

        story_tracker.mark_tested("ST-006", passed=True)

    def test_ST_007_engineer_triages_issue(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-007: Engineer changes IssueReport from open to triaged.

        Preconditions:
            - IssueReport.status is 'open'

        Expected outcome:
            - IssueReport.status becomes 'triaged'
        """
        app = as_engineer

        # Get references
        devices = demo_data["entities"].get("Device", [])
        testers = demo_data["entities"].get("Tester", [])

        if not devices or not testers:
            pytest.skip("Demo data required for this test")

        # Create an open issue
        issue = api_client.create(
            "IssueReport",
            {
                "device_id": devices[0]["id"],
                "reported_by_id": testers[0]["id"],
                "category": "connectivity",
                "severity": "medium",
                "description": "WiFi connection drops intermittently",
                "status": "open",
            },
        )
        issue_id = issue["id"]

        # Navigate to issue edit
        app.navigate_to_entity_edit("IssueReport", issue_id)
        app.wait_for_view("issue_report_edit")

        # Change status to triaged
        app.select_option("status", "triaged")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("IssueReport", issue_id)
        assert updated["status"] == "triaged"

        story_tracker.mark_tested("ST-007", passed=True)

    def test_ST_008_engineer_starts_work_on_issue(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-008: Engineer changes IssueReport from triaged to in_progress.

        Preconditions:
            - IssueReport.status is 'triaged'

        Expected outcome:
            - IssueReport.status becomes 'in_progress'
        """
        app = as_engineer

        # Get references
        devices = demo_data["entities"].get("Device", [])
        testers = demo_data["entities"].get("Tester", [])

        if not devices or not testers:
            pytest.skip("Demo data required for this test")

        # Create a triaged issue
        issue = api_client.create(
            "IssueReport",
            {
                "device_id": devices[0]["id"],
                "reported_by_id": testers[0]["id"],
                "category": "mechanical",
                "severity": "low",
                "description": "Button feels sticky",
                "status": "triaged",
            },
        )
        issue_id = issue["id"]

        # Navigate to issue edit
        app.navigate_to_entity_edit("IssueReport", issue_id)
        app.wait_for_view("issue_report_edit")

        # Change status to in_progress
        app.select_option("status", "in_progress")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("IssueReport", issue_id)
        assert updated["status"] == "in_progress"

        story_tracker.mark_tested("ST-008", passed=True)

    def test_ST_009_engineer_fixes_issue(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-009: Engineer changes IssueReport from in_progress to fixed.

        Preconditions:
            - IssueReport.status is 'in_progress'

        Expected outcome:
            - IssueReport.status becomes 'fixed'

        Note: The invariant requires a resolution when marking as fixed.
        """
        app = as_engineer

        # Get references
        devices = demo_data["entities"].get("Device", [])
        testers = demo_data["entities"].get("Tester", [])

        if not devices or not testers:
            pytest.skip("Demo data required for this test")

        # Create an in_progress issue
        issue = api_client.create(
            "IssueReport",
            {
                "device_id": devices[0]["id"],
                "reported_by_id": testers[0]["id"],
                "category": "crash",
                "severity": "critical",
                "description": "App crashes on startup",
                "status": "in_progress",
            },
        )
        issue_id = issue["id"]

        # Navigate to issue edit
        app.navigate_to_entity_edit("IssueReport", issue_id)
        app.wait_for_view("issue_report_edit")

        # Change status to fixed AND provide resolution (required by invariant)
        app.select_option("status", "fixed")
        app.fill_field("resolution", "Fixed null pointer exception in startup handler")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("IssueReport", issue_id)
        assert updated["status"] == "fixed"
        assert updated["resolution"] is not None

        story_tracker.mark_tested("ST-009", passed=True)


# =============================================================================
# Test Session Story (ST-010)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestTestSessionStories:
    """Tests for TestSession entity user stories."""

    def test_ST_010_engineer_creates_test_session(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-010: Engineer creates a new Test Session.

        Preconditions:
            - Engineer has permission to create TestSession

        Expected outcome:
            - New TestSession is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        # Get references
        devices = demo_data["entities"].get("Device", [])
        testers = demo_data["entities"].get("Tester", [])

        if not devices or not testers:
            pytest.skip("Demo data required for this test")

        device_id = devices[0]["id"]
        tester_id = testers[0]["id"]

        # Navigate to test session creation form
        app.navigate_to_entity_create("TestSession")
        app.wait_for_view("test_session_create")

        # Fill required fields
        app.select_option("device_id", device_id)
        app.select_option("tester_id", tester_id)
        app.fill_field("duration_minutes", "45")
        app.select_option("environment", "outdoor")
        app.fill_field("temperature", "22")
        app.fill_field("notes", "Outdoor field test in park conditions")

        # Submit form
        app.click_save()

        # Verify success
        app.wait_for_navigation()

        story_tracker.mark_tested("ST-010", passed=True)


# =============================================================================
# Firmware Release Stories (ST-011 to ST-014)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestFirmwareReleaseStories:
    """Tests for FirmwareRelease entity user stories."""

    def test_ST_011_engineer_creates_firmware_release(
        self, as_engineer: FieldTestHubPage, story_tracker
    ):
        """ST-011: Engineer creates a new Firmware Release.

        Preconditions:
            - Engineer has permission to create FirmwareRelease

        Expected outcome:
            - New FirmwareRelease is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        # Navigate to firmware release creation form
        app.navigate_to_entity_create("FirmwareRelease")
        app.wait_for_view("firmware_release_create")

        # Fill required fields
        app.fill_field("version", "v2.0.0-beta")
        app.fill_field("release_date", "2025-01-15")
        app.fill_field("applies_to_batch", "BATCH-2025-001")

        # Submit form (will be created in draft status)
        app.click_save()

        # Verify success
        app.wait_for_navigation()

        story_tracker.mark_tested("ST-011", passed=True)

    def test_ST_012_engineer_releases_firmware(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-012: Engineer changes FirmwareRelease from draft to released.

        Preconditions:
            - FirmwareRelease.status is 'draft'

        Expected outcome:
            - FirmwareRelease.status becomes 'released'

        Note: Invariant requires release_notes when releasing.
        """
        app = as_engineer

        # Create a draft firmware release
        firmware = api_client.create(
            "FirmwareRelease",
            {
                "version": "v2.1.0",
                "release_date": "2025-02-01",
                "status": "draft",
                "release_notes": "Bug fixes and performance improvements",  # Required
            },
        )
        firmware_id = firmware["id"]

        # Navigate to firmware edit
        app.navigate_to_entity_edit("FirmwareRelease", firmware_id)
        app.wait_for_view("firmware_release_edit")

        # Change status to released
        app.select_option("status", "released")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("FirmwareRelease", firmware_id)
        assert updated["status"] == "released"

        story_tracker.mark_tested("ST-012", passed=True)

    def test_ST_013_engineer_deprecates_firmware(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-013: Engineer changes FirmwareRelease from released to deprecated.

        Preconditions:
            - FirmwareRelease.status is 'released'

        Expected outcome:
            - FirmwareRelease.status becomes 'deprecated'
        """
        app = as_engineer

        # Create a released firmware
        firmware = api_client.create(
            "FirmwareRelease",
            {
                "version": "v1.9.0",
                "release_date": "2024-12-01",
                "status": "released",
                "release_notes": "Legacy version",
            },
        )
        firmware_id = firmware["id"]

        # Navigate to firmware edit
        app.navigate_to_entity_edit("FirmwareRelease", firmware_id)
        app.wait_for_view("firmware_release_edit")

        # Change status to deprecated
        app.select_option("status", "deprecated")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("FirmwareRelease", firmware_id)
        assert updated["status"] == "deprecated"

        story_tracker.mark_tested("ST-013", passed=True)

    def test_ST_014_engineer_reverts_firmware_to_draft(
        self, as_engineer: FieldTestHubPage, api_client, story_tracker
    ):
        """ST-014: Engineer changes FirmwareRelease from deprecated to draft.

        Preconditions:
            - FirmwareRelease.status is 'deprecated'

        Expected outcome:
            - FirmwareRelease.status becomes 'draft'

        Note: This transition is engineer-only.
        """
        app = as_engineer

        # Create a deprecated firmware
        firmware = api_client.create(
            "FirmwareRelease",
            {
                "version": "v1.8.0",
                "release_date": "2024-11-01",
                "status": "deprecated",
                "release_notes": "Old version being revived",
            },
        )
        firmware_id = firmware["id"]

        # Navigate to firmware edit
        app.navigate_to_entity_edit("FirmwareRelease", firmware_id)
        app.wait_for_view("firmware_release_edit")

        # Change status back to draft
        app.select_option("status", "draft")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("FirmwareRelease", firmware_id)
        assert updated["status"] == "draft"

        story_tracker.mark_tested("ST-014", passed=True)


# =============================================================================
# Task Stories (ST-015 to ST-018)
# =============================================================================


@pytest.mark.story
@pytest.mark.engineer
class TestTaskStories:
    """Tests for Task entity user stories."""

    def test_ST_015_engineer_creates_task(
        self, as_engineer: FieldTestHubPage, demo_data, story_tracker
    ):
        """ST-015: Engineer creates a new Task.

        Preconditions:
            - Engineer has permission to create Task

        Expected outcome:
            - New Task is saved to database
            - Engineer sees confirmation message
        """
        app = as_engineer

        testers = demo_data["entities"].get("Tester", [])
        if not testers:
            pytest.skip("Demo data required for this test")

        tester_id = testers[0]["id"]

        # Navigate to task creation form
        app.navigate_to_entity_create("Task")
        app.wait_for_view("task_create")

        # Fill required fields
        app.select_option("type", "debugging")
        app.select_option("created_by_id", tester_id)
        app.fill_field("notes", "Investigate battery drain issue")

        # Submit form
        app.click_save()

        # Verify success
        app.wait_for_navigation()

        story_tracker.mark_tested("ST-015", passed=True)

    def test_ST_016_engineer_starts_task(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-016: Engineer changes Task from open to in_progress.

        Preconditions:
            - Task.status is 'open'

        Expected outcome:
            - Task.status becomes 'in_progress'

        Note: Invariant requires assigned_to when in_progress.
        """
        app = as_engineer

        testers = demo_data["entities"].get("Tester", [])
        if not testers:
            pytest.skip("Demo data required for this test")

        # Create an open task
        task = api_client.create(
            "Task",
            {
                "type": "firmware_update",
                "created_by_id": testers[0]["id"],
                "assigned_to_id": testers[1]["id"] if len(testers) > 1 else testers[0]["id"],
                "status": "open",
                "notes": "Prepare firmware update package",
            },
        )
        task_id = task["id"]

        # Navigate to task edit
        app.navigate_to_entity_edit("Task", task_id)
        app.wait_for_view("task_edit")

        # Change status to in_progress
        app.select_option("status", "in_progress")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("Task", task_id)
        assert updated["status"] == "in_progress"

        story_tracker.mark_tested("ST-016", passed=True)

    def test_ST_017_engineer_completes_task(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-017: Engineer changes Task from in_progress to completed.

        Preconditions:
            - Task.status is 'in_progress'

        Expected outcome:
            - Task.status becomes 'completed'
        """
        app = as_engineer

        testers = demo_data["entities"].get("Tester", [])
        if not testers:
            pytest.skip("Demo data required for this test")

        # Create an in_progress task
        task = api_client.create(
            "Task",
            {
                "type": "hardware_replacement",
                "created_by_id": testers[0]["id"],
                "assigned_to_id": testers[0]["id"],
                "status": "in_progress",
                "notes": "Replace faulty battery",
            },
        )
        task_id = task["id"]

        # Navigate to task edit
        app.navigate_to_entity_edit("Task", task_id)
        app.wait_for_view("task_edit")

        # Change status to completed
        app.select_option("status", "completed")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("Task", task_id)
        assert updated["status"] == "completed"

        story_tracker.mark_tested("ST-017", passed=True)

    def test_ST_018_engineer_reopens_task(
        self, as_engineer: FieldTestHubPage, api_client, demo_data, story_tracker
    ):
        """ST-018: Engineer changes Task from in_progress to open.

        Preconditions:
            - Task.status is 'in_progress'

        Expected outcome:
            - Task.status becomes 'open'
        """
        app = as_engineer

        testers = demo_data["entities"].get("Tester", [])
        if not testers:
            pytest.skip("Demo data required for this test")

        # Create an in_progress task
        task = api_client.create(
            "Task",
            {
                "type": "recall_request",
                "created_by_id": testers[0]["id"],
                "assigned_to_id": testers[0]["id"],
                "status": "in_progress",
                "notes": "Recall investigation - needs more info",
            },
        )
        task_id = task["id"]

        # Navigate to task edit
        app.navigate_to_entity_edit("Task", task_id)
        app.wait_for_view("task_edit")

        # Change status back to open
        app.select_option("status", "open")
        app.click_save()

        # Verify the transition
        app.wait_for_navigation()
        updated = api_client.get("Task", task_id)
        assert updated["status"] == "open"

        story_tracker.mark_tested("ST-018", passed=True)
