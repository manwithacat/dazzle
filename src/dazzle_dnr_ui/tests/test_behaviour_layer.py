"""
Tests for the Behaviour Layer in DNR-UI runtime.

Tests signals, state management, actions, and effects.
"""

import json
import pytest

from dazzle_dnr_ui.specs import (
    UISpec,
    ComponentSpec,
    WorkspaceSpec,
    SingleColumnLayout,
    RouteSpec,
)
from dazzle_dnr_ui.specs.state import (
    StateSpec,
    StateScope,
    LiteralBinding,
    StateBinding,
    WorkspaceStateBinding,
)
from dazzle_dnr_ui.specs.actions import (
    ActionSpec,
    TransitionSpec,
    PatchSpec,
    PatchOp,
    FetchEffect,
    NavigateEffect,
    ToastEffect,
    LogEffect,
)
from dazzle_dnr_ui.runtime.js_generator import JSGenerator


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ui_spec_with_state() -> UISpec:
    """Create a UISpec with state declarations."""
    return UISpec(
        name="test_app",
        version="1.0.0",
        workspaces=[
            WorkspaceSpec(
                name="main",
                title="Main",
                layout=SingleColumnLayout(main="TaskList"),
                routes=[RouteSpec(path="/", component="TaskList")],
                state=[
                    StateSpec(
                        name="tasks",
                        scope=StateScope.WORKSPACE,
                        initial=[],
                        description="List of tasks",
                    ),
                    StateSpec(
                        name="selectedTask",
                        scope=StateScope.WORKSPACE,
                        initial=None,
                        description="Currently selected task",
                    ),
                    StateSpec(
                        name="isLoading",
                        scope=StateScope.WORKSPACE,
                        initial=False,
                        description="Loading state",
                    ),
                    StateSpec(
                        name="filter",
                        scope=StateScope.WORKSPACE,
                        initial="all",
                        persistent=True,
                        description="Task filter",
                    ),
                ],
            ),
        ],
        components=[
            ComponentSpec(
                name="TaskList",
                category="custom",
                description="Task list component",
            ),
        ],
    )


@pytest.fixture
def ui_spec_with_actions() -> UISpec:
    """Create a UISpec with action definitions."""
    return UISpec(
        name="test_app",
        version="1.0.0",
        workspaces=[
            WorkspaceSpec(
                name="main",
                title="Main",
                layout=SingleColumnLayout(main="TaskList"),
                routes=[RouteSpec(path="/", component="TaskList")],
            ),
        ],
        components=[
            ComponentSpec(
                name="TaskList",
                category="custom",
                description="Task list component",
                actions=[
                    ActionSpec(
                        name="selectTask",
                        description="Select a task",
                        inputs={"task_id": "uuid"},
                        transitions=[
                            TransitionSpec(
                                target_state="workspace.selectedTask",
                                update=PatchSpec(
                                    op=PatchOp.SET,
                                    path="selectedTask",
                                    value=None,
                                ),
                            ),
                        ],
                    ),
                    ActionSpec(
                        name="loadTasks",
                        description="Load tasks from API",
                        effect=FetchEffect(
                            backend_service="task_service",
                            on_success="handleTasksLoaded",
                            on_error="handleError",
                        ),
                    ),
                    ActionSpec(
                        name="createTask",
                        description="Create a new task",
                        inputs={"title": "str", "status": "str"},
                        effect=FetchEffect(
                            backend_service="task_service",
                            on_success="handleTaskCreated",
                        ),
                    ),
                    ActionSpec(
                        name="goToDetail",
                        description="Navigate to task detail",
                        effect=NavigateEffect(
                            route="/tasks/:id",
                            params={"id": StateBinding(path="selectedTask.id")},
                        ),
                    ),
                    ActionSpec(
                        name="showSuccess",
                        description="Show success toast",
                        effect=ToastEffect(
                            message=LiteralBinding(value="Operation successful!"),
                            variant="success",
                            duration=3000,
                        ),
                    ),
                    ActionSpec(
                        name="logAction",
                        description="Log an action",
                        effect=LogEffect(
                            message=LiteralBinding(value="Action executed"),
                            level="info",
                        ),
                    ),
                ],
            ),
        ],
    )


# =============================================================================
# State Management Tests
# =============================================================================


class TestStateManagement:
    """Test state management in generated runtime."""

    def test_state_stores_in_runtime(self, ui_spec_with_state: UISpec):
        """Test that runtime includes all state stores."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "stateStores" in runtime
        assert "local: new Map()" in runtime
        assert "workspace: new Map()" in runtime
        assert "app: new Map()" in runtime
        assert "session: new Map()" in runtime

    def test_state_functions_in_runtime(self, ui_spec_with_state: UISpec):
        """Test that runtime includes state management functions."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function getState(scope, path)" in runtime
        assert "function setState(scope, path, value)" in runtime
        assert "function updateState(scope, path, updater)" in runtime
        assert "function registerState(scope, path, initial" in runtime

    def test_global_loading_state(self, ui_spec_with_state: UISpec):
        """Test global loading state exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "globalLoading" in runtime
        assert "setGlobalLoading" in runtime

    def test_global_error_state(self, ui_spec_with_state: UISpec):
        """Test global error state exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "globalError" in runtime
        assert "setGlobalError" in runtime

    def test_notifications_state(self, ui_spec_with_state: UISpec):
        """Test notifications state exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "notifications" in runtime
        assert "setNotifications" in runtime

    def test_state_in_spec_json(self, ui_spec_with_state: UISpec):
        """Test that state is included in spec JSON."""
        generator = JSGenerator(ui_spec_with_state)
        spec_json = generator.generate_spec_json()
        spec = json.loads(spec_json)

        workspace = spec["workspaces"][0]
        assert "state" in workspace
        assert len(workspace["state"]) == 4

        # Check tasks state
        tasks_state = next(s for s in workspace["state"] if s["name"] == "tasks")
        assert tasks_state["scope"] == "workspace"
        assert tasks_state["initial"] == []

        # Check filter state with persistence
        filter_state = next(s for s in workspace["state"] if s["name"] == "filter")
        assert filter_state["persistent"] is True


# =============================================================================
# Signals Tests
# =============================================================================


class TestSignals:
    """Test signals-based reactivity in runtime."""

    def test_create_signal_function(self, ui_spec_with_state: UISpec):
        """Test createSignal function exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function createSignal(initialValue, options = {})" in runtime

    def test_create_effect_function(self, ui_spec_with_state: UISpec):
        """Test createEffect function exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function createEffect(fn, options = {})" in runtime

    def test_create_memo_function(self, ui_spec_with_state: UISpec):
        """Test createMemo function exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function createMemo(fn, options = {})" in runtime

    def test_create_resource_function(self, ui_spec_with_state: UISpec):
        """Test createResource function for async data."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function createResource(fetcher, options = {})" in runtime
        assert "data, loading, error, refetch" in runtime

    def test_batch_function(self, ui_spec_with_state: UISpec):
        """Test batch function for grouping updates."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function batch(fn)" in runtime
        assert "batchDepth" in runtime
        assert "pendingEffects" in runtime

    def test_signal_persistence(self, ui_spec_with_state: UISpec):
        """Test signal persistence option."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "localStorage.getItem" in runtime
        assert "localStorage.setItem" in runtime
        assert "persistent" in runtime


# =============================================================================
# Actions Tests
# =============================================================================


class TestActions:
    """Test action system in runtime."""

    def test_action_registry(self, ui_spec_with_actions: UISpec):
        """Test action registry exists."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "actionRegistry" in runtime
        assert "function registerAction(name, handler)" in runtime
        assert "function dispatch(actionName, payload = {})" in runtime

    def test_execute_action_function(self, ui_spec_with_actions: UISpec):
        """Test executeAction function."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "async function executeAction(action, context)" in runtime

    def test_built_in_filter_action(self, ui_spec_with_actions: UISpec):
        """Test built-in filter action."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "registerAction('filter'" in runtime
        assert "items.filter(predicate)" in runtime

    def test_built_in_sort_action(self, ui_spec_with_actions: UISpec):
        """Test built-in sort action."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "registerAction('sort'" in runtime
        assert "direction === 'desc'" in runtime

    def test_built_in_select_action(self, ui_spec_with_actions: UISpec):
        """Test built-in select action."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "registerAction('select'" in runtime

    def test_built_in_toggle_action(self, ui_spec_with_actions: UISpec):
        """Test built-in toggle action."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "registerAction('toggle'" in runtime
        assert "current => !current" in runtime

    def test_built_in_reset_action(self, ui_spec_with_actions: UISpec):
        """Test built-in reset action."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "registerAction('reset'" in runtime

    def test_actions_in_spec_json(self, ui_spec_with_actions: UISpec):
        """Test that actions are included in spec JSON."""
        generator = JSGenerator(ui_spec_with_actions)
        spec_json = generator.generate_spec_json()
        spec = json.loads(spec_json)

        component = spec["components"][0]
        assert "actions" in component
        assert len(component["actions"]) == 6

        # Check action names
        action_names = [a["name"] for a in component["actions"]]
        assert "selectTask" in action_names
        assert "loadTasks" in action_names
        assert "createTask" in action_names


# =============================================================================
# Effects Tests
# =============================================================================


class TestEffects:
    """Test effects system in runtime."""

    def test_execute_effect_function(self, ui_spec_with_actions: UISpec):
        """Test executeEffect function."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "async function executeEffect(effect, context)" in runtime

    def test_fetch_effect_handling(self, ui_spec_with_actions: UISpec):
        """Test fetch effect handling."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'fetch':" in runtime
        assert "apiClient" in runtime
        assert "setGlobalLoading(true)" in runtime
        assert "setGlobalLoading(false)" in runtime

    def test_navigate_effect_handling(self, ui_spec_with_actions: UISpec):
        """Test navigate effect handling."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'navigate':" in runtime
        assert "window.history.pushState" in runtime
        assert "dnr-navigate" in runtime

    def test_toast_effect_handling(self, ui_spec_with_actions: UISpec):
        """Test toast effect handling."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'toast':" in runtime
        assert "showToast" in runtime

    def test_log_effect_handling(self, ui_spec_with_actions: UISpec):
        """Test log effect handling."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'log':" in runtime
        assert "console[level]" in runtime

    def test_custom_effect_handling(self, ui_spec_with_actions: UISpec):
        """Test custom effect handling."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'custom':" in runtime
        assert "effect:${effect.name}" in runtime


# =============================================================================
# API Client Tests
# =============================================================================


class TestAPIClient:
    """Test API client in runtime."""

    def test_api_client_exists(self, ui_spec_with_state: UISpec):
        """Test API client object exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "apiClient = {" in runtime
        assert "baseUrl: '/api'" in runtime

    def test_api_client_methods(self, ui_spec_with_state: UISpec):
        """Test API client has CRUD methods."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "get(path, options)" in runtime
        assert "post(path, data, options)" in runtime
        assert "put(path, data, options)" in runtime
        assert "patch(path, data, options)" in runtime
        assert "delete(path, options)" in runtime

    def test_api_client_crud_helpers(self, ui_spec_with_state: UISpec):
        """Test API client has entity helpers."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "list(entity, params = {})" in runtime
        assert "read(entity, id)" in runtime
        assert "create(entity, data)" in runtime
        assert "update(entity, id, data)" in runtime
        assert "remove(entity, id)" in runtime


# =============================================================================
# Toast Notification Tests
# =============================================================================


class TestToastNotifications:
    """Test toast notification system in runtime."""

    def test_show_toast_function(self, ui_spec_with_state: UISpec):
        """Test showToast function exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "function showToast(message, options = {})" in runtime

    def test_toast_variants(self, ui_spec_with_state: UISpec):
        """Test toast supports different variants."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "'success'" in runtime
        assert "'error'" in runtime
        assert "'warning'" in runtime
        assert "'info'" in runtime

    def test_toast_container(self, ui_spec_with_state: UISpec):
        """Test toast container is created."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "dnr-toast-container" in runtime
        assert "ensureToastContainer" in runtime

    def test_toast_animations(self, ui_spec_with_state: UISpec):
        """Test toast animations exist."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "dnr-toast-in" in runtime
        assert "dnr-toast-out" in runtime


# =============================================================================
# Patch Operations Tests
# =============================================================================


class TestPatchOperations:
    """Test state patch operations in runtime."""

    def test_apply_patch_function(self, ui_spec_with_actions: UISpec):
        """Test applyPatch function exists."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "function applyPatch(scope, path, patch, context)" in runtime

    def test_patch_set_operation(self, ui_spec_with_actions: UISpec):
        """Test SET patch operation."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'set':" in runtime

    def test_patch_merge_operation(self, ui_spec_with_actions: UISpec):
        """Test MERGE patch operation."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'merge':" in runtime
        assert "...current, ...value" in runtime

    def test_patch_append_operation(self, ui_spec_with_actions: UISpec):
        """Test APPEND patch operation."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'append':" in runtime
        assert "[...current, value]" in runtime

    def test_patch_remove_operation(self, ui_spec_with_actions: UISpec):
        """Test REMOVE patch operation."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'remove':" in runtime
        assert "current.filter" in runtime

    def test_patch_delete_operation(self, ui_spec_with_actions: UISpec):
        """Test DELETE patch operation."""
        generator = JSGenerator(ui_spec_with_actions)
        runtime = generator.generate_runtime()

        assert "case 'delete':" in runtime


# =============================================================================
# UI Component Tests
# =============================================================================


class TestUIComponents:
    """Test built-in UI components in runtime."""

    def test_loading_component(self, ui_spec_with_state: UISpec):
        """Test Loading component exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "registerComponent('Loading'" in runtime
        assert "dnr-spinner" in runtime
        assert "dnr-spin" in runtime

    def test_error_component(self, ui_spec_with_state: UISpec):
        """Test Error component exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "registerComponent('Error'" in runtime
        assert "onRetry" in runtime

    def test_empty_component(self, ui_spec_with_state: UISpec):
        """Test Empty component exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "registerComponent('Empty'" in runtime
        assert "No data available" in runtime

    def test_modal_component(self, ui_spec_with_state: UISpec):
        """Test Modal component exists."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        assert "registerComponent('Modal'" in runtime
        assert "dnr-modal-overlay" in runtime
        assert "onClose" in runtime


# =============================================================================
# Global Exports Tests
# =============================================================================


class TestGlobalExports:
    """Test that all functionality is properly exported."""

    def test_dnr_global_object(self, ui_spec_with_state: UISpec):
        """Test DNR global object structure."""
        generator = JSGenerator(ui_spec_with_state)
        runtime = generator.generate_runtime()

        # Check major exports
        assert "global.DNR = {" in runtime

        # Signals
        assert "createSignal," in runtime
        assert "createEffect," in runtime
        assert "createMemo," in runtime
        assert "createResource," in runtime
        assert "batch," in runtime

        # State
        assert "getState," in runtime
        assert "setState," in runtime
        assert "updateState," in runtime

        # Actions
        assert "registerAction," in runtime
        assert "dispatch," in runtime
        assert "executeAction," in runtime

        # UI
        assert "showToast," in runtime
        assert "api: apiClient," in runtime
