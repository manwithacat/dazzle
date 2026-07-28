"""#1324 FR-5: declarative workspace `primary_actions:` heading CTAs.

Covers the build-site resolution of authored actions to ``{label, route}``
and the merge contract: authored actions APPEND AFTER the auto-inferred
create-surface CTAs (#827), with surface targets resolved via the SAME
route map the template compiler uses.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.http.runtime.page_routes import (
    _build_workspace_primary_action_candidates,
    _resolve_workspace_authored_actions,
    gate_authored_primary_actions_for_principal,
)


def _surface(name: str, mode: ir.SurfaceMode, entity: str) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(name=name, mode=mode, entity_ref=entity)


class TestResolveAuthoredActions:
    """`_resolve_workspace_authored_actions` → list of {label, route}."""

    def test_workspace_target_route(self) -> None:
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="Dashboard", target_kind="workspace", target="ops_dashboard"
                )
            ],
        )
        resolved = _resolve_workspace_authored_actions(ws, app_prefix="/app", surfaces_by_name={})
        assert resolved == [{"label": "Dashboard", "route": "/app/workspaces/ops_dashboard"}]

    def test_surface_target_uses_canonical_route_map(self) -> None:
        create = _surface("create_invoice", ir.SurfaceMode.CREATE, "Invoice")
        list_s = _surface("list_invoice", ir.SurfaceMode.LIST, "Invoice")
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="New Invoice", target_kind="surface", target="create_invoice"
                ),
                ir.WorkspacePrimaryActionSpec(
                    label="All Invoices", target_kind="surface", target="list_invoice"
                ),
            ],
        )
        resolved = _resolve_workspace_authored_actions(
            ws,
            app_prefix="/app",
            surfaces_by_name={"create_invoice": create, "list_invoice": list_s},
        )
        # CREATE → /app/<slug>/create ; LIST → /app/<slug> (mirrors
        # template_compiler.compile_appspec_to_templates route_map).
        # CREATE carries mutation metadata for request-time RBAC gate (cycle 1399).
        assert resolved == [
            {
                "label": "New Invoice",
                "route": "/app/invoice/create",
                "mutation": "create",
                "surface": "create_invoice",
            },
            {"label": "All Invoices", "route": "/app/invoice"},
        ]

    def test_edit_surface_carries_update_mutation(self) -> None:
        edit = _surface("edit_invoice", ir.SurfaceMode.EDIT, "Invoice")
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="Edit Invoice", target_kind="surface", target="edit_invoice"
                ),
            ],
        )
        resolved = _resolve_workspace_authored_actions(
            ws, app_prefix="/app", surfaces_by_name={"edit_invoice": edit}
        )
        assert resolved == [
            {
                "label": "Edit Invoice",
                "route": "/app/invoice/{id}/edit",
                "mutation": "update",
                "surface": "edit_invoice",
            },
        ]

    def test_unknown_surface_skipped_defensively(self) -> None:
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(label="Ghost", target_kind="surface", target="nope")
            ],
        )
        resolved = _resolve_workspace_authored_actions(ws, app_prefix="/app", surfaces_by_name={})
        assert resolved == []

    def test_no_authored_actions_empty(self) -> None:
        ws = ir.WorkspaceSpec(name="reports")
        resolved = _resolve_workspace_authored_actions(ws, app_prefix="/app", surfaces_by_name={})
        assert resolved == []


class TestAuthoredAppendsAfterInferred:
    """Authored actions append AFTER auto-inferred create-CTAs (#827)."""

    def test_authored_action_follows_inferred_create_cta(self) -> None:
        # A workspace region over Invoice → one inferred "New Invoice" CTA.
        ws = ir.WorkspaceSpec(
            name="reports",
            regions=[
                ir.WorkspaceRegion(name="metrics", source="Invoice"),
            ],
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="Go to Ops", target_kind="workspace", target="ops_dashboard"
                )
            ],
        )
        create = _surface("create_invoice", ir.SurfaceMode.CREATE, "Invoice")
        list_s = _surface("list_invoice", ir.SurfaceMode.LIST, "Invoice")

        inferred = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={"Invoice": create},
            list_surfaces_by_entity={"Invoice": list_s},
        )
        authored = _resolve_workspace_authored_actions(
            ws, app_prefix="/app", surfaces_by_name={"create_invoice": create}
        )

        # The handler builds `primary_actions` as: filtered(inferred) +
        # gate_authored(authored). Inferred candidates carry a `surface` key;
        # authored workspace targets are {label, route} (no mutation). Assert
        # the inferred create-CTA is first and the authored action follows it.
        assert len(inferred) == 1
        assert inferred[0]["label"] == "New Invoice"
        merged = [{"label": c["label"], "route": c["route"]} for c in inferred] + [
            {"label": a["label"], "route": a["route"]} for a in authored
        ]
        assert merged == [
            {"label": "New Invoice", "route": "/app/invoice/create"},
            {"label": "Go to Ops", "route": "/app/workspaces/ops_dashboard"},
        ]


class TestGateAuthoredPrimaryActions:
    """Authored CREATE/EDIT heading CTAs respect CREATE/UPDATE (cycle 1399)."""

    def _invoice_create_cedar(self) -> object:
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
                    operation=AccessOperationKind.UPDATE,
                    personas=["admin"],
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["admin", "viewer"],
                ),
            ],
        )

    def _deps(self) -> object:
        from dazzle.http.runtime.page_routes import _PageRouterConfig

        return _PageRouterConfig(
            appspec=ir.AppSpec(
                name="t",
                title="T",
                module="t",
                domain=ir.DomainSpec(entities=[]),
            ),
            theme_css="",
            get_auth_context=None,
            app_prefix="/app",
            surface_workspace={},
            entity_cedar_specs={"Invoice": self._invoice_create_cedar()},
            surface_entity={
                "create_invoice": "Invoice",
                "edit_invoice": "Invoice",
                "list_invoice": "Invoice",
            },
            surface_mode={},
            route_entity={},
        )

    def _auth(self, roles: list[str]) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="user1", roles=roles, is_superuser=False),
        )

    def test_create_cta_dropped_when_create_denied(self) -> None:
        authored = [
            {
                "label": "New Invoice",
                "route": "/app/invoice/create",
                "mutation": "create",
                "surface": "create_invoice",
            },
            {"label": "All Invoices", "route": "/app/invoice"},
            {"label": "Ops", "route": "/app/workspaces/ops"},
        ]
        out = gate_authored_primary_actions_for_principal(
            authored, deps=self._deps(), auth_ctx=self._auth(["role_viewer"])
        )
        assert out == [
            {"label": "All Invoices", "route": "/app/invoice"},
            {"label": "Ops", "route": "/app/workspaces/ops"},
        ]

    def test_create_cta_kept_when_create_allowed(self) -> None:
        authored = [
            {
                "label": "New Invoice",
                "route": "/app/invoice/create",
                "mutation": "create",
                "surface": "create_invoice",
            },
        ]
        out = gate_authored_primary_actions_for_principal(
            authored, deps=self._deps(), auth_ctx=self._auth(["role_admin"])
        )
        assert out == [{"label": "New Invoice", "route": "/app/invoice/create"}]

    def test_edit_cta_dropped_when_update_denied(self) -> None:
        authored = [
            {
                "label": "Edit Invoice",
                "route": "/app/invoice/{id}/edit",
                "mutation": "update",
                "surface": "edit_invoice",
            },
        ]
        out = gate_authored_primary_actions_for_principal(
            authored, deps=self._deps(), auth_ctx=self._auth(["role_viewer"])
        )
        assert out == []
