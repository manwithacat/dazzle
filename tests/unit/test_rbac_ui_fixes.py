"""Tests for RBAC/UX fixes #581, #582, #583, #585."""

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
) -> Any:
    from dazzle.http.runtime.page_routes import _PageRouterConfig

    return _PageRouterConfig(
        appspec=appspec,
        theme_css="",
        get_auth_context=None,
        app_prefix="/app",
        surface_workspace=surface_workspace or {},
        entity_cedar_specs=entity_cedar_specs or {},
        surface_entity=surface_entity or {},
        surface_mode=surface_mode or {},
    )


def _make_auth_ctx(roles: list[str], *, is_superuser: bool = False) -> Any:
    return SimpleNamespace(
        is_authenticated=True,
        user=SimpleNamespace(id="user1", roles=roles, is_superuser=is_superuser),
    )


def _update_cedar(readers: list[str], *, with_list: bool = False) -> Any:
    """UPDATE for ``admin`` only; READ (and optionally LIST) for ``readers``."""
    pytest.importorskip("dazzle.render.access_evaluator")
    from dazzle.http.specs.auth import (
        AccessOperationKind,
        EntityAccessSpec,
        PermissionRuleSpec,
    )

    ops = [AccessOperationKind.LIST] if with_list else []
    return EntityAccessSpec(
        permissions=[
            PermissionRuleSpec(operation=AccessOperationKind.UPDATE, personas=["admin"]),
            *(PermissionRuleSpec(operation=op, personas=readers) for op in ops),
            PermissionRuleSpec(operation=AccessOperationKind.READ, personas=readers),
        ],
    )


def _read_only_viewer_appspec() -> ir.AppSpec:
    """One workspace ``ws`` where the ``viewer`` persona variant is read_only."""
    return _make_appspec(
        workspaces=[
            ir.WorkspaceSpec(
                name="ws",
                title="WS",
                regions=[],
                ux=ir.UXSpec(
                    persona_variants=[ir.PersonaVariant(persona="viewer", read_only=True)]
                ),
            )
        ],
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
        from dazzle.http.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
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
# Cycle 1393 — Edit form route uses UPDATE (not READ) for Cedar access
# ---------------------------------------------------------------------------
class TestEditFormPermissionCheck:
    """Edit form surfaces use UPDATE operation for Cedar page gate.

    Parity with #581 create→CREATE and with detail chrome that already
    clears edit_url when UPDATE is denied (cycles 1390–1392). Without
    this, a viewer who can READ still deep-links into a painted edit form.
    """

    def _prc(
        self,
        *,
        deps: Any,
        surface_name: str,
        auth_ctx: Any,
    ) -> Any:
        from dazzle.http.runtime.page_routes import _PageRequestContext

        return _PageRequestContext(
            deps=deps,
            ctx=SimpleNamespace(user_roles=list(auth_ctx.user.roles)),
            request=SimpleNamespace(),
            auth_ctx=auth_ctx,
            surface_name=surface_name,
            cookies={},
            path_id="t1",
        )

    def test_edit_surface_denied_role_raises_403(self) -> None:
        from fastapi import HTTPException

        from dazzle.http.runtime.page_routes import _check_entity_cedar_access

        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.READ,
                    personas=["admin", "viewer"],
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_edit": "Task"},
            surface_mode={"task_edit": "edit"},
        )
        prc = self._prc(
            deps=deps,
            surface_name="task_edit",
            auth_ctx=_make_auth_ctx(["role_viewer"]),
        )
        with pytest.raises(HTTPException) as excinfo:
            _check_entity_cedar_access(prc)
        assert excinfo.value.status_code == 403

    def test_edit_surface_permitted_role_allows(self) -> None:
        from dazzle.http.runtime.page_routes import _check_entity_cedar_access

        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_edit": "Task"},
            surface_mode={"task_edit": "edit"},
        )
        prc = self._prc(
            deps=deps,
            surface_name="task_edit",
            auth_ctx=_make_auth_ctx(["role_admin"]),
        )
        assert _check_entity_cedar_access(prc) is None

    def test_view_surface_still_uses_read(self) -> None:
        """Regression: view must not require UPDATE after the edit→UPDATE map."""
        from dazzle.http.runtime.page_routes import _check_entity_cedar_access

        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.READ,
                    personas=["viewer"],
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_view": "Task"},
            surface_mode={"task_view": "view"},
        )
        prc = self._prc(
            deps=deps,
            surface_name="task_view",
            auth_ctx=_make_auth_ctx(["role_viewer"]),
        )
        assert _check_entity_cedar_access(prc) is None


# ---------------------------------------------------------------------------
# Cycle 1394 — Related-tab create CTA uses CREATE on related entity
# ---------------------------------------------------------------------------
class TestRelatedTabCreatePermission:
    """Detail related-tab "+ New X" must clear create_url when CREATE denied.

    Parity with list create_url (#582), create-form page gate (#581), and the
    1390–1393 mutation-chrome series. Compile-time always stamps create_url.
    """

    def _contact_create_cedar(self) -> Any:
        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        return EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.CREATE,
                    personas=["admin"],
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.READ,
                    personas=["admin", "viewer"],
                ),
            ],
        )

    def _detail_with_related_create(self, create_url: str = "/contacts/create") -> Any:
        from dazzle.render.context import (
            DetailContext,
            RelatedGroupContext,
            RelatedTabContext,
        )

        tab = RelatedTabContext(
            tab_id="tab-contacts",
            label="Contacts",
            entity_name="Contact",
            api_endpoint="/contacts",
            filter_field="company",
            columns=[],
            create_url=create_url,
        )
        return DetailContext(
            entity_name="Company",
            title="Company",
            fields=[],
            related_groups=[
                RelatedGroupContext(
                    group_id="group-people",
                    label="People",
                    display="table",
                    tabs=[tab],
                )
            ],
        )

    def test_entity_can_mutate_create_deny_viewer(self) -> None:
        from dazzle.http.runtime.page_routes import _entity_can_mutate

        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Contact": self._contact_create_cedar()},
        )
        assert not _entity_can_mutate(deps, "Contact", "create", _make_auth_ctx(["role_viewer"]))
        assert _entity_can_mutate(deps, "Contact", "create", _make_auth_ctx(["role_admin"]))

    def test_related_create_cleared_when_create_denied(self) -> None:
        from dazzle.http.runtime.page_routes import _gate_related_tab_create_urls

        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Contact": self._contact_create_cedar()},
            surface_entity={"company_view": "Company"},
            surface_mode={"company_view": "view"},
        )
        detail = self._detail_with_related_create()
        _gate_related_tab_create_urls(
            detail,
            deps,
            "company_view",
            _make_auth_ctx(["role_viewer"]),
            ["role_viewer"],
        )
        assert detail.related_groups[0].tabs[0].create_url is None

    def test_related_create_kept_when_create_allowed(self) -> None:
        from dazzle.http.runtime.page_routes import _gate_related_tab_create_urls

        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Contact": self._contact_create_cedar()},
            surface_entity={"company_view": "Company"},
            surface_mode={"company_view": "view"},
        )
        detail = self._detail_with_related_create()
        _gate_related_tab_create_urls(
            detail,
            deps,
            "company_view",
            _make_auth_ctx(["role_admin"]),
            ["role_admin"],
        )
        assert detail.related_groups[0].tabs[0].create_url == "/contacts/create"

    def test_workspace_read_only_clears_related_create(self) -> None:
        from dazzle.http.runtime.page_routes import _gate_related_tab_create_urls

        appspec = _read_only_viewer_appspec()
        # No CREATE rules → entity_can_mutate would allow; read_only wins.
        deps = _make_deps(
            appspec,
            surface_workspace={"company_view": "ws"},
            surface_entity={"company_view": "Company"},
            surface_mode={"company_view": "view"},
        )
        detail = self._detail_with_related_create()
        _gate_related_tab_create_urls(
            detail,
            deps,
            "company_view",
            _make_auth_ctx(["role_viewer"]),
            ["role_viewer"],
        )
        assert detail.related_groups[0].tabs[0].create_url is None


class TestListShellInlineEditablePermission:
    """List-shell inline_editable must clear when UPDATE denied (cycle 1396).

    HTMX hydrate already gates; shell DzTableMount still stamped columns
    for pure Cedar UPDATE deny and workspace read_only.
    """

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            pytest.param("role_viewer", [], id="cleared-when-update-denied"),
            pytest.param("role_admin", ["title", "status"], id="kept-when-update-allowed"),
        ],
    )
    def test_cedar_update_gates_inline(self, role: str, expected: list[str]) -> None:
        from dazzle.http.runtime.page_routes import _gate_table_inline_editable

        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Ticket": _update_cedar(["admin", "viewer"])},
            surface_entity={"ticket_list": "Ticket"},
            surface_mode={"ticket_list": "list"},
        )
        table = SimpleNamespace(inline_editable=["title", "status"])
        _gate_table_inline_editable(table, deps, "ticket_list", _make_auth_ctx([role]), [role])
        assert table.inline_editable == expected

    def test_workspace_read_only_clears_inline(self) -> None:
        from dazzle.http.runtime.page_routes import _gate_table_inline_editable

        deps = _make_deps(
            _read_only_viewer_appspec(),
            surface_workspace={"ticket_list": "ws"},
            surface_entity={"ticket_list": "Ticket"},
            surface_mode={"ticket_list": "list"},
        )
        table = SimpleNamespace(inline_editable=["title"])
        _gate_table_inline_editable(
            table,
            deps,
            "ticket_list",
            _make_auth_ctx(["role_viewer"]),
            ["role_viewer"],
        )
        assert table.inline_editable == []


_TRANSITIONS = [
    {"to_state": "approved", "label": "Approve"},
    {"to_state": "rejected", "label": "Reject"},
]


class TestQueueTransitionPermission:
    """Workspace QUEUE SM buttons must clear when UPDATE denied (cycle 1396)."""

    @pytest.mark.parametrize(
        ("has_cedar", "role", "expected"),
        [
            pytest.param(True, "role_viewer", [], id="cleared-when-update-denied"),
            pytest.param(True, "role_admin", _TRANSITIONS, id="kept-when-update-allowed"),
            pytest.param(False, "role_viewer", _TRANSITIONS, id="no-cedar-leaves-transitions"),
        ],
    )
    def test_gate_queue_transitions(
        self, has_cedar: bool, role: str, expected: list[dict[str, str]]
    ) -> None:
        from dazzle.http.runtime.workspace_region_orchestration import (
            gate_queue_transitions_for_principal,
        )

        out = gate_queue_transitions_for_principal(
            list(_TRANSITIONS),
            _update_cedar(["admin", "viewer"]) if has_cedar else None,
            _make_auth_ctx([role]),
            entity_name="Ticket",
        )
        assert out == expected


_CONFIRM_URLS = ("/app/integration/enable", "/app/integration/draft", "/app/integration/revoke")


class TestConfirmActionPanelPermission:
    """confirm_action_panel commit/revoke URLs clear when UPDATE denied (cycle 1397)."""

    @pytest.mark.parametrize(
        ("has_cedar", "role", "expected"),
        [
            pytest.param(True, "role_ops_engineer", ("", "", ""), id="cleared-when-update-denied"),
            pytest.param(True, "role_admin", _CONFIRM_URLS, id="kept-when-update-allowed"),
            pytest.param(False, "role_viewer", _CONFIRM_URLS, id="no-cedar-leaves-urls"),
        ],
    )
    def test_gate_confirm_action_urls(
        self, has_cedar: bool, role: str, expected: tuple[str, str, str]
    ) -> None:
        from dazzle.http.runtime.workspace_region_orchestration import (
            gate_confirm_action_urls_for_principal,
        )

        primary, secondary, revoke = _CONFIRM_URLS
        out = gate_confirm_action_urls_for_principal(
            primary_url=primary,
            secondary_url=secondary,
            revoke_url=revoke,
            cedar_access_spec=_update_cedar(["admin", "ops_engineer"]) if has_cedar else None,
            auth_ctx=_make_auth_ctx([role]),
            entity_name="Integration",
        )
        assert out == expected


# ---------------------------------------------------------------------------
# Cycle 1406 — EDIT-path region row drill UPDATE gate
# ---------------------------------------------------------------------------
class TestEditPathRowDrillGate:
    """Region action: task_edit → …/{id}/edit clears when UPDATE denied."""

    @pytest.mark.parametrize(
        ("url", "role", "expected"),
        [
            # Cycle 1407: demote to VIEW detail (not blank — rows stay navigable)
            pytest.param(
                "/app/task/{id}/edit",
                "role_viewer",
                "/app/task/{id}",
                id="edit-demoted-to-detail-when-update-denied-1407",
            ),
            pytest.param(
                "/app/task/{id}/edit?tab=meta",
                "role_viewer",
                "/app/task/{id}?tab=meta",
                id="demote-preserves-query",
            ),
            pytest.param(
                "/app/task/{id}/edit",
                "role_admin",
                "/app/task/{id}/edit",
                id="edit-kept-when-update-allowed",
            ),
            pytest.param(
                "/app/task/{id}", "role_viewer", "/app/task/{id}", id="view-drill-always-kept"
            ),
        ],
    )
    def test_gate_edit_path_drill(self, url: str, role: str, expected: str) -> None:
        from dazzle.http.runtime.handlers.list_handlers import (
            gate_edit_path_drill_for_principal,
        )

        specs = {"Task": _update_cedar(["admin", "viewer"], with_list=True)}
        assert gate_edit_path_drill_for_principal(url, specs, _make_auth_ctx([role])) == expected

    @pytest.mark.parametrize(
        ("urls", "role", "expected"),
        [
            # task_inbox multi-entity map: EDIT demotes, VIEW stays (cycle 1409)
            pytest.param(
                {"Task": "/app/task/{id}/edit", "Note": "/app/note/{id}"},
                "role_viewer",
                {"Task": "/app/task/{id}", "Note": "/app/note/{id}"},
                id="demotes-per-entity-1409",
            ),
            pytest.param(
                {"Task": "/app/task/{id}/edit"},
                "role_admin",
                {"Task": "/app/task/{id}/edit"},
                id="kept-for-admin",
            ),
            pytest.param(None, None, {}, id="none-map-empty"),
            pytest.param({}, None, {}, id="empty-map-empty"),
        ],
    )
    def test_gate_edit_path_drill_map(
        self, urls: dict[str, str] | None, role: str | None, expected: dict[str, str]
    ) -> None:
        from dazzle.http.runtime.handlers.list_handlers import (
            gate_edit_path_drill_map_for_principal,
        )

        specs: dict[str, Any] = {}
        auth = None
        if role is not None:
            specs = {"Task": _update_cedar(["admin", "viewer"], with_list=True)}
            auth = _make_auth_ctx([role])
        assert gate_edit_path_drill_map_for_principal(urls, specs, auth) == expected


# ---------------------------------------------------------------------------
# #585 — ColumnContext visible_condition
# ---------------------------------------------------------------------------
class TestColumnVisibleCondition:
    """List columns respect visible: directive for per-role visibility (#585)."""

    def test_column_context_has_visible_condition(self) -> None:
        from dazzle.render.context import ColumnContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        assert col.visible_condition is not None
        assert col.hidden is False

    def test_column_hidden_when_role_denied(self) -> None:
        from dazzle.core.condition_eval import evaluate_condition
        from dazzle.render.context import ColumnContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        role_ctx = {"user_roles": ["viewer"]}
        if not evaluate_condition(col.visible_condition, {}, role_ctx):
            col.hidden = True
        assert col.hidden is True

    def test_column_visible_when_role_allowed(self) -> None:
        from dazzle.core.condition_eval import evaluate_condition
        from dazzle.render.context import ColumnContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        col = ColumnContext(key="salary", label="Salary", visible_condition=vis)
        role_ctx = {"user_roles": ["admin"]}
        if not evaluate_condition(col.visible_condition, {}, role_ctx):
            col.hidden = True
        assert col.hidden is False

    def test_column_without_condition_always_visible(self) -> None:
        from dazzle.render.context import ColumnContext

        col = ColumnContext(key="name", label="Name")
        assert col.visible_condition is None
        assert col.hidden is False

    def test_shared_table_not_mutated_by_visibility_check(self) -> None:
        """Regression: visible_condition check must not corrupt the shared ctx (#587).

        The page handler deep-copies ctx.table before checking
        visibility — verify that the original columns stay unhidden.
        """
        from dazzle.render.context import ColumnContext, TableContext

        vis = {"role_check": {"role_name": "admin"}, "comparison": None, "operator": None}
        shared_table = TableContext(
            entity_name="Task",
            title="Tasks",
            api_endpoint="/_dazzle/tasks",
            columns=[
                ColumnContext(key="name", label="Name"),
                ColumnContext(key="salary", label="Salary", visible_condition=vis),
            ],
        )

        # Simulate what page_routes.py now does: deep-copy, then mutate copy
        req_table = shared_table.model_copy(deep=True)
        from dazzle.core.condition_eval import evaluate_condition

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
        from dazzle.http.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle.render.access_evaluator")
        from dazzle.http.specs.auth import (
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
