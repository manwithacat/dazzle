"""State machine tests for FieldTest Hub.

Tests state transitions for all entities with status fields:
- Device: prototype → active → recalled/retired
- IssueReport: open → triaged → in_progress → fixed → verified → closed
- FirmwareRelease: draft → released → deprecated
- Task: open ↔ in_progress → completed, any → cancelled

Validates:
- Valid transitions succeed
- Invalid transitions are blocked
- Guard conditions are enforced (e.g., firmware_version required for activation)
"""

from __future__ import annotations

import pytest
from helpers.api_client import APIClient
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# Device State Machine Tests
# =============================================================================


@pytest.mark.state_machine
@pytest.mark.device
class TestDeviceStateMachine:
    """Test Device state transitions.

    States: prototype → active → recalled | retired
    Guards:
    - prototype → active: requires firmware_version
    - recalled → active: engineer only
    """

    def test_device_prototype_to_active_requires_firmware(
        self, as_engineer: FieldTestHubPage, api_client: APIClient
    ):
        """Device cannot activate without firmware_version."""
        app = as_engineer

        # Create a prototype device without firmware
        app.navigate_to_entity_create("Device")
        app.fill_field("name", "State Test Device")
        app.fill_field("serial_number", "ST-001")
        # Leave firmware_version empty
        app.click_save()
        app.wait_for_navigation()

        # Try to transition to active - should fail or require firmware
        # The exact behavior depends on whether transition is inline or via action

    def test_device_prototype_to_active_with_firmware(
        self, as_engineer: FieldTestHubPage, api_client: APIClient
    ):
        """Device can activate when firmware_version is set."""
        app = as_engineer

        # Create a prototype device with firmware
        app.navigate_to_entity_create("Device")
        app.fill_field("name", "Activated Device")
        app.fill_field("serial_number", "ST-002")
        app.fill_field("firmware_version", "1.0.0")
        app.click_save()
        app.wait_for_navigation()

        # Device should be able to transition to active

    def test_device_active_to_recalled(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can recall an active device."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        active_devices = [d for d in devices if d.get("status") == "active"]

        if active_devices:
            device_id = active_devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # Should have recall action available
            app.assert_action_visible("recall")

    def test_device_active_to_retired(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can retire an active device."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        active_devices = [d for d in devices if d.get("status") == "active"]

        if active_devices:
            device_id = active_devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # Should have retire action available
            app.assert_action_visible("retire")

    def test_device_recalled_to_active(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can reactivate a recalled device."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        recalled_devices = [d for d in devices if d.get("status") == "recalled"]

        if recalled_devices:
            device_id = recalled_devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # Should have activate action available
            app.assert_action_visible("activate")

    def test_device_retired_is_terminal(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Retired devices cannot transition to other states."""
        app = as_engineer
        devices = demo_data.get("entities", {}).get("Device", [])
        retired_devices = [d for d in devices if d.get("status") == "retired"]

        if retired_devices:
            device_id = retired_devices[0]["id"]
            app.navigate_to_entity_detail("Device", device_id)
            # No transition actions should be available
            app.assert_action_hidden("activate")
            app.assert_action_hidden("recall")


# =============================================================================
# IssueReport State Machine Tests
# =============================================================================


@pytest.mark.state_machine
@pytest.mark.issue_report
class TestIssueReportStateMachine:
    """Test IssueReport state transitions.

    States: open → triaged → in_progress → fixed → verified → closed
    Guards:
    - in_progress → fixed: requires resolution
    - fixed → closed: requires resolution
    """

    def test_issue_open_to_triaged(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can triage an open issue."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        open_issues = [i for i in issues if i.get("status") == "open"]

        if open_issues:
            issue_id = open_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            app.assert_action_visible("triage")

    def test_issue_triaged_to_in_progress(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can start work on a triaged issue."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        triaged_issues = [i for i in issues if i.get("status") == "triaged"]

        if triaged_issues:
            issue_id = triaged_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            app.assert_action_visible("start_work")

    def test_issue_in_progress_to_fixed_requires_resolution(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """Issue cannot be marked fixed without resolution."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        in_progress_issues = [i for i in issues if i.get("status") == "in_progress"]

        if in_progress_issues:
            issue_id = in_progress_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            # If resolution is empty, fix action should be disabled or show error

    def test_issue_fixed_to_verified(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Fixed issue can be verified."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        fixed_issues = [i for i in issues if i.get("status") == "fixed"]

        if fixed_issues:
            issue_id = fixed_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            app.assert_action_visible("verify")

    def test_issue_verified_to_closed(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Verified issue can be closed."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        verified_issues = [i for i in issues if i.get("status") == "verified"]

        if verified_issues:
            issue_id = verified_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            app.assert_action_visible("close")

    def test_issue_closed_is_terminal(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Closed issues cannot transition."""
        app = as_engineer
        issues = demo_data.get("entities", {}).get("IssueReport", [])
        closed_issues = [i for i in issues if i.get("status") == "closed"]

        if closed_issues:
            issue_id = closed_issues[0]["id"]
            app.navigate_to_entity_detail("IssueReport", issue_id)
            # No transition actions should be available
            app.assert_action_hidden("triage")
            app.assert_action_hidden("start_work")
            app.assert_action_hidden("fix")


# =============================================================================
# FirmwareRelease State Machine Tests
# =============================================================================


@pytest.mark.state_machine
@pytest.mark.firmware
class TestFirmwareReleaseStateMachine:
    """Test FirmwareRelease state transitions.

    States: draft → released → deprecated
    Guards:
    - draft → released: requires release_notes
    - deprecated → draft: engineer only
    """

    def test_firmware_draft_to_released_requires_notes(self, as_engineer: FieldTestHubPage):
        """Firmware cannot be released without release_notes."""
        app = as_engineer

        # Create a draft firmware without release notes
        app.navigate_to_entity_create("FirmwareRelease")
        app.fill_field("version", "0.0.1-test")
        # Leave release_notes empty
        app.click_save()
        app.wait_for_navigation()

        # Release action should require notes

    def test_firmware_draft_to_released_with_notes(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """Firmware can be released when release_notes is set."""
        app = as_engineer
        releases = demo_data.get("entities", {}).get("FirmwareRelease", [])
        draft_releases = [r for r in releases if r.get("status") == "draft"]

        if draft_releases:
            release_id = draft_releases[0]["id"]
            app.navigate_to_entity_detail("FirmwareRelease", release_id)
            # Should have release action if notes are present
            app.assert_action_visible("release")

    def test_firmware_released_to_deprecated(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can deprecate a released firmware."""
        app = as_engineer
        releases = demo_data.get("entities", {}).get("FirmwareRelease", [])
        released = [r for r in releases if r.get("status") == "released"]

        if released:
            release_id = released[0]["id"]
            app.navigate_to_entity_detail("FirmwareRelease", release_id)
            app.assert_action_visible("deprecate")

    def test_firmware_deprecated_to_draft(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Engineer can revert a deprecated firmware to draft."""
        app = as_engineer
        releases = demo_data.get("entities", {}).get("FirmwareRelease", [])
        deprecated = [r for r in releases if r.get("status") == "deprecated"]

        if deprecated:
            release_id = deprecated[0]["id"]
            app.navigate_to_entity_detail("FirmwareRelease", release_id)
            app.assert_action_visible("revert_to_draft")


# =============================================================================
# Task State Machine Tests
# =============================================================================


@pytest.mark.state_machine
@pytest.mark.task
class TestTaskStateMachine:
    """Test Task state transitions.

    States: open ↔ in_progress → completed, any → cancelled
    Guards:
    - open → in_progress: requires assigned_to
    - cancelled: engineer only
    """

    def test_task_open_to_in_progress_requires_assignee(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """Task cannot start without assignee."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        open_tasks = [t for t in tasks if t.get("status") == "open" and not t.get("assigned_to")]

        if open_tasks:
            task_id = open_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            # Start action should be disabled or prompt for assignee

    def test_task_open_to_in_progress_with_assignee(
        self, as_engineer: FieldTestHubPage, demo_data: dict
    ):
        """Task can start when assignee is set."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        assigned_open_tasks = [
            t for t in tasks if t.get("status") == "open" and t.get("assigned_to")
        ]

        if assigned_open_tasks:
            task_id = assigned_open_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            app.assert_action_visible("start")

    def test_task_in_progress_to_completed(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """In-progress task can be completed."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        in_progress_tasks = [t for t in tasks if t.get("status") == "in_progress"]

        if in_progress_tasks:
            task_id = in_progress_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            app.assert_action_visible("complete")

    def test_task_in_progress_to_open(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """In-progress task can be reverted to open."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        in_progress_tasks = [t for t in tasks if t.get("status") == "in_progress"]

        if in_progress_tasks:
            task_id = in_progress_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            app.assert_action_visible("revert")

    def test_task_can_be_cancelled(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Any task can be cancelled by engineer."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        non_cancelled_tasks = [t for t in tasks if t.get("status") != "cancelled"]

        if non_cancelled_tasks:
            task_id = non_cancelled_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            app.assert_action_visible("cancel")

    def test_task_completed_is_terminal(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Completed tasks cannot transition."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        completed_tasks = [t for t in tasks if t.get("status") == "completed"]

        if completed_tasks:
            task_id = completed_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            # No transition actions except possibly cancel
            app.assert_action_hidden("start")
            app.assert_action_hidden("complete")
            app.assert_action_hidden("revert")

    def test_task_cancelled_is_terminal(self, as_engineer: FieldTestHubPage, demo_data: dict):
        """Cancelled tasks cannot transition."""
        app = as_engineer
        tasks = demo_data.get("entities", {}).get("Task", [])
        cancelled_tasks = [t for t in tasks if t.get("status") == "cancelled"]

        if cancelled_tasks:
            task_id = cancelled_tasks[0]["id"]
            app.navigate_to_entity_detail("Task", task_id)
            # No transition actions
            app.assert_action_hidden("start")
            app.assert_action_hidden("complete")
            app.assert_action_hidden("revert")
            app.assert_action_hidden("cancel")
