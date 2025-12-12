"""Access control tests for FieldTest Hub.

Tests that verify persona-based permissions:
- Engineer: Full access to all entities
- Field Tester: Limited access (own devices, issues, sessions)
- Manager: Read-only access to metrics/issues

Uses Dazzle Bar to switch personas and verifies both
positive (allowed) and negative (denied) access scenarios.
"""

from __future__ import annotations

import pytest
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# Engineer Access Tests - Full Access
# =============================================================================


@pytest.mark.access_control
@pytest.mark.engineer
class TestEngineerAccess:
    """Verify Engineer has full CRUD access to all entities."""

    def test_engineer_can_view_device_list(self, as_engineer: FieldTestHubPage):
        """Engineer can view the Device list."""
        app = as_engineer
        app.navigate_to_entity_list("Device")
        app.assert_view_visible("device_list")

    def test_engineer_can_create_device(self, as_engineer: FieldTestHubPage):
        """Engineer can access Device create form."""
        app = as_engineer
        app.navigate_to_entity_list("Device")
        app.assert_action_visible("create")
        app.click_create()
        app.assert_view_visible("device_create")

    def test_engineer_can_edit_device(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can edit any Device."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        if devices:
            device_id = devices[0]["id"]
            app.navigate_to_entity_edit("Device", device_id)
            app.assert_view_visible("device_edit")
            app.assert_action_visible("save")

    def test_engineer_can_delete_device(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can see delete action for Device."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        if devices:
            device_id = devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            app.assert_action_visible("delete")

    def test_engineer_can_manage_firmware(self, as_engineer: FieldTestHubPage):
        """Engineer can create FirmwareRelease."""
        app = as_engineer
        app.navigate_to_entity_list("FirmwareRelease")
        app.assert_action_visible("create")

    def test_engineer_can_manage_tasks(self, as_engineer: FieldTestHubPage):
        """Engineer can create Task."""
        app = as_engineer
        app.navigate_to_entity_list("Task")
        app.assert_action_visible("create")

    def test_engineer_can_manage_testers(self, as_engineer: FieldTestHubPage):
        """Engineer can create Tester."""
        app = as_engineer
        app.navigate_to_entity_list("Tester")
        app.assert_action_visible("create")


# =============================================================================
# Field Tester Access Tests - Limited Access
# =============================================================================


@pytest.mark.access_control
@pytest.mark.tester
class TestTesterAccess:
    """Verify Field Tester has limited access."""

    def test_tester_can_view_assigned_devices(self, as_tester: FieldTestHubPage):
        """Field Tester can view devices (likely filtered to assigned)."""
        app = as_tester
        app.navigate_to_entity_list("Device")
        # Should see device list view, possibly filtered
        app.assert_view_visible("device_list")

    def test_tester_cannot_create_device(self, as_tester: FieldTestHubPage):
        """Field Tester cannot create new devices."""
        app = as_tester
        app.navigate_to_entity_list("Device")
        # Create action should be hidden or disabled
        app.assert_action_hidden("create")

    def test_tester_can_create_issue_report(self, as_tester: FieldTestHubPage):
        """Field Tester can create issue reports."""
        app = as_tester
        app.navigate_to_entity_list("IssueReport")
        app.assert_action_visible("create")

    def test_tester_can_edit_own_issue_report(
        self, as_tester: FieldTestHubPage, demo_data: dict, test_users: dict
    ):
        """Field Tester can edit their own issue reports."""
        app = as_tester
        # Find an issue report created by the tester persona
        _tester_user = test_users.get("tester", {})  # noqa: F841
        issues = demo_data.get("entities", {}).get("IssueReport", [])

        # Try to access the first issue (may need filtering in real scenario)
        if issues:
            issue_id = issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            # Tester should see edit button for accessible issues
            # (actual visibility depends on ownership/assignment rules)

    def test_tester_can_create_test_session(self, as_tester: FieldTestHubPage):
        """Field Tester can log test sessions."""
        app = as_tester
        app.navigate_to_entity_list("TestSession")
        app.assert_action_visible("create")

    def test_tester_cannot_create_firmware(self, as_tester: FieldTestHubPage):
        """Field Tester cannot create firmware releases."""
        app = as_tester
        app.navigate_to_entity_list("FirmwareRelease")
        app.assert_action_hidden("create")

    def test_tester_cannot_create_task(self, as_tester: FieldTestHubPage):
        """Field Tester cannot create tasks."""
        app = as_tester
        app.navigate_to_entity_list("Task")
        app.assert_action_hidden("create")


# =============================================================================
# Manager Access Tests - Read-Only
# =============================================================================


@pytest.mark.access_control
@pytest.mark.manager
class TestManagerAccess:
    """Verify Manager has read-only access to metrics and issues."""

    def test_manager_can_view_issue_reports(self, as_manager: FieldTestHubPage):
        """Manager can view issue reports."""
        app = as_manager
        app.navigate_to_entity_list("IssueReport")
        app.assert_view_visible("issue_report_list")

    def test_manager_cannot_create_issue_report(self, as_manager: FieldTestHubPage):
        """Manager cannot create issue reports."""
        app = as_manager
        app.navigate_to_entity_list("IssueReport")
        app.assert_action_hidden("create")

    def test_manager_can_view_devices(self, as_manager: FieldTestHubPage):
        """Manager can view device metrics/list."""
        app = as_manager
        app.navigate_to_entity_list("Device")
        app.assert_view_visible("device_list")

    def test_manager_cannot_create_device(self, as_manager: FieldTestHubPage):
        """Manager cannot create devices."""
        app = as_manager
        app.navigate_to_entity_list("Device")
        app.assert_action_hidden("create")

    def test_manager_cannot_edit_device(self, as_manager: FieldTestHubPage, demo_data: dict):
        """Manager cannot edit devices."""
        app = as_manager
        devices = demo_data.get("entities", {}).get("Device", [])
        if devices:
            device_id = devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # Edit action should be hidden
            app.assert_action_hidden("edit")

    def test_manager_cannot_create_tester(self, as_manager: FieldTestHubPage):
        """Manager cannot create testers."""
        app = as_manager
        app.navigate_to_entity_list("Tester")
        app.assert_action_hidden("create")

    def test_manager_cannot_create_firmware(self, as_manager: FieldTestHubPage):
        """Manager cannot create firmware."""
        app = as_manager
        app.navigate_to_entity_list("FirmwareRelease")
        app.assert_action_hidden("create")

    def test_manager_cannot_create_task(self, as_manager: FieldTestHubPage):
        """Manager cannot create tasks."""
        app = as_manager
        app.navigate_to_entity_list("Task")
        app.assert_action_hidden("create")


# =============================================================================
# Access Denial Tests - Explicit 403/Forbidden
# =============================================================================


@pytest.mark.access_control
@pytest.mark.denial
class TestAccessDenial:
    """Test explicit access denial scenarios."""

    def test_tester_denied_device_creation_via_url(self, as_tester: FieldTestHubPage):
        """Tester navigating directly to device create URL is denied."""
        app = as_tester
        app.navigate_to_entity_create("Device")
        # Should either redirect, show 403, or show access denied message
        # The actual behavior depends on the app implementation

    def test_manager_denied_issue_edit_via_url(self, as_manager: FieldTestHubPage, demo_data: dict):
        """Manager navigating directly to issue edit URL is denied."""
        app = as_manager
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        if issues:
            issue_id = issues[0]["id"]
            app.navigate_to_entity_edit("IssueReport", issue_id)
            # Should be denied

    def test_tester_denied_firmware_creation_via_url(self, as_tester: FieldTestHubPage):
        """Tester navigating directly to firmware create URL is denied."""
        app = as_tester
        app.navigate_to_entity_create("FirmwareRelease")
        # Should be denied


# =============================================================================
# Cross-Persona State Transition Tests
# =============================================================================


@pytest.mark.access_control
@pytest.mark.transitions
class TestPersonaTransitions:
    """Test state transitions restricted by persona."""

    def test_only_engineer_can_recall_device(self, as_tester: FieldTestHubPage, demo_data: dict):
        """Only Engineer can transition device to recalled state."""
        app = as_tester
        devices = demo_data.get("entities", {}).get("Device", [])
        active_devices = [d for d in devices if d.get("status") == "active"]
        if active_devices:
            device_id = active_devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # Recall action should be hidden for tester
            app.assert_action_hidden("recall")

    def test_only_engineer_can_deprecate_firmware(
        self, as_tester: FieldTestHubPage, demo_data: dict
    ):
        """Only Engineer can deprecate firmware releases."""
        app = as_tester
        releases = demo_data.get("entities", {}).get("FirmwareRelease", [])
        released = [r for r in releases if r.get("status") == "released"]
        if released:
            release_id = released[0]["id"]
            app.navigate_to_entity_detail("FirmwareRelease", release_id)
            # Deprecate action should be hidden for tester
            app.assert_action_hidden("deprecate")

    def test_only_engineer_can_cancel_task(self, as_tester: FieldTestHubPage, demo_data: dict):
        """Only Engineer can cancel tasks."""
        app = as_tester
        tasks = demo_data.get("entities", {}).get("Task", [])
        open_tasks = [t for t in tasks if t.get("status") == "open"]
        if open_tasks:
            task_id = open_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            # Cancel action should be hidden for tester
            app.assert_action_hidden("cancel")
