"""TR-57: workspace primary CTA must say "New Contact", not "New Contact List"."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir.fields import FieldModifier
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


def test_child_comment_entity_not_workspace_primary_cta() -> None:
    """#1626 — New Task Comment must not peer with New Task on the desk."""
    ws = ir.WorkspaceSpec(
        name="my_work",
        regions=[
            ir.WorkspaceRegion(name="open", source="Task"),
            ir.WorkspaceRegion(name="notes", source="TaskComment"),
        ],
    )
    task_create = ir.SurfaceSpec(
        name="task_create", mode=ir.SurfaceMode.CREATE, entity_ref="Task", title="New Task"
    )
    comment_create = ir.SurfaceSpec(
        name="task_comment_create",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="TaskComment",
        title="New Task Comment",
    )
    actions = _build_workspace_primary_action_candidates(
        ws,
        app_prefix="/app",
        create_surfaces_by_entity={"Task": task_create, "TaskComment": comment_create},
        list_surfaces_by_entity={},
        entity_titles={"Task": "Task", "TaskComment": "Task Comment"},
    )
    labels = [a["label"] for a in actions]
    assert labels == ["New Task"]
    assert not any("Comment" in lbl for lbl in labels)


def test_required_parent_record_suppresses_contextual_create_cta() -> None:
    invoice = ir.EntitySpec(name="Invoice", title="Invoice", fields=[])
    document = ir.EntitySpec(
        name="InvoiceDocument",
        title="Invoice Document",
        fields=[
            ir.FieldSpec(
                name="invoice",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Invoice"),
                modifiers=[FieldModifier.REQUIRED],
            )
        ],
    )
    create = {
        name: ir.SurfaceSpec(
            name=f"{name.lower()}_create", mode=ir.SurfaceMode.CREATE, entity_ref=name
        )
        for name in ("Invoice", "InvoiceDocument")
    }
    desk = ir.WorkspaceSpec(
        name="pay_desk",
        regions=[
            ir.WorkspaceRegion(name="past_due", source="Invoice"),
            ir.WorkspaceRegion(name="documents", source="InvoiceDocument"),
        ],
    )
    actions = _build_workspace_primary_action_candidates(
        desk,
        app_prefix="/app",
        create_surfaces_by_entity=create,
        list_surfaces_by_entity={},
        entities_by_name={"Invoice": invoice, "InvoiceDocument": document},
    )
    assert [action["entity"] for action in actions] == ["Invoice"]

    document_desk = ir.WorkspaceSpec(
        name="document_desk",
        regions=[ir.WorkspaceRegion(name="documents", source="InvoiceDocument")],
    )
    standalone_actions = _build_workspace_primary_action_candidates(
        document_desk,
        app_prefix="/app",
        create_surfaces_by_entity=create,
        list_surfaces_by_entity={},
        entities_by_name={"Invoice": invoice, "InvoiceDocument": document},
    )
    assert [action["entity"] for action in standalone_actions] == ["InvoiceDocument"]


def test_tenant_reference_does_not_make_a_root_record_contextual() -> None:
    invoice = ir.EntitySpec(
        name="Invoice",
        title="Invoice",
        fields=[
            ir.FieldSpec(
                name="tenant_id",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Tenant"),
                modifiers=[FieldModifier.REQUIRED],
            )
        ],
    )
    desk = ir.WorkspaceSpec(
        name="billing",
        regions=[
            ir.WorkspaceRegion(name="tenant", source="Tenant"),
            ir.WorkspaceRegion(name="invoices", source="Invoice"),
        ],
    )
    actions = _build_workspace_primary_action_candidates(
        desk,
        app_prefix="/app",
        create_surfaces_by_entity={
            "Invoice": ir.SurfaceSpec(
                name="invoice_create", mode=ir.SurfaceMode.CREATE, entity_ref="Invoice"
            )
        },
        list_surfaces_by_entity={},
        entities_by_name={"Invoice": invoice},
    )
    assert [action["entity"] for action in actions] == ["Invoice"]
