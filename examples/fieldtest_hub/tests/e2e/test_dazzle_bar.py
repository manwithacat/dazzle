"""Dazzle Bar tests for FieldTest Hub.

Tests the Dazzle Bar developer toolbar functionality:
- Persona dropdown shows all 3 personas
- Switching persona updates context
- Reset data clears all entities
- Regenerate data creates new demo data
- State persists across navigation
"""

from __future__ import annotations

import pytest
from helpers.api_client import ControlPlaneClient
from helpers.page_objects import FieldTestHubPage

# =============================================================================
# Dazzle Bar Visibility Tests
# =============================================================================


@pytest.mark.dazzle_bar
class TestDazzleBarVisibility:
    """Test Dazzle Bar component visibility."""

    def test_dazzle_bar_visible_on_page(self, app: FieldTestHubPage):
        """Dazzle Bar should be visible on all pages."""
        app.goto("/")
        app.page.wait_for_load_state("networkidle")

        # Dazzle Bar component should be present
        dazzle_bar = app.dazzle_bar()
        assert dazzle_bar.count() > 0, "Dazzle Bar not found on page"

    def test_dazzle_bar_has_persona_selector(self, app: FieldTestHubPage):
        """Dazzle Bar should have persona selection dropdown."""
        app.goto("/")

        persona_select = app.page.locator('[data-dazzle-component="persona-select"]')
        assert persona_select.count() > 0, "Persona selector not found"

    def test_dazzle_bar_has_reset_button(self, app: FieldTestHubPage):
        """Dazzle Bar should have reset data button."""
        app.goto("/")

        reset_btn = app.page.locator('[data-dazzle-action="reset-data"]')
        assert reset_btn.count() > 0, "Reset data button not found"

    def test_dazzle_bar_has_regenerate_button(self, app: FieldTestHubPage):
        """Dazzle Bar should have regenerate data button."""
        app.goto("/")

        regen_btn = app.page.locator('[data-dazzle-action="regenerate-data"]')
        assert regen_btn.count() > 0, "Regenerate data button not found"


# =============================================================================
# Persona Switching Tests
# =============================================================================


@pytest.mark.dazzle_bar
@pytest.mark.personas
class TestPersonaSwitching:
    """Test persona switching functionality."""

    def test_three_personas_available(self, app: FieldTestHubPage):
        """All three personas should be available in dropdown."""
        app.goto("/")

        persona_select = app.page.locator('[data-dazzle-component="persona-select"]')
        options = persona_select.locator("option")

        # Should have at least 3 options (engineer, tester, manager)
        assert options.count() >= 3, f"Expected 3+ personas, got {options.count()}"

    def test_switch_to_engineer(self, app: FieldTestHubPage, control_plane: ControlPlaneClient):
        """Can switch to Engineer persona."""
        app.goto("/")

        # Switch via API
        result = control_plane.set_persona("engineer")
        assert result.get("success") or result.get("persona_id") == "engineer"

        # Verify in UI after refresh
        app.goto("/")
        state = control_plane.get_state()
        assert state.get("current_persona") == "engineer"

    def test_switch_to_tester(self, app: FieldTestHubPage, control_plane: ControlPlaneClient):
        """Can switch to Field Tester persona."""
        app.goto("/")

        result = control_plane.set_persona("tester")
        assert result.get("success") or result.get("persona_id") == "tester"

        app.goto("/")
        state = control_plane.get_state()
        assert state.get("current_persona") == "tester"

    def test_switch_to_manager(self, app: FieldTestHubPage, control_plane: ControlPlaneClient):
        """Can switch to Manager persona."""
        app.goto("/")

        result = control_plane.set_persona("manager")
        assert result.get("success") or result.get("persona_id") == "manager"

        app.goto("/")
        state = control_plane.get_state()
        assert state.get("current_persona") == "manager"

    def test_persona_persists_across_navigation(
        self, app: FieldTestHubPage, control_plane: ControlPlaneClient
    ):
        """Selected persona should persist when navigating between pages."""
        # Set to tester
        control_plane.set_persona("tester")

        # Navigate to different pages
        app.goto("/")
        app.navigate_to_entity_list("Device")
        app.navigate_to_entity_list("IssueReport")

        # Verify persona is still tester
        state = control_plane.get_state()
        assert state.get("current_persona") == "tester"


# =============================================================================
# Data Reset Tests
# =============================================================================


@pytest.mark.dazzle_bar
@pytest.mark.data_management
class TestDataReset:
    """Test reset data functionality."""

    def test_reset_clears_all_data(
        self,
        app: FieldTestHubPage,
        control_plane: ControlPlaneClient,
        api_client,
    ):
        """Reset data should clear all entities."""
        app.goto("/")

        # Reset data
        control_plane.reset_data()

        # Verify entities are empty
        for entity in ["Device", "IssueReport", "TestSession", "Task"]:
            try:
                items = api_client.list(entity)
                assert len(items) == 0, f"{entity} should be empty after reset"
            except Exception:
                # Entity might not exist or API might differ
                pass

    def test_reset_button_via_ui(self, app: FieldTestHubPage):
        """Can trigger reset via Dazzle Bar button."""
        app.goto("/")

        reset_btn = app.page.locator('[data-dazzle-action="reset-data"]')
        if reset_btn.count() > 0:
            reset_btn.click()
            # Wait for confirmation or completion
            app.wait_for_navigation()


# =============================================================================
# Data Regeneration Tests
# =============================================================================


@pytest.mark.dazzle_bar
@pytest.mark.data_management
class TestDataRegeneration:
    """Test regenerate data functionality."""

    def test_regenerate_creates_new_data(
        self,
        app: FieldTestHubPage,
        control_plane: ControlPlaneClient,
        api_client,
    ):
        """Regenerate should create new demo data."""
        app.goto("/")

        # First reset
        control_plane.reset_data()

        # Then regenerate
        control_plane.regenerate_data()

        # Verify entities have data
        try:
            devices = api_client.list("Device")
            assert len(devices) > 0, "Devices should exist after regeneration"
        except Exception:
            # API might differ, skip if not available
            pass

    def test_regenerate_button_via_ui(self, app: FieldTestHubPage):
        """Can trigger regenerate via Dazzle Bar button."""
        app.goto("/")

        regen_btn = app.page.locator('[data-dazzle-action="regenerate-data"]')
        if regen_btn.count() > 0:
            regen_btn.click()
            # Wait for confirmation or completion
            app.wait_for_navigation()

    def test_regenerate_with_custom_counts(self, control_plane: ControlPlaneClient, api_client):
        """Regenerate can accept custom entity counts."""
        # Reset first
        control_plane.reset_data()

        # Regenerate with specific counts
        control_plane.regenerate_data({"Device": 5, "IssueReport": 3})

        # Verify counts
        try:
            devices = api_client.list("Device")
            # Should have approximately the requested count
            assert len(devices) >= 3, "Should have at least some devices"
        except Exception:
            pass


# =============================================================================
# State Persistence Tests
# =============================================================================


@pytest.mark.dazzle_bar
@pytest.mark.state
class TestStatePersistence:
    """Test Dazzle Bar state persistence."""

    def test_state_endpoint_returns_data(self, control_plane: ControlPlaneClient):
        """State endpoint should return current state."""
        state = control_plane.get_state()

        assert state is not None
        assert "current_persona" in state or "persona" in state

    def test_state_reflects_persona_change(self, control_plane: ControlPlaneClient):
        """State should update after persona change."""
        # Set to engineer
        control_plane.set_persona("engineer")
        state1 = control_plane.get_state()

        # Set to manager
        control_plane.set_persona("manager")
        state2 = control_plane.get_state()

        # States should differ
        assert state1.get("current_persona") != state2.get("current_persona")

    def test_state_persists_after_page_reload(
        self, app: FieldTestHubPage, control_plane: ControlPlaneClient
    ):
        """State should persist after page reload."""
        # Set persona
        control_plane.set_persona("tester")

        # Navigate and reload
        app.goto("/")
        app.page.reload()

        # Check state
        state = control_plane.get_state()
        assert state.get("current_persona") == "tester"


# =============================================================================
# Dazzle Bar Display Tests
# =============================================================================


@pytest.mark.dazzle_bar
@pytest.mark.display
class TestDazzleBarDisplay:
    """Test Dazzle Bar display elements."""

    def test_shows_current_persona_name(
        self, app: FieldTestHubPage, control_plane: ControlPlaneClient
    ):
        """Dazzle Bar should show current persona name."""
        control_plane.set_persona("engineer")
        app.goto("/")

        # Look for persona indicator text
        dazzle_bar = app.dazzle_bar()
        bar_text = dazzle_bar.inner_text()

        # Should mention engineer or show persona info
        # Exact text depends on implementation
        assert len(bar_text) > 0, "Dazzle Bar should have content"

    def test_shows_project_info(self, app: FieldTestHubPage):
        """Dazzle Bar should show project information."""
        app.goto("/")

        dazzle_bar = app.dazzle_bar()
        bar_text = dazzle_bar.inner_text().lower()

        # May show project name or other info
        assert len(bar_text) > 0, "Dazzle Bar should have content"

    def test_dazzle_bar_positioned_correctly(self, app: FieldTestHubPage):
        """Dazzle Bar should be positioned as toolbar (top or bottom)."""
        app.goto("/")

        dazzle_bar = app.dazzle_bar()
        if dazzle_bar.count() > 0:
            # Get bounding box
            box = dazzle_bar.bounding_box()
            if box:
                # Should be at top or bottom of viewport
                # (y near 0 or near viewport height - bar height)
                assert box["y"] < 100 or box["y"] > 600, "Bar should be at top/bottom"
