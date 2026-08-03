"""#1603 — list row open via FK hop (task → parent/context entity)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.page.open_via import resolve_list_detail_url_template
from dazzle.render.fragment.region._row_links import _resolve_row_links

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"
SUPPORT = REPO / "examples" / "support_tickets"
INVOICE_OPS = REPO / "examples" / "invoice_ops"
HR = REPO / "examples" / "hr_records"
OPS = REPO / "examples" / "ops_dashboard"
LLM = REPO / "examples" / "llm_ticket_classifier"
CONTACT = REPO / "examples" / "contact_manager"


def test_resolve_default_same_entity() -> None:
    surface = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
    )
    entity = ir.EntitySpec(name="Task", title="Task", fields=[])
    tmpl = resolve_list_detail_url_template(surface, entity)
    assert tmpl == "/app/task/{id}"


def test_resolve_open_via_fk_hop() -> None:
    surface = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
        open_via="assigned_to",
        open_entity="User",
    )
    entity = ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="assigned_to",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
            ),
        ],
    )
    tmpl = resolve_list_detail_url_template(surface, entity)
    assert tmpl == "/app/user/{assigned_to}"


def test_row_links_format_fk_placeholder() -> None:
    tmpl = "/app/user/{assigned_to}"
    rows = [
        {"id": "t1", "assigned_to": "u-aaa", "title": "A"},
        {"id": "t2", "assigned_to": None, "title": "B"},
        {"id": "t3", "title": "C"},  # missing key
    ]
    links = _resolve_row_links(rows, tmpl)
    assert links[0] == "/app/user/u-aaa"
    assert links[1] is None  # null FK — no dead link
    assert links[2] is None  # missing key


def test_row_links_null_fk_falls_back_to_same_entity() -> None:
    """#1614: open-via null → same-entity ``.../{id}`` so row stays drillable."""
    tmpl = "/app/user/{assigned_to}"
    fallback = "/app/task/{id}"
    rows = [
        {"id": "t1", "assigned_to": "u-aaa"},
        {"id": "t2", "assigned_to": None},
        {"id": "t3"},  # missing key
    ]
    links = _resolve_row_links(rows, tmpl, fallback_template=fallback)
    assert links[0] == "/app/user/u-aaa"
    assert links[1] == "/app/task/t2"
    assert links[2] == "/app/task/t3"


def test_row_links_unwraps_hydrated_ref_dict_and_uuid() -> None:
    """#1603 dogfood v0.104.9: list JSON embeds full contact dict under FK key.

    CyFuture saw::

        hx-get="/app/contact/{'id': UUID('7048…'), 'first_name': 'Demo', …}"

    format_map must extract the scalar id, not str(dict).
    """
    from uuid import UUID

    uid = UUID("704816af-f88a-42eb-9ecf-e28308774039")
    tmpl = "/app/contact/{contact}"
    rows = [
        {
            "id": "task-1",
            "contact": {
                "id": uid,
                "first_name": "Demo",
                "last_name": "User",
            },
        },
        {"id": "task-2", "contact": {"name": "no-id-field"}},  # unwrappable
        {"id": "task-3", "contact": uid},  # bare UUID
        {"id": "task-4", "contact": str(uid)},  # already scalar
    ]
    links = _resolve_row_links(rows, tmpl)
    assert links[0] == f"/app/contact/{uid}"
    assert links[1] is None
    assert links[2] == f"/app/contact/{uid}"
    assert links[3] == f"/app/contact/{uid}"


def test_data_row_htmx_unwraps_nested_contact_dict() -> None:
    from uuid import UUID

    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    uid = UUID("704816af-f88a-42eb-9ecf-e28308774039")
    columns = [{"key": "title", "type": "str"}]
    item = {
        "id": "task-1",
        "title": "Call",
        "contact": {"id": uid, "first_name": "Demo"},
    }
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert f'hx-get="/app/contact/{uid}"' in html
    assert "first_name" not in html
    assert "UUID(" not in html
    assert "{contact}" not in html


def test_data_row_htmx_path_substitutes_open_via_fk() -> None:
    """#1603 dogfood: rich CRUD data-table path must format {contact} etc.

    CyFuture pilot saw literal ``hx-get="/app/contact/{contact}"`` because
    ``_data_row`` only did ``.replace("{id}", …)``. Row HTML must carry the
    substituted UUID when the via field is present.
    """
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-1", "title": "Call", "contact": "c-uuid-99"}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'hx-get="/app/contact/c-uuid-99"' in html or 'href="/app/contact/c-uuid-99"' in html
    assert "{contact}" not in html


def test_data_row_null_fk_falls_back_to_same_entity_detail() -> None:
    """#1614: null open-via FK → same-entity detail + click drill (not bare row)."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-2", "title": "Orphan", "contact": None}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/contact/{contact}",
        detail_url_fallback_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert "{contact}" not in html
    assert 'hx-get="/app/task/task-2"' in html
    assert 'hx-trigger="click"' in html


def test_delete_button_pins_hx_trigger_click() -> None:
    """#1613: delete must not inherit tbody load via implicitInheritance."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "task-3", "title": "X"}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'hx-delete="/api/tasks/task-3"' in html
    assert 'hx-trigger="click"' in html
    assert "hx-disinherit" in html


def test_simple_task_parses_open_via() -> None:
    """task_list triple-open: Task hub, assignee, creator (cycle 1590)."""
    appspec = load_project_appspec(SIMPLE)
    task_list = next(s for s in appspec.surfaces if s.name == "task_list")
    assert task_list.open_via == "id"
    assert task_list.open_entity == "Task"
    assert [(t.entity, t.via) for t in (task_list.open_via_targets or [])] == [
        ("Task", "id"),
        ("User", "assigned_to"),
        ("User", "created_by"),
    ]
    entity = appspec.get_entity("Task")
    tmpl = resolve_list_detail_url_template(task_list, entity)
    assert tmpl == "/app/task/{id}"


def test_simple_task_comments_triple_open() -> None:
    """task_comments triple-open: note hub, parent Task, author User (cycle 1607)."""
    appspec = load_project_appspec(SIMPLE)
    comments = next(s for s in appspec.surfaces if s.name == "task_comments")
    assert comments.open_via == "id"
    assert comments.open_entity == "TaskComment"
    assert [(t.entity, t.via) for t in (comments.open_via_targets or [])] == [
        ("TaskComment", "id"),
        ("Task", "task"),
        ("User", "author"),
    ]
    entity = appspec.get_entity("TaskComment")
    tmpl = resolve_list_detail_url_template(comments, entity)
    assert tmpl == "/app/taskcomment/{id}"
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    cands = resolve_list_detail_url_candidates(comments, entity)
    assert cands == [
        "/app/taskcomment/{id}",
        "/app/task/{task}",
        "/app/user/{author}",
    ]


def test_support_tickets_comment_list_triple_open() -> None:
    """comment_list triple-open: Comment hub, Ticket, author User (cycle 1604)."""
    appspec = load_project_appspec(SUPPORT)
    comment_list = next(s for s in appspec.surfaces if s.name == "comment_list")
    assert comment_list.open_via == "id"
    assert comment_list.open_entity == "Comment"
    assert [(t.entity, t.via) for t in (comment_list.open_via_targets or [])] == [
        ("Comment", "id"),
        ("Ticket", "ticket"),
        ("User", "author"),
    ]
    entity = appspec.get_entity("Comment")
    tmpl = resolve_list_detail_url_template(comment_list, entity)
    assert tmpl == "/app/comment/{id}"
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    cands = resolve_list_detail_url_candidates(comment_list, entity)
    assert cands == [
        "/app/comment/{id}",
        "/app/ticket/{ticket}",
        "/app/user/{author}",
    ]


def test_invoice_ops_line_item_list_triple_open() -> None:
    """line_item_list triple-open: line hub, Invoice, Tenant (cycle 1608)."""
    appspec = load_project_appspec(INVOICE_OPS)
    surf = next(s for s in appspec.surfaces if s.name == "line_item_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("LineItem", "id"),
        ("Invoice", "invoice"),
        ("Tenant", "tenant_id"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("LineItem")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/lineitem/{id}",
        "/app/invoice/{invoice}",
        "/app/tenant/{tenant_id}",
    ]


def test_invoice_ops_bank_list_triple_open() -> None:
    """supplier_bank_account_list triple-open: bank hub, Supplier, Tenant (cycle 1608)."""
    appspec = load_project_appspec(INVOICE_OPS)
    surf = next(s for s in appspec.surfaces if s.name == "supplier_bank_account_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("SupplierBankAccount", "id"),
        ("Supplier", "supplier"),
        ("Tenant", "tenant_id"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("SupplierBankAccount")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/supplierbankaccount/{id}",
        "/app/supplier/{supplier}",
        "/app/tenant/{tenant_id}",
    ]


def test_hr_managerlink_list_triple_open() -> None:
    """managerlink_list triple-open: link hub, report Person, manager Person (cycle 1609)."""
    appspec = load_project_appspec(HR)
    surf = next(s for s in appspec.surfaces if s.name == "managerlink_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("ManagerLink", "id"),
        ("Person", "report"),
        ("Person", "manager"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("ManagerLink")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/managerlink/{id}",
        "/app/person/{report}",
        "/app/person/{manager}",
    ]
    assert any(s.name == "managerlink_detail" and s.mode.value == "view" for s in appspec.surfaces)


def test_ops_dashboard_alert_list_dual_open() -> None:
    """alert_list dual-open: Alert hub + System parent (cycle 1613 acceptance)."""
    appspec = load_project_appspec(OPS)
    surf = next(s for s in appspec.surfaces if s.name == "alert_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("Alert", "id"),
        ("System", "system"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("Alert")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/alert/{id}",
        "/app/system/{system}",
    ]
    assert getattr(entity, "display_field", None) == "message"


def test_llm_classification_list_dual_open() -> None:
    """classification_list dual-open: AI run hub + parent Ticket (cycle 1614 journey)."""
    appspec = load_project_appspec(LLM)
    surf = next(s for s in appspec.surfaces if s.name == "classification_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("TicketClassification", "id"),
        ("Ticket", "ticket"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("TicketClassification")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/ticketclassification/{id}",
        "/app/ticket/{ticket}",
    ]
    # Goal B conversation (cycle 1653): queue titles are AI draft replies, not category shells.
    assert getattr(entity, "display_field", None) == "suggested_response"


def test_contact_manager_engagement_letter_list_dual_open() -> None:
    """engagement_letter_list dual-open: letter hub + Contact parent (cycle 1615 story_walk)."""
    appspec = load_project_appspec(CONTACT)
    surf = next(s for s in appspec.surfaces if s.name == "engagement_letter_list")
    assert [(t.entity, t.via) for t in (surf.open_via_targets or [])] == [
        ("EngagementLetter", "id"),
        ("Contact", "contact"),
    ]
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    entity = appspec.get_entity("EngagementLetter")
    cands = resolve_list_detail_url_candidates(surf, entity)
    assert cands == [
        "/app/engagementletter/{id}",
        "/app/contact/{contact}",
    ]
    # Goal B document depth: scope_summary is the document title buyers scan
    # (MSA/NDA/retainer), not only the counterparty party string.
    assert getattr(entity, "display_field", None) == "scope_summary"
    # Home composition queue (draft|sent) is product path for ST-009 / Goal B.
    home = next(w for w in appspec.workspaces if w.name == "home")
    assert any(r.name == "composition" for r in home.regions)


def test_resolve_first_non_null_candidates() -> None:
    """#1600 P2: multi-hop open produces ordered candidate templates."""
    surface = ir.SurfaceSpec(
        name="sub_list",
        title="Subs",
        entity_ref="ClientSubscription",
        mode=ir.SurfaceMode.LIST,
        open_via="company",
        open_entity="Company",
        open_via_targets=[
            ir.OpenViaTarget(via="company", entity="Company"),
            ir.OpenViaTarget(via="sole_trader", entity="SoleTrader"),
            ir.OpenViaTarget(via="partnership", entity="Partnership"),
        ],
    )
    entity = ir.EntitySpec(
        name="ClientSubscription",
        title="Sub",
        fields=[
            ir.FieldSpec(
                name="company",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Company"),
            ),
            ir.FieldSpec(
                name="sole_trader",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="SoleTrader"),
            ),
            ir.FieldSpec(
                name="partnership",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Partnership"),
            ),
        ],
    )
    from dazzle.page.open_via import resolve_list_detail_url_candidates

    cands = resolve_list_detail_url_candidates(surface, entity)
    assert cands == [
        "/app/company/{company}",
        "/app/soletrader/{sole_trader}",
        "/app/partnership/{partnership}",
    ]
    assert resolve_list_detail_url_template(surface, entity) == cands[0]


def test_row_links_first_non_null_picks_second_hop() -> None:
    """#1600 P2: null company → sole_trader hop; all null → fallback."""
    cands = (
        "/app/company/{company}",
        "/app/soletrader/{sole_trader}",
        "/app/partnership/{partnership}",
    )
    fallback = "/app/clientsubscription/{id}"
    rows = [
        {"id": "s1", "company": "co-1", "sole_trader": None, "partnership": None},
        {"id": "s2", "company": None, "sole_trader": "st-9", "partnership": None},
        {"id": "s3", "company": None, "sole_trader": None, "partnership": "p-2"},
        {"id": "s4", "company": None, "sole_trader": None, "partnership": None},
    ]
    links = _resolve_row_links(
        rows,
        cands[0],
        fallback_template=fallback,
        candidate_templates=cands,
    )
    assert links[0] == "/app/company/co-1"
    assert links[1] == "/app/soletrader/st-9"
    assert links[2] == "/app/partnership/p-2"
    assert links[3] == "/app/clientsubscription/s4"


def test_parse_open_first_non_null_bare_fields() -> None:
    """Parse ``open: first_non_null(company, sole_trader)``."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    dsl = """
module test.core
app test_app "T"

entity Company "Company":
  id: uuid pk
  name: str(100)

entity SoleTrader "Sole Trader":
  id: uuid pk
  name: str(100)

entity Sub "Sub":
  id: uuid pk
  company: ref Company
  sole_trader: ref SoleTrader

surface sub_list "Subs":
  uses entity Sub
  mode: list
  open: first_non_null(company, sole_trader)
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.open_via == "company"
    assert surface.open_entity is None  # bare fields — entity inferred later
    assert len(surface.open_via_targets) == 2
    assert surface.open_via_targets[0].via == "company"
    assert surface.open_via_targets[0].entity is None
    assert surface.open_via_targets[1].via == "sole_trader"


def test_parse_open_pipe_chain() -> None:
    """Parse ``open: Company via company | SoleTrader via sole_trader``."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    dsl = """
module test.core
app test_app "T"

entity Company "Company":
  id: uuid pk

entity SoleTrader "Sole Trader":
  id: uuid pk

entity Sub "Sub":
  id: uuid pk
  company: ref Company
  sole_trader: ref SoleTrader

surface sub_list "Subs":
  uses entity Sub
  mode: list
  open: Company via company | SoleTrader via sole_trader
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.open_via == "company"
    assert surface.open_entity == "Company"
    assert [(t.entity, t.via) for t in surface.open_via_targets] == [
        ("Company", "company"),
        ("SoleTrader", "sole_trader"),
    ]


def test_parse_multiple_open_lines_merge() -> None:
    """Cycle 1530 / AUD-007 — two open: lines merge; no longer last-wins."""
    from dazzle.core.dsl_parser_impl import parse_dsl

    dsl = """
module test.core
app test_app "T"

entity Letter "Letter":
  id: uuid pk
  contact: ref Contact

entity Contact "Contact":
  id: uuid pk

surface letter_list "Letters":
  uses entity Letter
  mode: list
  open: Letter via id
  open: Contact via contact
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    surface = fragment.surfaces[0]
    assert surface.open_via == "id"
    assert surface.open_entity == "Letter"
    assert [(t.entity, t.via) for t in surface.open_via_targets] == [
        ("Letter", "id"),
        ("Contact", "contact"),
    ]


def test_data_row_first_non_null_htmx() -> None:
    """Rich data-table path uses multi-hop candidates."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {
        "id": "s2",
        "title": "ST client",
        "company": None,
        "sole_trader": "st-uuid",
        "partnership": None,
    }
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/company/{company}",
        detail_url_candidates=(
            "/app/company/{company}",
            "/app/soletrader/{sole_trader}",
            "/app/partnership/{partnership}",
        ),
        detail_url_fallback_template="/app/sub/{id}",
        entity_name="Sub",
        api_endpoint="/api/subs",
    )
    assert 'hx-get="/app/soletrader/st-uuid"' in html
    assert "{company}" not in html


def test_resolve_row_open_chain_dual_hops() -> None:
    """All resolvable dual-open candidates, not first-only (url, via) pairs."""
    from dazzle.render.fragment.region._row_links import _resolve_row_open_chain

    item = {"id": "t1", "assigned_to": "u-9", "title": "Work"}
    chain = _resolve_row_open_chain(
        item,
        candidate_templates=(
            "/app/task/{id}",
            "/app/user/{assigned_to}",
        ),
    )
    assert chain == (("/app/task/t1", "id"), ("/app/user/u-9", "assigned_to"))


def test_data_row_dual_open_emits_secondary_context_hop() -> None:
    """Dual-open (hub | parent): primary drill + secondary context action (cycle 1566)."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {"id": "t1", "title": "Ship dual-open", "assigned_to": "u-abc"}
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/task/{id}",
        detail_url_candidates=(
            "/app/task/{id}",
            "/app/user/{assigned_to}",
        ),
        detail_url_fallback_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'hx-get="/app/task/t1"' in html
    assert 'data-dz-open-secondary="/app/user/u-abc"' in html
    assert "dz-tr-open-secondary" in html
    assert 'data-dazzle-action="Task.open_context"' in html
    assert 'href="/app/user/u-abc"' in html
    # Cycle 1571: entity-aware labels + agent attrs
    assert 'data-dz-open-entity="User"' in html
    assert 'data-dz-open-context="/app/user/u-abc"' in html
    # Cycle 1577: via-field relation labels + open-chain discovery
    assert 'data-dz-open-via="assigned_to"' in html
    assert 'title="Open User via assigned to"' in html
    assert 'aria-label="Open User via assigned to for Ship dual-open"' in html
    assert 'data-dz-open-chain="/app/task/t1 /app/user/u-abc"' in html
    # Cycle 1583: chain-via + primary hop parity
    assert 'data-dz-open-chain-via="id assigned_to"' in html
    assert 'title="Open Task"' in html  # primary via id
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-entity="Task"' in html
    # Cycle 1589: hop role/index + row hop count
    assert 'data-dz-open-role="primary"' in html
    assert 'data-dz-open-hop="0"' in html
    assert 'data-dz-open-role="context"' in html
    assert 'data-dz-open-hop="1"' in html
    assert 'data-dz-open-hops="2"' in html
    # Cycle 1594: hop phrases as data attrs (attr-first agents)
    assert 'data-dz-open-label="Open Task"' in html
    assert 'data-dz-open-label="Open User via assigned to"' in html
    assert 'data-dz-open-chain-label="Open Task | Open User via assigned to"' in html
    # Cycle 1599: ordered entity display names on the row
    assert 'data-dz-open-chain-entity="Task | User"' in html


def test_entity_label_from_detail_url() -> None:
    from dazzle.render.fragment.region._row_links import (
        entity_label_from_detail_url,
        field_label_from_via,
        open_hop_label,
        via_field_from_template,
    )

    assert entity_label_from_detail_url("/app/user/u-9") == "User"
    assert entity_label_from_detail_url("/app/payment-attempt/x") == "Payment Attempt"
    assert entity_label_from_detail_url("/app/supplier_bank_account/1") == "Supplier Bank Account"
    assert entity_label_from_detail_url("") == "Related"
    assert via_field_from_template("/app/user/{assigned_to}") == "assigned_to"
    assert via_field_from_template("/app/task/{id}") == "id"
    assert field_label_from_via("assigned_to") == "Assigned to"
    assert open_hop_label("User", "assigned_to") == "Open User via assigned to"
    assert open_hop_label("Task", "id") == "Open Task"
    assert open_hop_label("Company", "company") == "Open Company"


def test_data_row_multi_open_emits_all_context_hops() -> None:
    """open: A|B|C → primary + two labeled context hops (cycle 1571/1577)."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    columns = [{"key": "title", "type": "str"}]
    item = {
        "id": "pa1",
        "title": "Attempt",
        "invoice": "inv-1",
        "supplier": "sup-9",
    }
    html = render_data_row(
        columns,
        item,
        RowCapabilities(drill=True),
        detail_url_template="/app/payment-attempt/{id}",
        detail_url_candidates=(
            "/app/payment-attempt/{id}",
            "/app/invoice/{invoice}",
            "/app/supplier/{supplier}",
        ),
        entity_name="PaymentAttempt",
        api_endpoint="/api/payment-attempts",
    )
    assert 'hx-get="/app/payment-attempt/pa1"' in html
    assert 'data-dz-open-secondary="/app/invoice/inv-1"' in html
    assert 'data-dz-open-entity="Invoice"' in html
    assert 'data-dz-open-entity="Supplier"' in html
    assert 'data-dz-open-via="invoice"' in html
    assert 'data-dz-open-via="supplier"' in html
    # via name matches entity slug → title stays "Open Invoice" (no redundant via)
    assert 'title="Open Invoice"' in html
    assert 'title="Open Supplier"' in html
    assert html.count("dz-tr-open-secondary") == 2
    # Only the first extra hop keeps the legacy secondary attr
    assert html.count("data-dz-open-secondary=") == 2  # anchor + tr mirror
    assert 'data-dz-open-context="/app/supplier/sup-9"' in html
    assert (
        'data-dz-open-chain="/app/payment-attempt/pa1 /app/invoice/inv-1 /app/supplier/sup-9"'
        in html
    )
    # Cycle 1583: via fields parallel to chain URLs; primary hop labeled
    assert 'data-dz-open-chain-via="id invoice supplier"' in html
    assert 'title="Open Payment Attempt"' in html
    # Cycle 1589: three hops → indices 0/1/2 + hops count
    assert 'data-dz-open-hops="3"' in html
    assert 'data-dz-open-hop="2"' in html
    # Cycle 1594: ordered hop phrases on the row
    assert 'data-dz-open-chain-label="Open Payment Attempt | Open Invoice | Open Supplier"' in html
    assert 'data-dz-open-label="Open Payment Attempt"' in html
    assert 'data-dz-open-label="Open Invoice"' in html
    assert 'data-dz-open-label="Open Supplier"' in html
    # Cycle 1599: entity chain (multi-word labels stay pipe-joined)
    assert 'data-dz-open-chain-entity="Payment Attempt | Invoice | Supplier"' in html


def test_validate_open_via_wrong_mode_errors() -> None:
    from dazzle.core.validation.surfaces import validate_surfaces

    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(
            entities=[
                ir.EntitySpec(
                    name="Task",
                    title="Task",
                    fields=[
                        ir.FieldSpec(
                            name="assigned_to",
                            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
                        ),
                    ],
                )
            ]
        ),
        surfaces=[
            ir.SurfaceSpec(
                name="task_detail",
                title="Detail",
                entity_ref="Task",
                mode=ir.SurfaceMode.VIEW,
                open_via="assigned_to",
                open_entity="User",
            )
        ],
    )
    errors, _ = validate_surfaces(appspec)
    assert any("open" in e.lower() and "list" in e.lower() for e in errors)
