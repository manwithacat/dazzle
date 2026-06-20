"""#1324 FR-5: declarative workspace `primary_actions:` heading CTAs.

Covers the build-site resolution of authored actions to ``{label, route}``
and the merge contract: authored actions APPEND AFTER the auto-inferred
create-surface CTAs (#827), with surface targets resolved via the SAME
route map the template compiler uses.
"""

from __future__ import annotations

from dazzle.back.runtime.page_routes import (
    _build_workspace_primary_action_candidates,
    _resolve_workspace_authored_actions,
)
from dazzle.core import ir


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
        assert resolved == [
            {"label": "New Invoice", "route": "/app/invoice/create"},
            {"label": "All Invoices", "route": "/app/invoice"},
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

        # The handler builds `primary_actions` as: filtered(inferred) + authored.
        # Inferred candidates carry a `surface` key (per-request mutate-gated);
        # authored are already-resolved {label, route}. Assert the inferred
        # create-CTA is first and the authored action follows it.
        assert len(inferred) == 1
        assert inferred[0]["label"] == "New Invoice"
        merged = [{"label": c["label"], "route": c["route"]} for c in inferred] + authored
        assert merged == [
            {"label": "New Invoice", "route": "/app/invoice/create"},
            {"label": "Go to Ops", "route": "/app/workspaces/ops_dashboard"},
        ]
