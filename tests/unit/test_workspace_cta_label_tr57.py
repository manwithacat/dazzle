"""TR-57: workspace primary CTA must say "New Contact", not "New Contact List"."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.http.runtime.page_routes import _build_workspace_primary_action_candidates


def test_workspace_cta_uses_entity_title_not_list_surface_title() -> None:
    ws = ir.WorkspaceSpec(
        name="contacts",
        regions=[ir.WorkspaceRegion(name="directory", source="Contact")],
    )
    create = ir.SurfaceSpec(
        name="contact_create",
        title="Create Contact",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="Contact",
    )
    # The buggy path used this list title → "New Contact List"
    list_s = ir.SurfaceSpec(
        name="contact_list",
        title="Contact List",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Contact",
    )
    actions = _build_workspace_primary_action_candidates(
        ws,
        app_prefix="/app",
        create_surfaces_by_entity={"Contact": create},
        list_surfaces_by_entity={"Contact": list_s},
        entity_titles={"Contact": "Contact"},
    )
    assert len(actions) == 1
    assert actions[0]["label"] == "New Contact"
    assert actions[0]["route"] == "/app/contact/create"


def test_workspace_cta_falls_back_to_create_surface_title() -> None:
    ws = ir.WorkspaceSpec(
        name="contacts",
        regions=[ir.WorkspaceRegion(name="directory", source="Contact")],
    )
    create = ir.SurfaceSpec(
        name="contact_create",
        title="Create Contact",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="Contact",
    )
    list_s = ir.SurfaceSpec(
        name="contact_list",
        title="Contact List",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Contact",
    )
    actions = _build_workspace_primary_action_candidates(
        ws,
        app_prefix="/app",
        create_surfaces_by_entity={"Contact": create},
        list_surfaces_by_entity={"Contact": list_s},
        entity_titles={},  # no entity title map
    )
    assert actions[0]["label"] == "New Contact"


def test_inferred_still_new_invoice_without_entity_title() -> None:
    """Regression: Invoice without titles still becomes New Invoice."""
    ws = ir.WorkspaceSpec(
        name="reports",
        regions=[ir.WorkspaceRegion(name="metrics", source="Invoice")],
    )
    create = ir.SurfaceSpec(name="create_invoice", mode=ir.SurfaceMode.CREATE, entity_ref="Invoice")
    list_s = ir.SurfaceSpec(name="list_invoice", mode=ir.SurfaceMode.LIST, entity_ref="Invoice")
    actions = _build_workspace_primary_action_candidates(
        ws,
        app_prefix="/app",
        create_surfaces_by_entity={"Invoice": create},
        list_surfaces_by_entity={"Invoice": list_s},
    )
    assert actions[0]["label"] == "New Invoice"
