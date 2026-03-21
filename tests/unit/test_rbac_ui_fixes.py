"""Tests for RBAC/UX fixes #581, #582, #583, #585."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core import ir


@pytest.fixture(autouse=True)
def _skip_if_no_fastapi() -> None:
    pytest.importorskip("fastapi")


def _make_appspec(
    *,
    workspaces: list[ir.WorkspaceSpec] | None = None,
    entities: list[ir.EntitySpec] | None = None,
    surfaces: list[ir.SurfaceSpec] | None = None,
) -> ir.AppSpec:
    return ir.AppSpec(
        name="test_app",
        title="Test App",
        module="test",
        workspaces=workspaces or [],
        domain=ir.DomainSpec(entities=entities or []),
        surfaces=surfaces or [],
    )


def _make_deps(
    appspec: ir.AppSpec,
    surface_workspace: dict[str, str] | None = None,
    entity_cedar_specs: dict[str, Any] | None = None,
    surface_entity: dict[str, str] | None = None,
    surface_mode: dict[str, str] | None = None,
    route_entity: dict[str, str] | None = None,
) -> Any:
    from dazzle_ui.runtime.page_routes import _PageDeps

    return _PageDeps(
        appspec=appspec,
        backend_url="http://localhost:8000",
        theme_css="",
        get_auth_context=None,
        app_prefix="/app",
        surface_workspace=surface_workspace or {},
        entity_cedar_specs=entity_cedar_specs or {},
        surface_entity=surface_entity or {},
        surface_mode=surface_mode or {},
        route_entity=route_entity or {},
    )


def _make_auth_ctx(roles: list[str], *, is_superuser: bool = False) -> Any:
    return SimpleNamespace(
        is_authenticated=True,
        user=SimpleNamespace(id="user1", roles=roles, is_superuser=is_superuser),
    )


# ---------------------------------------------------------------------------
# #581 — Create form route returns 403 for denied roles
# ---------------------------------------------------------------------------
class TestCreateFormPermissionCheck:
    """Create form surfaces use CREATE operation for Cedar access check (#581)."""

    def test_create_surface_uses_create_operation(self) -> None:
        """Verify the mode-to-operation mapping includes 'create'."""
        # The fix maps surface_mode=="create" → AccessOperationKind.CREATE
        # in _page_handler. We test _user_can_mutate which uses the same
        # Cedar infrastructure.
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.CREATE,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_create": "Task"},
            surface_mode={"task_create": "create"},
        )
        # Admin can create
        auth_admin = _make_auth_ctx(["role_admin"])
        assert _user_can_mutate(deps, "task_create", "create", auth_admin)

        # Viewer cannot create
        auth_viewer = _make_auth_ctx(["role_viewer"])
        assert not _user_can_mutate(deps, "task_create", "create", auth_viewer)


# ---------------------------------------------------------------------------
# #583 — Sidebar nav filtering by entity access
# ---------------------------------------------------------------------------
class TestNavEntityFiltering:
    """Sidebar nav items filtered by entity permit rules (#583)."""

    def test_denied_entity_removed_from_nav(self) -> None:
        from dazzle_ui.runtime.page_routes import _filter_nav_by_entity_access

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            route_entity={"/app/task": "Task"},
        )
        nav_items = [
            SimpleNamespace(label="Dashboard", route="/app/workspaces/main"),
            SimpleNamespace(label="Tasks", route="/app/task"),
        ]
        auth_ctx = _make_auth_ctx(["role_viewer"])
        filtered = _filter_nav_by_entity_access(nav_items, deps, auth_ctx)
        # Workspace link kept, entity link removed
        assert len(filtered) == 1
        assert filtered[0].label == "Dashboard"

    def test_permitted_entity_kept_in_nav(self) -> None:
        from dazzle_ui.runtime.page_routes import _filter_nav_by_entity_access

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            route_entity={"/app/task": "Task"},
        )
        nav_items = [
            SimpleNamespace(label="Tasks", route="/app/task"),
        ]
        auth_ctx = _make_auth_ctx(["role_admin"])
        filtered = _filter_nav_by_entity_access(nav_items, deps, auth_ctx)
        assert len(filtered) == 1

    def test_superuser_bypasses_nav_filter(self) -> None:
        from dazzle_ui.runtime.page_routes import _filter_nav_by_entity_access

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            route_entity={"/app/task": "Task"},
        )
        nav_items = [
            SimpleNamespace(label="Tasks", route="/app/task"),
        ]
        auth_ctx = _make_auth_ctx(["role_viewer"], is_superuser=True)
        filtered = _filter_nav_by_entity_access(nav_items, deps, auth_ctx)
        assert len(filtered) == 1

    def test_entity_without_cedar_spec_kept(self) -> None:
        from dazzle_ui.runtime.page_routes import _filter_nav_by_entity_access

        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={},
            route_entity={"/app/task": "Task"},
        )
        nav_items = [
            SimpleNamespace(label="Tasks", route="/app/task"),
        ]
        auth_ctx = _make_auth_ctx(["role_viewer"])
        filtered = _filter_nav_by_entity_access(nav_items, deps, auth_ctx)
        assert len(filtered) == 1


# ---------------------------------------------------------------------------
# #585 — ColumnContext visible_condition
# ---------------------------------------------------------------------------
class TestColumnVisibleCondition:
    """List columns respect visible: directive for per-role visibility (#585)."""

    def test_column_context_has_visible_condition(self) -> None:
        from dazzle_ui.runtime.template_context import ColumnContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        assert col.visible_condition is not None
        assert col.hidden is False

    def test_column_hidden_when_role_denied(self) -> None:
        from dazzle_ui.runtime.template_context import ColumnContext
        from dazzle_ui.utils.condition_eval import evaluate_condition

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        role_ctx = {"user_roles": ["viewer"]}
        if not evaluate_condition(col.visible_condition, {}, role_ctx):
            col.hidden = True
        assert col.hidden is True

    def test_column_visible_when_role_allowed(self) -> None:
        from dazzle_ui.runtime.template_context import ColumnContext
        from dazzle_ui.utils.condition_eval import evaluate_condition

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        role_ctx = {"user_roles": ["admin"]}
        if not evaluate_condition(col.visible_condition, {}, role_ctx):
            col.hidden = True
        assert col.hidden is False

    def test_column_without_condition_always_visible(self) -> None:
        from dazzle_ui.runtime.template_context import ColumnContext

        col = ColumnContext(key="name", label="Name")
        assert col.visible_condition is None
        assert col.hidden is False

    def test_shared_table_not_mutated_by_visibility_check(self) -> None:
        """Regression: visible_condition check must not corrupt the shared ctx (#587).

        The page handler deep-copies ctx.table before checking
        visibility — verify that the original columns stay unhidden.
        """
        from dazzle_ui.runtime.template_context import ColumnContext, TableContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        shared_table = TableContext(
            entity_name="Task",
            title="Tasks",
            api_endpoint="/api/tasks",
            columns=[
                ColumnContext(key="name", label="Name"),
                ColumnContext(key="salary", label="Salary", visible_condition=vis),
            ],
        )

        # Simulate what page_routes.py now does: deep-copy, then mutate copy
        req_table = shared_table.model_copy(deep=True)
        from dazzle_ui.utils.condition_eval import evaluate_condition

        role_ctx = {"user_roles": ["viewer"]}
        for _col in req_table.columns:
            if _col.visible_condition:
                if not evaluate_condition(_col.visible_condition, {}, role_ctx):
                    _col.hidden = True

        # Copy's column is hidden
        assert req_table.columns[1].hidden is True
        # Original is untouched
        assert shared_table.columns[1].hidden is False


# ---------------------------------------------------------------------------
# #582 — Empty state CTA guard
# ---------------------------------------------------------------------------
class TestEmptyStateCTAGuard:
    """Empty state template only shows create CTA when create_url is set (#582).

    The empty_state.html template already guards with {% if create_url %}.
    Workspace region rendering never passes create_url, so the CTA is hidden.
    Entity list pages suppress table.create_url when the user lacks CREATE
    permission (covered by TestUserCanMutate in test_permit_button_suppression.py).
    """

    def test_create_url_suppressed_for_denied_role(self) -> None:
        """Table create_url set to None when role lacks CREATE permission."""
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.CREATE,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_list": "Task"},
        )
        auth_ctx = _make_auth_ctx(["role_viewer"])
        # This is what page_routes does: if not _user_can_mutate → create_url = None
        assert not _user_can_mutate(deps, "task_list", "create", auth_ctx)
