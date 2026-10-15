"""Goal B depth pins for ``examples/invoice_ops``, read from the parsed AppSpec.

Conversation, document, media, command density, org structure and empty-region
honesty, plus the #1666/#1668/#1669 steals, as one table per kind of fact:
workspace regions (exact ordered ``name display source``), first-persona focus,
region filters and other clauses, metric counts, entity and surface shape, and
demo-seed rules. An exact region list subsumes the old order, presence and
absence checks (no ``media_shelf`` on money desks, no chart or trail voids).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.appspec_loader import load_project_appspec

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "invoice_ops"
SEEDS = EXAMPLE / "dsl" / "seeds" / "demo_data"


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_project_appspec(EXAMPLE)


def _cond(c: Any) -> str | None:
    """Render an IR condition back to DSL-shaped text."""
    if c is None:
        return None
    if c.comparison is not None:
        cmp, v = c.comparison, c.comparison.value
        if v.date_expr is not None:
            val = v.date_expr.kind.value
        else:
            val = "null" if v.literal is None else str(v.literal)
        return f"{cmp.field} {cmp.operator.value} {val}"

    def side(x: Any) -> str:
        s = _cond(x) or ""
        return f"({s})" if x.left is not None and x.operator != c.operator else s

    return f"{side(c.left)} {c.operator.value} {side(c.right)}"


def _count(agg: Any) -> str:
    where = f" where {_cond(agg.where)}" if agg.where is not None else ""
    return f"{agg.func}({agg.entity}{where})"


def _ws(spec: Any, name: str) -> Any:
    return {w.name: w for w in spec.workspaces}[name]


def _region(spec: Any, ws: str, region: str) -> Any:
    return {r.name: r for r in _ws(spec, ws).regions}[region]


_DOC = "InvoiceDocument"
_WATCHES = (
    "remittances credit_memos debit_memos vendor_statements packing_slips ach_authorizations"
    " wire_instructions lien_waivers insurance_certificates form_w9s"
)
_RAILS = "compliance_drafts match_evidence settle_rail adjustment_rail bank_rail tax_identity"


def _docq(names: str) -> str:
    """``name:queue:InvoiceDocument`` tokens for a run of document watches."""
    return " ".join(f"{n}:queue:{_DOC}" for n in names.split())


# workspace -> exact ordered ``name:display:source`` tokens.
REGIONS: dict[str, str] = {
    "pay_desk": "settle_metrics:metrics:Invoice past_due:queue:Invoice ready_to_pay:queue:Invoice"
    " draft_invoice_queue:queue:Invoice awaiting_approval_queue:queue:Invoice"
    f" document_pulse:metrics:{_DOC} {_docq('draft_packets ' + _RAILS + ' ' + _WATCHES)}"
    f" {_docq('payment_confirmations composition')} disputed_queue:queue:Invoice"
    " live_conversation:conversation:InvoiceNote settle_board:kanban:Invoice",
    "finance_ops": f"packet_covers:grid:{_DOC} ops_metrics:metrics:Invoice"
    f" document_pulse:metrics:{_DOC} {_docq('draft_packets ' + _RAILS)}"
    f" {_docq('po_packets tax_certificates goods_receipts credit_memos remittances')}"
    f" {_docq('dispute_packets ' + ' '.join(_WATCHES.split()[2:]) + ' composition')}"
    " awaiting_approval:queue:Invoice ready_to_pay:queue:Invoice past_due:queue:Invoice"
    " line_composition:queue:LineItem live_conversation:conversation:InvoiceNote"
    " disputed_queue:queue:Invoice ops_board:kanban:Invoice",
    "my_invoices": "my_pipeline:metrics:Invoice document_pulse:metrics:LineItem"
    " composition:queue:LineItem drafts:queue:Invoice in_flight:queue:Invoice"
    " rejected:queue:Invoice disputed:queue:Invoice awaiting_settle:queue:Invoice"
    " my_status_board:kanban:Invoice suppliers_nearby:queue:Supplier",
    "approval_desk": "approval_load:metrics:Invoice awaiting_approval:queue:Invoice"
    f" document_pulse:metrics:{_DOC}"
    f" {_docq('match_evidence goods_receipts po_packets tax_certificates composition')}"
    " live_conversation:conversation:InvoiceNote approval_board:kanban:Invoice"
    " suppliers_nearby:queue:Supplier",
    "audit_review": f"document_pulse:metrics:{_DOC} packet_covers:grid:{_DOC}"
    f" composition:queue:{_DOC} disputed_queue:queue:Invoice"
    " payment_attempts:timeline:PaymentAttempt settled_invoices:queue:Invoice"
    " audit_mix:bar_chart:Invoice audit_board:kanban:Invoice",
    "suppliers_desk": "vendor_pulse:metrics:Supplier by_region:kanban:Supplier"
    " by_supplier:kanban:Invoice roster:queue:Supplier bank_refs:queue:SupplierBankAccount"
    " recent_invoices:queue:Invoice",
    "team_desk": "team_pulse:metrics:User by_title:kanban:User by_department:queue:User"
    " people:queue:User open_invoices:queue:Invoice org_hint:status_list:None",
    "line_items_desk": "line_pulse:metrics:LineItem unmatched_lines:queue:LineItem"
    " partial_lines:queue:LineItem po_match_board:kanban:LineItem composition:queue:LineItem"
    " open_documents:queue:Invoice invoice_trail:timeline:Invoice",
    "dispute_desk": f"dispute_pulse:metrics:Invoice document_pulse:metrics:{_DOC}"
    f" dispute_packets:queue:{_DOC} disputed_queue:queue:Invoice"
    " settle_pipeline:kanban:Invoice payment_attempts:timeline:PaymentAttempt"
    " status_mix:bar_chart:Invoice",
}


@pytest.mark.parametrize("ws", sorted(REGIONS))
def test_workspace_regions(spec: Any, ws: str) -> None:
    got = [f"{r.name}:{r.display}:{r.source}" for r in _ws(spec, ws).regions]
    assert got == REGIONS[ws].split()


_SETTLE = "settle_metrics, past_due, ready_to_pay, draft_invoice_queue, awaiting_approval_queue,"
_SETTLE += (
    " document_pulse, draft_packets, settle_rail, match_evidence, compliance_drafts, composition"
)
_OPS = "packet_covers, ops_metrics, document_pulse, draft_packets, settle_rail, match_evidence,"
_OPS += " compliance_drafts, composition, past_due, awaiting_approval"

# workspace -> (personas with a variant, focus of the first variant)
FOCUS: dict[str, tuple[str, str]] = {
    "pay_desk": ("finance, finance_admin", _SETTLE),
    "finance_ops": ("finance_admin, tenant_admin, finance, approver, auditor, requester", _OPS),
    "my_invoices": (
        "requester",
        "my_pipeline, document_pulse, drafts, in_flight, rejected, disputed, awaiting_settle,"
        " my_status_board",
    ),
    "approval_desk": (
        "approver, finance_admin",
        "approval_load, awaiting_approval, document_pulse, match_evidence, goods_receipts,"
        " po_packets, composition, live_conversation",
    ),
    "audit_review": (
        "auditor, finance_admin, tenant_admin",
        "document_pulse, packet_covers, composition, disputed_queue, payment_attempts,"
        " settled_invoices",
    ),
    "suppliers_desk": (
        "finance, finance_admin, tenant_admin, approver",
        "vendor_pulse, by_region, by_supplier, roster, bank_refs",
    ),
    "team_desk": (
        "tenant_admin, finance_admin, auditor",
        "team_pulse, by_title, by_department, people",
    ),
    "line_items_desk": (
        "requester, finance, finance_admin, auditor",
        "line_pulse, unmatched_lines, partial_lines, composition",
    ),
    "dispute_desk": (
        "finance, finance_admin, auditor, tenant_admin",
        "dispute_pulse, document_pulse, dispute_packets, disputed_queue, settle_pipeline,"
        " payment_attempts",
    ),
}


@pytest.mark.parametrize("ws", sorted(FOCUS))
def test_workspace_focus(spec: Any, ws: str) -> None:
    variants = _ws(spec, ws).ux.persona_variants
    personas, focus = FOCUS[ws]
    assert ", ".join(v.persona for v in variants) == personas
    assert ", ".join(variants[0].focus) == focus


_KINDS = {
    "remittances": "remittance",
    "credit_memos": "credit_memo",
    "debit_memos": "debit_memo",
    "vendor_statements": "vendor_statement",
    "packing_slips": "packing_slip",
    "ach_authorizations": "ach_authorization",
    "wire_instructions": "wire_instructions",
    "lien_waivers": "lien_waiver",
    "insurance_certificates": "insurance_certificate",
    "form_w9s": "form_w9",
    "po_packets": "po_packet",
    "tax_certificates": "tax_certificate",
    "goods_receipts": "goods_receipt",
    "payment_confirmations": "payment_confirmation",
    "dispute_packets": "dispute_packet",
}


def _any_kind(*kinds: str) -> str:
    return " or ".join(f"doc_kind = {k}" for k in kinds)


# Every InvoiceDocument watch/rail filter, wherever the region appears. A pure
# kind watch filters exactly its kind; a rail is the exact compound.
DOC_FILTERS: dict[str, str] = {
    **{region: f"doc_kind = {kind}" for region, kind in _KINDS.items()},
    "packet_covers": "preview_url != null",
    "draft_packets": "status = draft",
    "compliance_drafts": "status = draft and ("
    + _any_kind("form_w9", "insurance_certificate", "tax_certificate", "lien_waiver")
    + " or doc_kind = ach_authorization)",
    "match_evidence": _any_kind("po_packet", "goods_receipt", "packing_slip"),
    "settle_rail": _any_kind("remittance", "payment_confirmation"),
    "adjustment_rail": _any_kind("credit_memo", "debit_memo"),
    "bank_rail": _any_kind("ach_authorization", "wire_instructions"),
    "tax_identity": _any_kind("form_w9", "tax_certificate"),
}


@pytest.mark.parametrize(
    "ws", ["pay_desk", "finance_ops", "approval_desk", "audit_review", "dispute_desk"]
)
def test_document_region_filters(spec: Any, ws: str) -> None:
    for r in _ws(spec, ws).regions:
        if r.source == _DOC and r.name in DOC_FILTERS:
            assert _cond(r.filter) == DOC_FILTERS[r.name], (ws, r.name)


# Count-tile key -> what it counts; every document_pulse key must be one of these,
# and a tile named after a watch counts exactly what the watch lists.
DOC_COUNTS: dict[str, str | None] = {
    **{k: v for k, v in DOC_FILTERS.items() if k not in {"packet_covers", "draft_packets"}},
    "documents": None,
    "published": "status = published",
    "draft": "status = draft",
    "tax_certs": DOC_FILTERS["tax_certificates"],
    "po_packs": DOC_FILTERS["po_packets"],
    "pay_confirms": DOC_FILTERS["payment_confirmations"],
}


@pytest.mark.parametrize(
    ("ws", "keys"),
    [
        pytest.param(
            "finance_ops",
            "documents published draft tax_certs po_packs goods_receipts credit_memos debit_memos"
            " vendor_statements packing_slips ach_authorizations wire_instructions lien_waivers"
            " insurance_certificates form_w9s compliance_drafts match_evidence settle_rail"
            " adjustment_rail bank_rail tax_identity remittances dispute_packets",
            id="finance_ops",
        ),
        pytest.param(
            "pay_desk",
            "documents published draft pay_confirms settle_rail adjustment_rail bank_rail"
            " tax_identity credit_memos debit_memos vendor_statements packing_slips"
            " ach_authorizations wire_instructions lien_waivers insurance_certificates form_w9s"
            " compliance_drafts match_evidence remittances",
            id="pay_desk",
        ),
        pytest.param(
            "approval_desk",
            "documents published tax_certs po_packs goods_receipts match_evidence",
            id="approval_desk",
        ),
        pytest.param(
            "dispute_desk", "dispute_packets published draft documents", id="dispute_desk"
        ),
    ],
)
def test_document_pulse_counts(spec: Any, ws: str, keys: str) -> None:
    aggs = _region(spec, ws, "document_pulse").aggregates
    assert list(aggs) == keys.split()
    for key, agg in aggs.items():
        where = f" where {DOC_COUNTS[key]}" if DOC_COUNTS[key] else ""
        assert _count(agg) == f"count({_DOC}{where})", (ws, key)


DOC_HUB = "invoice_document_detail"

# (workspace, region) -> {clause: expected}; filters are rendered DSL text.
CLAUSES: list[tuple[str, str, dict[str, Any]]] = [
    ("pay_desk", "past_due", {"filter": "status = approved and due_date < today", "limit": 3}),
    ("pay_desk", "ready_to_pay", {"filter": "status = approved and due_date >= today"}),
    ("pay_desk", "draft_invoice_queue", {"filter": "status = draft", "limit": 3}),
    ("pay_desk", "awaiting_approval_queue", {"filter": "status = submitted", "limit": 3}),
    ("finance_ops", "packet_covers", {"sort": "created_at desc", "action": DOC_HUB}),
    ("finance_ops", "past_due", {"sort": "due_date asc"}),
    ("audit_review", "payment_attempts", {"filter": "created_at >= today"}),
    ("my_invoices", "rejected", {"filter": "status = rejected"}),
    ("my_invoices", "disputed", {"filter": "status = disputed"}),
    ("my_invoices", "awaiting_settle", {"filter": "status = approved"}),
    (
        "my_invoices",
        "my_status_board",
        {
            "filter": "status = draft or status = submitted or status = rejected"
            " or status = disputed or status = approved"
        },
    ),
    ("dispute_desk", "disputed_queue", {"filter": "status = disputed"}),
    ("team_desk", "by_title", {"group_by": "job_title"}),
    ("suppliers_desk", "by_region", {"group_by": "region"}),
    ("suppliers_desk", "by_supplier", {"group_by": "supplier"}),
    ("line_items_desk", "unmatched_lines", {"filter": "po_match = unmatched"}),
    ("line_items_desk", "partial_lines", {"filter": "po_match = partial"}),
    ("line_items_desk", "po_match_board", {"group_by": "po_match"}),
]
for _r in ("past_due", "ready_to_pay"):
    CLAUSES.append(("pay_desk", _r, {"limit": 3, "transitions": "none"}))


@pytest.mark.parametrize(("ws", "region", "clauses"), CLAUSES, ids=lambda v: str(v)[:40])
def test_region_clauses(spec: Any, ws: str, region: str, clauses: dict[str, Any]) -> None:
    r = _region(spec, ws, region)
    actual = {
        "filter": _cond(r.filter),
        "sort": ", ".join(f"{s.field} {s.direction}" for s in r.sort),
        "limit": r.limit,
        "group_by": r.group_by,
        "transitions": r.transitions,
        "action": r.action,
    }
    assert {k: actual[k] for k in clauses} == clauses


METRICS: list[tuple[str, str, dict[str, str]]] = [
    (
        "pay_desk",
        "settle_metrics",
        {
            "ready": "count(Invoice where status = approved)",
            "on_time": "count(Invoice where status = approved and due_date >= today)",
            "past_due": "count(Invoice where status = approved and due_date < today)",
            "disputed": "count(Invoice where status = disputed)",
        },
    ),
    (
        "finance_ops",
        "ops_metrics",
        {
            "past_due": "count(Invoice where due_date < today and status != paid"
            " and status != rejected and status != draft)"
        },
    ),
    (
        "dispute_desk",
        "dispute_pulse",
        {
            "disputed": "count(Invoice where status = disputed)",
            "with_reason": "count(Invoice where status = disputed and dispute_reason != null)",
        },
    ),
    (
        "line_items_desk",
        "line_pulse",
        {k: f"count(LineItem where po_match = {k})" for k in ("matched", "unmatched", "partial")},
    ),
]


@pytest.mark.parametrize(("ws", "region", "counts"), METRICS, ids=lambda v: str(v)[:30])
def test_metric_counts(spec: Any, ws: str, region: str, counts: dict[str, str]) -> None:
    aggs = {k: _count(v) for k, v in _region(spec, ws, region).aggregates.items()}
    if region == "settle_metrics":  # settlement only: no intake / thread tiles
        assert aggs == counts
    else:
        assert {k: aggs[k] for k in counts} == counts


def test_bar_charts_stay_in_the_app(spec: Any) -> None:
    """Hero prunes must not leave ``bar_chart`` uncovered in this probe app."""
    charts = [r for w in spec.workspaces for r in w.regions if str(r.display) == "bar_chart"]
    assert len(charts) >= 2


def _type(f: Any) -> str:
    t = f.type
    kind = t.kind.value
    if t.enum_values:
        kind = f"enum[{', '.join(t.enum_values)}]"
    elif t.max_length:
        kind = f"{kind}({t.max_length})"
    elif t.precision:
        kind = f"{kind}({t.precision},{t.scale})"
    elif t.ref_entity:
        kind = f"ref {t.ref_entity}"
    mods = " ".join(m.value for m in f.modifiers)
    default = f"={f.default}" if f.default is not None else ""
    return f"{kind}{default}{' ' + mods if mods else ''}"


_DOC_KINDS = (
    "remittance credit_memo debit_memo vendor_statement packing_slip ach_authorization"
    " wire_instructions lien_waiver insurance_certificate form_w9 po_packet tax_certificate"
    " payment_confirmation goods_receipt dispute_packet"
).split()

ENTITY_FIELDS: list[tuple[str, str, str]] = [
    ("Invoice", "due_date", "date optional"),
    ("Invoice", "amount", "decimal(15,2) required"),
    ("Invoice", "supplier", "ref Supplier required"),
    ("Invoice", "dispute_reason", "text optional"),
    ("Invoice", "approval_exception", "text optional"),
    ("LineItem", "description", "str(200) required"),
    ("LineItem", "tax_code", "str(20) optional"),
    ("LineItem", "po_match", "enum[matched, partial, unmatched, not_applicable]=not_applicable"),
    ("InvoiceDocument", "headline", "str(200) required"),
    ("InvoiceDocument", "doc_kind", f"enum[{', '.join(_DOC_KINDS)}]=remittance"),
    ("InvoiceDocument", "status", "enum[draft, published, archived]=draft"),
    ("InvoiceDocument", "preview_url", "url"),
    ("InvoiceNote", "body", "text required"),
    ("User", "department", "str(50)"),
    ("User", "job_title", "str(80)"),
    ("PaymentAttempt", "status", "enum[pending, succeeded, failed]=pending"),
]


@pytest.mark.parametrize(("entity", "field", "shape"), ENTITY_FIELDS, ids=lambda v: str(v))
def test_entity_field(spec: Any, entity: str, field: str, shape: str) -> None:
    e = {x.name: x for x in spec.domain.entities}[entity]
    assert _type({f.name: f for f in e.fields}[field]) == shape


@pytest.mark.parametrize(
    ("entity", "display_field", "repr_fields"),
    [
        (
            "Invoice",
            "invoice_number",
            "invoice_number supplier amount currency due_date status dispute_reason",
        ),
        ("LineItem", "description", None),
        ("InvoiceDocument", "headline", "invoice headline doc_kind status author preview_url"),
        ("InvoiceNote", "body", "invoice author body"),
    ],
)
def test_entity_identity(
    spec: Any, entity: str, display_field: str, repr_fields: str | None
) -> None:
    e = {x.name: x for x in spec.domain.entities}[entity]
    assert e.display_field == display_field
    assert (" ".join(e.fitness.repr_fields) if e.fitness else None) == repr_fields


def test_entity_lifecycles_and_absences(spec: Any) -> None:
    """#1668 spoken exception guards approve; #1669 theory adds no taste entities."""
    entities = {e.name: e for e in spec.domain.entities}
    assert {"CreditNote", "NeedsYou"}.isdisjoint(entities)
    approve = next(
        t
        for t in entities["Invoice"].state_machine.transitions
        if (t.from_state, t.to_state) == ("submitted", "approved")
    )
    assert [(g.requires_role, g.requires_field) for g in approve.guards] == [
        ("approver", None),
        (None, "approval_exception"),
    ]
    doc_moves = entities["InvoiceDocument"].state_machine.transitions
    assert {("draft", "published"), ("published", "archived")} <= {
        (t.from_state, t.to_state) for t in doc_moves
    }
    titles = {n: entities[n].title for n in ("InvoiceDocument", "LineItem", "PaymentAttempt")}
    assert titles == {
        "InvoiceDocument": "Invoice Document",
        "LineItem": "Line Item",
        "PaymentAttempt": "Payment Attempt",
    }
    # finance and finance_admin list and read packets and lines (finance_ops home).
    for name in ("InvoiceDocument", "LineItem"):
        rules = {r.operation.value: r for r in entities[name].access.permissions}
        for op in ("list", "read"):
            assert {"finance", "finance_admin"} <= _roles(rules[op].condition), (name, op)


def _roles(c: Any) -> set[str]:
    if c is None:
        return set()
    own = {c.role_check.role_name} if c.role_check is not None else set()
    return own | _roles(c.left) | _roles(c.right)


SURFACE_FIELDS: list[tuple[str, str]] = [
    (
        "invoice_list",
        "invoice_number:Number supplier:Supplier amount:Amount due_date:Due currency:Currency"
        " status:Status dispute_reason:Dispute submitted_by:Submitted By",
    ),
    (
        "invoice_document_list",
        "preview_url:Cover headline:Headline invoice:Invoice doc_kind:Kind status:Status"
        " author:Author created_at:Created",
    ),
    (
        "payment_attempt_detail",
        "attempt_number:Attempt status:Status invoice:Invoice tenant_id:Tenant"
        " provider_reference:Provider reference failure_reason:Failure Reason",
    ),
]


@pytest.mark.parametrize(("surface", "fields"), SURFACE_FIELDS, ids=lambda v: str(v)[:24])
def test_surface_fields(spec: Any, surface: str, fields: str) -> None:
    s = {x.name: x for x in spec.surfaces}[surface]
    got = " ".join(f"{e.field_name}:{e.label}" for sec in s.sections for e in sec.elements)
    assert got == fields


def test_surface_hubs(spec: Any) -> None:
    s = {x.name: x for x in spec.surfaces}
    hub = s["invoice_detail"]
    labels = {(e.field_name, e.label) for sec in hub.sections for e in sec.elements}
    assert {("due_date", "Due Date"), ("dispute_reason", "Dispute Reason")} <= labels
    groups = {g.name: (str(g.display), g.show, g.columns) for g in hub.related_groups}
    assert groups["lines"] == (
        "queue",
        ["LineItem"],
        ["description", "quantity", "unit_amount", "tax_code", "po_match"],
    )
    assert groups["documents"][:2] == ("queue", ["InvoiceDocument"])
    assert groups["discussion"] == (
        "conversation",
        ["InvoiceNote"],
        ["body", "author", "created_at"],
    )
    docs = s["invoice_document_list"]
    assert [(t.via, t.entity) for t in docs.open_via_targets] == [
        ("id", "InvoiceDocument"),
        ("invoice", "Invoice"),
    ]
    assert "invoice_document_detail" in s
    assert s["payment_attempt_detail"].related_groups == []  # three doors, no folio (#1666)
    assert (s["user_list"].ux.filter, s["supplier_list"].ux.filter) == (
        ["department", "job_title"],
        ["region"],
    )
    assert s["supplier_list"].ux.search == ["name", "contact_email", "region"]


def test_finance_persona_reaches_dispute_desk(spec: Any) -> None:
    nav = {n.name: n for n in spec.navs}["finance_nav"]
    assert "dispute_desk" in [i.entity for g in nav.groups for i in g.items]


def _rows(name: str) -> list[dict[str, Any]]:
    text = (SEEDS / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _of(rows: list[dict[str, Any]], key: str, *values: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get(key) in values]


def _invoices() -> None:
    rows = _rows("Invoice")
    assert len(rows) >= 12
    for r in rows:
        assert len(str(r["due_date"])) == 10 and str(r["due_date"])[4] == "-"
    open_past = [
        r
        for r in rows
        if r["due_date"] < "2026-08-11" and r["status"] not in {"paid", "rejected", "draft"}
    ]
    assert len(open_past) >= 3 and sum(r["due_date"] >= "2026-08-11" for r in rows) >= 3
    dues = sorted(r["due_date"] for r in _of(rows, "status", "approved"))
    assert len(dues) >= 2 and dues[0] <= "2026-08-01" and dues[-1] >= "2026-09-01"
    assert _of(rows, "status", "draft") and _of(rows, "status", "submitted")
    disputed = _of(rows, "status", "disputed")
    assert len(disputed) >= 3
    assert all(len(r["dispute_reason"]) >= 16 and " " in r["dispute_reason"] for r in disputed)


def _documents() -> None:
    rows = _rows("InvoiceDocument")
    invoices = {f"3c000000-0000-4000-8000-0000000000{n:02d}" for n in (1, 2, 3, 4, 5, 8, 15, 18)}
    assert len(rows) >= 8
    for r in rows:
        assert len(r["headline"]) >= 16 and " " in r["headline"]
        assert r["invoice"] in invoices and r["id"].startswith("3f000000-")
        assert len(r.get("body") or "") >= 24
        url = r.get("preview_url") or ""
        assert not url or (url.startswith("https://") and "placehold.co" in url)
    assert sum(bool(r.get("preview_url")) for r in rows) >= 8
    assert {r["status"] for r in rows} >= {"draft", "published"}
    by_kind = Counter(r["doc_kind"] for r in rows)
    assert by_kind.keys() >= set(_KINDS.values()) - {"dispute_packet"}
    for kind in ("goods_receipt", "credit_memo", "remittance", "debit_memo", "vendor_statement"):
        assert by_kind[kind] >= 2, kind
    for kind in ("packing_slip", "ach_authorization", "wire_instructions", "lien_waiver"):
        assert by_kind[kind] >= 2, kind
    for kind in ("insurance_certificate", "form_w9"):
        assert by_kind[kind] >= 2, kind
    published = {"debit_memo", "vendor_statement", "packing_slip", "ach_authorization"}
    both = {"wire_instructions", "lien_waiver", "insurance_certificate", "form_w9"}
    for kind in published | both:
        assert _of(_of(rows, "doc_kind", kind), "status", "published"), kind
    for kind in both:
        assert _of(_of(rows, "doc_kind", kind), "status", "draft"), kind
    assert all(r.get("preview_url") for r in _of(rows, "doc_kind", "goods_receipt"))
    compliance = _of(
        _of(rows, "status", "draft"),
        "doc_kind",
        "form_w9",
        "insurance_certificate",
        "tax_certificate",
        "lien_waiver",
        "ach_authorization",
    )
    assert len(compliance) >= 2 and len({r["doc_kind"] for r in compliance}) >= 2
    for kinds, floor in (
        (("po_packet", "goods_receipt", "packing_slip"), 6),
        (("remittance", "payment_confirmation"), 5),
        (("credit_memo", "debit_memo"), 5),
        (("ach_authorization", "wire_instructions"), 5),
        (("form_w9", "tax_certificate"), 5),
    ):
        assert sum(by_kind[k] for k in kinds) >= floor and all(by_kind[k] for k in kinds)
    packs = _of(rows, "doc_kind", "dispute_packet")
    assert len(packs) >= 3
    assert all(r.get("preview_url") and r["status"] == "published" for r in packs)
    assert {f"3c000000-0000-4000-8000-0000000000{n}" for n in ("08", "15", "18")} <= {
        r["invoice"] for r in packs
    }


def _lines() -> None:
    rows = _rows("LineItem")
    assert len(rows) >= 12
    for r in rows:
        assert len(r["description"]) >= 12 and " " in r["description"]
        assert int(r["quantity"]) >= 1 and float(r["unit_amount"]) > 0
        assert str(r.get("tax_code") or "").startswith("GB-")
        assert r["po_match"] in {"matched", "partial", "unmatched", "not_applicable"}
    matches = Counter(r["po_match"] for r in rows)
    assert matches["matched"] and matches["unmatched"] >= 2 and matches["partial"] >= 2
    assert len({r["tax_code"] for r in rows}) >= 2


def _notes() -> None:
    rows = _rows("InvoiceNote")
    assert len(rows) >= 10
    assert all(len(r.get("body") or "") >= 24 and " " in r["body"] for r in rows)


def _users() -> None:
    rows = _rows("User")
    assert len(rows) >= 8
    assert all(r.get("name") and r.get("department") and r.get("job_title") for r in rows)
    depts = Counter(r["department"] for r in rows)
    assert {"Accounts Payable", "Treasury", "Controllership", "Audit"} <= depts.keys()
    assert sum(n >= 2 for n in depts.values()) >= 3
    titles = {r["job_title"] for r in rows}
    assert {"Requester", "Approver", "Finance Operator", "Auditor"} <= titles
    assert sum(str(r.get("id", "")).startswith("b2000000") for r in rows) >= 4


def _suppliers() -> None:
    assert {"emea", "amer", "apac"} <= {r.get("region") for r in _rows("Supplier")}


SEED_RULES: dict[str, Callable[[], None]] = {
    "Invoice": _invoices,
    "InvoiceDocument": _documents,
    "LineItem": _lines,
    "InvoiceNote": _notes,
    "User": _users,
    "Supplier": _suppliers,
}


@pytest.mark.parametrize("seed", sorted(SEED_RULES))
def test_demo_seeds(seed: str) -> None:
    SEED_RULES[seed]()
