"""Post-5.8 Goal B document — invoice_ops named AP packets + line tax/PO match + due date."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
LINE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/LineItem.jsonl"
DOC_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/InvoiceDocument.jsonl"
INVOICE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/Invoice.jsonl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_invoice_due_date_on_entity() -> None:
    """Peer Bill.com / Melio / Tipalti: amount + due date + vendor on work rows."""
    text = ENTITIES.read_text()
    inv = text.split('entity Invoice "Invoice"', 1)[1].split("entity ", 1)[0]
    assert "due_date: date optional" in inv
    assert "amount: decimal(15,2) required" in inv
    assert "supplier: ref Supplier required" in inv
    # Goal B document peer-pack (cycle 1921): dispute reason on work rows
    assert "dispute_reason: text optional" in inv
    assert (
        "repr_fields: [invoice_number, supplier, amount, due_date, status, dispute_reason]" in inv
    )


def test_line_item_display_field_is_description() -> None:
    text = ENTITIES.read_text()
    assert 'entity LineItem "Line Item"' in text
    assert "display_field: description" in text
    assert "description: str(200) required" in text
    # Peer-pack document grain (cycle 1900): tax + PO match on composition lines
    assert "tax_code: str(20) optional" in text
    assert "po_match: enum[matched, partial, unmatched, not_applicable]=not_applicable" in text
    # finance_admin must list/read composition on finance_ops home
    assert "role(finance_admin)" in text
    assert "finance_admin, auditor, tenant_admin" in text or "finance_admin" in text


def test_invoice_document_entity_is_named_packet_composition() -> None:
    text = ENTITIES.read_text()
    assert 'entity InvoiceDocument "Invoice Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert (
        "doc_kind: enum[remittance, credit_memo, debit_memo, vendor_statement, packing_slip, ach_authorization, wire_instructions, lien_waiver, insurance_certificate, form_w9, po_packet, tax_certificate, "
        "payment_confirmation, goods_receipt, dispute_packet]=remittance" in text
    )
    assert "status: enum[draft, published, archived]=draft" in text
    assert "preview_url: url" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text
    assert (
        "preview_url"
        in text.split("entity InvoiceDocument", 1)[1].split("fitness:", 1)[1].split("audit:", 1)[0]
    )


def test_ops_and_requester_homes_declare_document_composition() -> None:
    """Goal B document: packet covers first on finance_ops; lines on desks."""
    text = SURFACES.read_text()
    assert "workspace finance_ops" in text
    assert "workspace my_invoices" in text
    assert "workspace line_items_desk" in text
    assert "document_pulse:" in text

    ops = _workspace_block("finance_ops")
    assert "packet_covers:" in ops
    assert "source: InvoiceDocument" in ops
    assert "filter: preview_url != null" in ops
    assert "display: grid" in ops
    assert "documents: count(InvoiceDocument)" in ops
    assert "action: invoice_document_detail" in ops
    assert "line_composition:" in ops
    # Order: packet covers → document pulse → named packets → dual attention → past_due region
    assert ops.index("packet_covers:") < ops.index("document_pulse:")
    assert ops.index("document_pulse:") < ops.index("composition:")
    # Region marker (not the ops_metrics aggregate line past_due: count(...))
    past_due_region = ops.index("\n  past_due:\n")
    assert ops.index("composition:") < past_due_region
    assert past_due_region < ops.index("line_composition:")
    assert ops.index("line_composition:") < ops.index("live_conversation:")
    assert "past_due: count(Invoice where due_date < today" in ops
    assert "sort: due_date asc" in ops
    # Peer refuse: no headshot-first media shelf on the money desk
    assert "media_shelf:" not in ops
    assert "draft_packets:" in ops
    assert "filter: status = draft" in ops
    assert ops.index("document_pulse:") < ops.index("draft_packets:")
    assert ops.index("draft_packets:") < ops.index("composition:")
    assert "tax_certificates:" in ops
    assert "filter: doc_kind = tax_certificate" in ops
    assert ops.index("draft_packets:") < ops.index("tax_certificates:")
    assert ops.index("tax_certificates:") < ops.index("composition:")
    assert "tax_certs: count(InvoiceDocument where doc_kind = tax_certificate)" in ops
    # Cycle 1965: PO packet watch after draft gate, before tax certs (above fold)
    assert "po_packets:" in ops
    assert "filter: doc_kind = po_packet" in ops
    assert "po_packs: count(InvoiceDocument where doc_kind = po_packet)" in ops
    assert ops.index("draft_packets:") < ops.index("po_packets:")
    assert ops.index("po_packets:") < ops.index("tax_certificates:")
    assert ops.index("tax_certificates:") < ops.index("composition:")
    # Cycle 1967: goods receipt three-way match after draft, focused above fold
    # Region marker (not the document_pulse aggregate key goods_receipts: count(...)).
    assert "\n  goods_receipts:\n" in ops
    assert "filter: doc_kind = goods_receipt" in ops
    assert "goods_receipts: count(InvoiceDocument where doc_kind = goods_receipt)" in ops
    assert ops.index("draft_packets:") < ops.index("\n  goods_receipts:\n")
    assert ops.index("\n  goods_receipts:\n") < ops.index("composition:")
    assert (
        "focus: packet_covers, ops_metrics, document_pulse, draft_packets, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, "
        "compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, "
        "awaiting_approval" in ops
    )

    # List / hub expose amount + due + vendor (peer above_fold)
    inv_list = text.split('surface invoice_list "Invoices"', 1)[1].split("surface ", 1)[0]
    assert 'field supplier "Supplier"' in inv_list
    assert 'field due_date "Due"' in inv_list
    assert 'field amount "Amount"' in inv_list
    hub = text.split('surface invoice_detail "Invoice"', 1)[1].split("surface ", 1)[0]
    assert 'field due_date "Due Date"' in hub
    assert "columns: description, quantity, unit_amount, tax_code, po_match" in hub

    # Dedicated composition desk: PO match board before line body (recipe line_tax_po_match)
    lines_desk = _workspace_block("line_items_desk")
    assert "po_match_board:" in lines_desk
    assert "group_by: po_match" in lines_desk
    assert "source: LineItem" in lines_desk
    assert lines_desk.index("po_match_board:") < lines_desk.index("composition:")
    assert "matched: count(LineItem where po_match = matched)" in lines_desk
    assert "unmatched: count(LineItem where po_match = unmatched)" in lines_desk
    assert "focus: line_pulse, po_match_board, composition, open_documents" in lines_desk
    assert "source: LineItem" in text.split("workspace my_invoices", 1)[1]


def test_pay_desk_draft_packet_release_gate() -> None:
    """Cycle 1957: Bill.com/Melio draft packets must publish before settle batch."""
    desk = _workspace_block("pay_desk")
    assert "draft_packets:" in desk
    region = desk.split("\n  draft_packets:\n", 1)[1].split("\n  remittances:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: status = draft" in region
    assert "display: queue" in region
    assert "draft: count(InvoiceDocument where status = draft)" in desk
    assert desk.index("document_pulse:") < desk.index("draft_packets:")
    assert desk.index("draft_packets:") < desk.index("composition:")
    assert desk.index("draft_packets:") < desk.index("ready_to_pay:")
    assert (
        "focus: settle_metrics, document_pulse, draft_packets, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, "
        "compliance_drafts, remittances, form_w9s, packing_slips, composition, "
        "ready_to_pay" in desk
    )


def test_finance_ops_and_approval_goods_receipt_match() -> None:
    """Cycle 1967: Coupa/Tipalti three-way match goods receipts on ops + approve."""
    ops = _workspace_block("finance_ops")
    assert "goods_receipts:" in ops
    region = ops.split("\n  goods_receipts:\n", 1)[1].split("\n  credit_memos:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = goods_receipt" in region
    assert "display: queue" in region
    assert "goods_receipts: count(InvoiceDocument where doc_kind = goods_receipt)" in ops
    desk = _workspace_block("approval_desk")
    assert "goods_receipts:" in desk
    assert "filter: doc_kind = goods_receipt" in desk
    assert "goods_receipts" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    gr = [r for r in rows if r.get("doc_kind") == "goods_receipt"]
    assert len(gr) >= 2
    for r in gr:
        assert len(str(r.get("headline") or "")) >= 16
        assert r.get("preview_url")


def test_finance_ops_and_pay_desk_credit_memo_watch() -> None:
    """Cycle 1971: Bill.com/Melio credit memo watch on ops + settle desks."""
    ops = _workspace_block("finance_ops")
    assert "\n  credit_memos:\n" in ops
    region = ops.split("\n  credit_memos:\n", 1)[1].split("\n  remittances:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = credit_memo" in region
    assert "display: queue" in region
    assert "credit_memos: count(InvoiceDocument where doc_kind = credit_memo)" in ops
    # Focus later prefers vendor_statements (cycle 1983); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  credit_memos:\n" in desk
    assert "filter: doc_kind = credit_memo" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    cm = [r for r in rows if r.get("doc_kind") == "credit_memo"]
    assert len(cm) >= 2
    for r in cm:
        assert len(str(r.get("headline") or "")) >= 16


def test_finance_ops_and_pay_desk_remittance_advice_watch() -> None:
    """Cycle 1974: Bill.com/Melio remittance advice watch on ops + settle desks."""
    ops = _workspace_block("finance_ops")
    assert "\n  remittances:\n" in ops
    region = ops.split("\n  remittances:\n", 1)[1].split("\n  dispute_packets:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = remittance" in region
    assert "display: queue" in region
    assert "remittances: count(InvoiceDocument where doc_kind = remittance)" in ops
    assert "remittances" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    desk = _workspace_block("pay_desk")
    assert "\n  remittances:\n" in desk
    assert "filter: doc_kind = remittance" in desk
    assert "remittances" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    rem = [r for r in rows if r.get("doc_kind") == "remittance"]
    assert len(rem) >= 2
    for r in rem:
        assert len(str(r.get("headline") or "")) >= 16


def test_finance_ops_and_pay_desk_debit_memo_watch() -> None:
    """Cycle 1981: Bill.com/Melio debit memo watch — opposite credit_memo."""
    ops = _workspace_block("finance_ops")
    assert "\n  debit_memos:\n" in ops
    region = ops.split("\n  debit_memos:\n", 1)[1].split("\n  vendor_statements:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = debit_memo" in region
    assert "display: queue" in region
    # Pure debit grain — not credit_memo / dispute_packet re-stack filters.
    assert "doc_kind = credit_memo" not in region
    assert "doc_kind = dispute_packet" not in region
    assert "debit_memos: count(InvoiceDocument where doc_kind = debit_memo)" in ops
    # Focus later prefers vendor_statements (cycle 1983); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  debit_memos:\n" in desk
    assert "filter: doc_kind = debit_memo" in desk
    assert "debit_memos: count(InvoiceDocument where doc_kind = debit_memo)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    dm = [r for r in rows if r.get("doc_kind") == "debit_memo"]
    assert len(dm) >= 2
    for r in dm:
        assert len(str(r.get("headline") or "")) >= 16
    # At least one published debit (not draft-only theater).
    assert any(r.get("status") == "published" for r in dm)


def test_finance_ops_and_pay_desk_vendor_statement_watch() -> None:
    """Cycle 1983: Bill.com/Melio vendor statement period-end reconcile."""
    ops = _workspace_block("finance_ops")
    assert "\n  vendor_statements:\n" in ops
    region = ops.split("\n  vendor_statements:\n", 1)[1].split("\n  packing_slips:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = vendor_statement" in region
    assert "display: queue" in region
    assert "doc_kind = remittance" not in region
    assert "doc_kind = debit_memo" not in region
    assert "vendor_statements: count(InvoiceDocument where doc_kind = vendor_statement)" in ops
    # Focus later prefers packing_slips (cycle 1985); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  vendor_statements:\n" in desk
    assert "filter: doc_kind = vendor_statement" in desk
    assert "vendor_statements: count(InvoiceDocument where doc_kind = vendor_statement)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    vs = [r for r in rows if r.get("doc_kind") == "vendor_statement"]
    assert len(vs) >= 2
    for r in vs:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in vs)


def test_finance_ops_and_pay_desk_packing_slip_watch() -> None:
    """Cycle 1985: Bill.com/Coupa packing slip three-way match grain."""
    ops = _workspace_block("finance_ops")
    assert "\n  packing_slips:\n" in ops
    region = ops.split("\n  packing_slips:\n", 1)[1].split("\n  ach_authorizations:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = packing_slip" in region
    assert "display: queue" in region
    assert "doc_kind = goods_receipt" not in region
    assert "doc_kind = po_packet" not in region
    assert "packing_slips: count(InvoiceDocument where doc_kind = packing_slip)" in ops
    # Focus later prefers insurance_certificates (cycle 1993); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  packing_slips:\n" in desk
    assert "filter: doc_kind = packing_slip" in desk
    assert "packing_slips: count(InvoiceDocument where doc_kind = packing_slip)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    ps = [r for r in rows if r.get("doc_kind") == "packing_slip"]
    assert len(ps) >= 2
    for r in ps:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in ps)


def test_finance_ops_and_pay_desk_ach_authorization_watch() -> None:
    """Cycle 1987: Bill.com/Melio ACH authorization before first settle."""
    ops = _workspace_block("finance_ops")
    assert "\n  ach_authorizations:\n" in ops
    region = ops.split("\n  ach_authorizations:\n", 1)[1].split("\n  wire_instructions:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = ach_authorization" in region
    assert "display: queue" in region
    assert "doc_kind = remittance" not in region
    assert "doc_kind = payment_confirmation" not in region
    assert "ach_authorizations: count(InvoiceDocument where doc_kind = ach_authorization)" in ops
    # Focus later prefers insurance_certificates (cycle 1993); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  ach_authorizations:\n" in desk
    assert "filter: doc_kind = ach_authorization" in desk
    assert "ach_authorizations: count(InvoiceDocument where doc_kind = ach_authorization)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    aa = [r for r in rows if r.get("doc_kind") == "ach_authorization"]
    assert len(aa) >= 2
    for r in aa:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in aa)


def test_finance_ops_and_pay_desk_wire_instructions_watch() -> None:
    """Cycle 1989: Bill.com/Melio wire instructions before first high-value wire."""
    ops = _workspace_block("finance_ops")
    assert "\n  wire_instructions:\n" in ops
    region = ops.split("\n  wire_instructions:\n", 1)[1].split("\n  lien_waivers:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = wire_instructions" in region
    assert "display: queue" in region
    assert "doc_kind = ach_authorization" not in region
    assert "doc_kind = payment_confirmation" not in region
    assert "wire_instructions: count(InvoiceDocument where doc_kind = wire_instructions)" in ops
    # Focus later prefers insurance_certificates (cycle 1993); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  wire_instructions:\n" in desk
    assert "filter: doc_kind = wire_instructions" in desk
    assert "wire_instructions: count(InvoiceDocument where doc_kind = wire_instructions)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    wi = [r for r in rows if r.get("doc_kind") == "wire_instructions"]
    assert len(wi) >= 2
    for r in wi:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in wi)
    assert any(r.get("status") == "draft" for r in wi)


def test_finance_ops_and_pay_desk_lien_waiver_watch() -> None:
    """Cycle 1991: Bill.com/Melio lien waivers before construction pay release."""
    ops = _workspace_block("finance_ops")
    assert "\n  lien_waivers:\n" in ops
    region = ops.split("\n  lien_waivers:\n", 1)[1].split("\n  insurance_certificates:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = lien_waiver" in region
    assert "display: queue" in region
    assert "doc_kind = wire_instructions" not in region
    assert "doc_kind = ach_authorization" not in region
    assert "lien_waivers: count(InvoiceDocument where doc_kind = lien_waiver)" in ops
    # Focus later prefers insurance_certificates (cycle 1993); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  lien_waivers:\n" in desk
    assert "filter: doc_kind = lien_waiver" in desk
    assert "lien_waivers: count(InvoiceDocument where doc_kind = lien_waiver)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    lw = [r for r in rows if r.get("doc_kind") == "lien_waiver"]
    assert len(lw) >= 2
    for r in lw:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in lw)
    assert any(r.get("status") == "draft" for r in lw)


def test_finance_ops_and_pay_desk_insurance_certificate_watch() -> None:
    """Cycle 1993: Bill.com/Melio COI before contractor/facility pay release."""
    ops = _workspace_block("finance_ops")
    assert "\n  insurance_certificates:\n" in ops
    region = ops.split("\n  insurance_certificates:\n", 1)[1].split("\n  form_w9s:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = insurance_certificate" in region
    assert "display: queue" in region
    assert "doc_kind = lien_waiver" not in region
    assert "doc_kind = wire_instructions" not in region
    assert "doc_kind = ach_authorization" not in region
    assert (
        "insurance_certificates: count(InvoiceDocument where doc_kind = insurance_certificate)"
        in ops
    )
    # Focus later prefers compliance_drafts (cycle 2000); region + metric remain.
    desk = _workspace_block("pay_desk")
    assert "\n  insurance_certificates:\n" in desk
    assert "filter: doc_kind = insurance_certificate" in desk
    assert (
        "insurance_certificates: count(InvoiceDocument where doc_kind = insurance_certificate)"
        in desk
    )
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    coi = [r for r in rows if r.get("doc_kind") == "insurance_certificate"]
    assert len(coi) >= 2
    for r in coi:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in coi)
    assert any(r.get("status") == "draft" for r in coi)


def test_finance_ops_and_pay_desk_form_w9_watch() -> None:
    """Cycle 1995: Bill.com/Melio/Tipalti Form W-9 before first US settle."""
    ops = _workspace_block("finance_ops")
    assert "\n  form_w9s:\n" in ops
    region = ops.split("\n  form_w9s:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "filter: doc_kind = form_w9" in region
    assert "display: queue" in region
    assert "doc_kind = tax_certificate" not in region
    assert "doc_kind = insurance_certificate" not in region
    assert "doc_kind = ach_authorization" not in region
    assert "form_w9s: count(InvoiceDocument where doc_kind = form_w9)" in ops
    # Focus later prefers compliance_drafts (cycle 2000); form_w9 region + metric remain.
    assert "form_w9s" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    desk = _workspace_block("pay_desk")
    assert "\n  form_w9s:\n" in desk
    assert "filter: doc_kind = form_w9" in desk
    assert "form_w9s" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert "form_w9s: count(InvoiceDocument where doc_kind = form_w9)" in desk
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    w9 = [r for r in rows if r.get("doc_kind") == "form_w9"]
    assert len(w9) >= 2
    for r in w9:
        assert len(str(r.get("headline") or "")) >= 16
    assert any(r.get("status") == "published" for r in w9)
    assert any(r.get("status") == "draft" for r in w9)


def test_finance_ops_and_pay_desk_compliance_draft_gate() -> None:
    """Cycle 2000: Bill.com/Melio/Tipalti compliance drafts before first settle.

    Compound status=draft + onboarding kinds (W-9/COI/tax/lien/ACH) — not
    form_w9-only or all-draft re-stack.
    """
    ops = _workspace_block("finance_ops")
    assert "\n  compliance_drafts:\n" in ops
    region = ops.split("\n  compliance_drafts:\n", 1)[1].split("\n  match_evidence:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "status = draft" in region
    assert "doc_kind = form_w9" in region
    assert "doc_kind = insurance_certificate" in region
    assert "doc_kind = tax_certificate" in region
    assert "doc_kind = lien_waiver" in region
    assert "doc_kind = ach_authorization" in region
    # Pure compliance compound — not remittance/credit/all-draft re-stack.
    assert "doc_kind = remittance" not in region
    assert "doc_kind = credit_memo" not in region
    assert "display: queue" in region
    assert (
        "compliance_drafts: count(InvoiceDocument where status = draft and "
        "(doc_kind = form_w9 or doc_kind = insurance_certificate or "
        "doc_kind = tax_certificate or doc_kind = lien_waiver or "
        "doc_kind = ach_authorization))" in ops
    )
    assert "compliance_drafts" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    # Region sits after draft_packets (refined gate), before match evidence (cycle 2002).
    assert ops.index("draft_packets:") < ops.index("\n  compliance_drafts:\n")
    assert ops.index("\n  compliance_drafts:\n") < ops.index("\n  match_evidence:\n")

    desk = _workspace_block("pay_desk")
    assert "\n  compliance_drafts:\n" in desk
    region_d = desk.split("\n  compliance_drafts:\n", 1)[1].split("\n  match_evidence:", 1)[0]
    assert "status = draft" in region_d
    assert "doc_kind = form_w9" in region_d
    assert "doc_kind = insurance_certificate" in region_d
    assert "doc_kind = remittance" not in region_d
    assert (
        "compliance_drafts: count(InvoiceDocument where status = draft and "
        "(doc_kind = form_w9 or doc_kind = insurance_certificate or "
        "doc_kind = tax_certificate or doc_kind = lien_waiver or "
        "doc_kind = ach_authorization))" in desk
    )
    assert "compliance_drafts" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  draft_packets:\n") < desk.index("\n  compliance_drafts:\n")
    assert desk.index("\n  compliance_drafts:\n") < desk.index("\n  match_evidence:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    compliance_kinds = {
        "form_w9",
        "insurance_certificate",
        "tax_certificate",
        "lien_waiver",
        "ach_authorization",
    }
    drafts = [
        r for r in rows if r.get("status") == "draft" and r.get("doc_kind") in compliance_kinds
    ]
    assert len(drafts) >= 2
    for r in drafts:
        assert len(str(r.get("headline") or "")) >= 16
    # At least two distinct compliance kinds still draft (not single-kind theater).
    assert len({r.get("doc_kind") for r in drafts}) >= 2


def test_finance_ops_pay_and_approval_three_way_match_evidence() -> None:
    """Cycle 2002: Coupa/Tipalti/Bill.com three-way match evidence pack.

    Compound PO + goods receipt + packing slip — not single doc_kind re-stack
    after compliance_draft_gate or goods_receipt/packing_slip/po_packet alone.
    """
    match_filter = "doc_kind = po_packet or doc_kind = goods_receipt or doc_kind = packing_slip"
    match_count = f"match_evidence: count(InvoiceDocument where {match_filter})"

    ops = _workspace_block("finance_ops")
    assert "\n  match_evidence:\n" in ops
    region = ops.split("\n  match_evidence:\n", 1)[1].split("\n  settle_rail:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = po_packet" in region
    assert "doc_kind = goods_receipt" in region
    assert "doc_kind = packing_slip" in region
    # Pure match compound — not compliance draft or remittance re-stack.
    assert "status = draft" not in region
    assert "doc_kind = remittance" not in region
    assert "doc_kind = form_w9" not in region
    assert "display: queue" in region
    assert match_count in ops
    assert "match_evidence" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  compliance_drafts:\n") < ops.index("\n  match_evidence:\n")
    assert ops.index("\n  match_evidence:\n") < ops.index("\n  settle_rail:\n")

    desk = _workspace_block("pay_desk")
    assert "\n  match_evidence:\n" in desk
    region_d = desk.split("\n  match_evidence:\n", 1)[1].split("\n  settle_rail:", 1)[0]
    assert match_filter in region_d
    assert "doc_kind = remittance" not in region_d
    assert match_count in desk
    assert "match_evidence" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  compliance_drafts:\n") < desk.index("\n  match_evidence:\n")
    assert desk.index("\n  match_evidence:\n") < desk.index("\n  settle_rail:\n")

    approval = _workspace_block("approval_desk")
    assert "\n  match_evidence:\n" in approval
    region_a = approval.split("\n  match_evidence:\n", 1)[1].split("\n  goods_receipts:", 1)[0]
    assert match_filter in region_a
    assert match_count in approval
    assert "match_evidence" in approval.split("focus:", 1)[1].split("\n", 1)[0]
    assert approval.index("\n  match_evidence:\n") < approval.index("\n  goods_receipts:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    match_kinds = {"po_packet", "goods_receipt", "packing_slip"}
    evidence = [r for r in rows if r.get("doc_kind") in match_kinds]
    assert len(evidence) >= 6
    for r in evidence:
        assert len(str(r.get("headline") or "")) >= 16
    # All three match kinds present (not single-kind theater).
    assert match_kinds.issubset({r.get("doc_kind") for r in evidence})


def test_finance_ops_and_pay_desk_settle_rail_evidence() -> None:
    """Cycle 2004: Bill.com/Melio settle rail (remittance + payment confirmation).

    Compound settle proof pack — not remittance-only or payment_confirmation-only
    re-stack after three_way_match_evidence / compliance_draft_gate.
    """
    rail_filter = "doc_kind = remittance or doc_kind = payment_confirmation"
    rail_count = f"settle_rail: count(InvoiceDocument where {rail_filter})"

    ops = _workspace_block("finance_ops")
    assert "\n  settle_rail:\n" in ops
    region = ops.split("\n  settle_rail:\n", 1)[1].split("\n  adjustment_rail:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = remittance" in region
    assert "doc_kind = payment_confirmation" in region
    assert "doc_kind = po_packet" not in region
    assert "doc_kind = goods_receipt" not in region
    assert "status = draft" not in region
    assert "display: queue" in region
    assert rail_count in ops
    assert "settle_rail" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  match_evidence:\n") < ops.index("\n  settle_rail:\n")
    assert ops.index("\n  settle_rail:\n") < ops.index("\n  adjustment_rail:\n")

    desk = _workspace_block("pay_desk")
    assert "\n  settle_rail:\n" in desk
    region_d = desk.split("\n  settle_rail:\n", 1)[1].split("\n  adjustment_rail:", 1)[0]
    assert rail_filter in region_d
    assert "doc_kind = credit_memo" not in region_d
    assert rail_count in desk
    assert "settle_rail" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  match_evidence:\n") < desk.index("\n  settle_rail:\n")
    assert desk.index("\n  settle_rail:\n") < desk.index("\n  adjustment_rail:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    rail_kinds = {"remittance", "payment_confirmation"}
    rail = [r for r in rows if r.get("doc_kind") in rail_kinds]
    assert len(rail) >= 5
    for r in rail:
        assert len(str(r.get("headline") or "")) >= 16
    assert rail_kinds.issubset({r.get("doc_kind") for r in rail})


def test_finance_ops_and_pay_desk_adjustment_rail_evidence() -> None:
    """Cycle 2006: Bill.com/Melio adjustment rail (credit + debit memos).

    Compound AP adjustment pack — not credit-only or debit-only re-stack after
    settle_rail / match_evidence / compliance_draft_gate.
    """
    adj_filter = "doc_kind = credit_memo or doc_kind = debit_memo"
    adj_count = f"adjustment_rail: count(InvoiceDocument where {adj_filter})"

    ops = _workspace_block("finance_ops")
    assert "\n  adjustment_rail:\n" in ops
    region = ops.split("\n  adjustment_rail:\n", 1)[1].split("\n  bank_rail:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = credit_memo" in region
    assert "doc_kind = debit_memo" in region
    assert "doc_kind = remittance" not in region
    assert "doc_kind = payment_confirmation" not in region
    assert "status = draft" not in region
    assert "display: queue" in region
    assert adj_count in ops
    assert "adjustment_rail" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  settle_rail:\n") < ops.index("\n  adjustment_rail:\n")
    assert ops.index("\n  adjustment_rail:\n") < ops.index("\n  bank_rail:\n")

    desk = _workspace_block("pay_desk")
    assert "\n  adjustment_rail:\n" in desk
    region_d = desk.split("\n  adjustment_rail:\n", 1)[1].split("\n  bank_rail:", 1)[0]
    assert adj_filter in region_d
    assert "doc_kind = remittance" not in region_d
    assert adj_count in desk
    assert "adjustment_rail" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  settle_rail:\n") < desk.index("\n  adjustment_rail:\n")
    assert desk.index("\n  adjustment_rail:\n") < desk.index("\n  bank_rail:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    adj_kinds = {"credit_memo", "debit_memo"}
    adj = [r for r in rows if r.get("doc_kind") in adj_kinds]
    assert len(adj) >= 5
    for r in adj:
        assert len(str(r.get("headline") or "")) >= 16
    assert adj_kinds.issubset({r.get("doc_kind") for r in adj})


def test_finance_ops_and_pay_desk_bank_rail_evidence() -> None:
    """Cycle 2008: Bill.com/Melio bank rail (ACH auth + wire instructions).

    Compound payment-method pack — not ACH-only or wire-only re-stack after
    adjustment_rail / settle_rail / compliance_draft_gate.
    """
    bank_filter = "doc_kind = ach_authorization or doc_kind = wire_instructions"
    bank_count = f"bank_rail: count(InvoiceDocument where {bank_filter})"

    ops = _workspace_block("finance_ops")
    assert "\n  bank_rail:\n" in ops
    region = ops.split("\n  bank_rail:\n", 1)[1].split("\n  tax_identity:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = ach_authorization" in region
    assert "doc_kind = wire_instructions" in region
    assert "doc_kind = remittance" not in region
    assert "doc_kind = credit_memo" not in region
    assert "status = draft" not in region
    assert "display: queue" in region
    assert bank_count in ops
    assert "bank_rail" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  adjustment_rail:\n") < ops.index("\n  bank_rail:\n")
    assert ops.index("\n  bank_rail:\n") < ops.index("\n  tax_identity:\n")

    desk = _workspace_block("pay_desk")
    assert "\n  bank_rail:\n" in desk
    region_d = desk.split("\n  bank_rail:\n", 1)[1].split("\n  tax_identity:", 1)[0]
    assert bank_filter in region_d
    assert "doc_kind = remittance" not in region_d
    assert bank_count in desk
    assert "bank_rail" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  adjustment_rail:\n") < desk.index("\n  bank_rail:\n")
    assert desk.index("\n  bank_rail:\n") < desk.index("\n  tax_identity:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    bank_kinds = {"ach_authorization", "wire_instructions"}
    bank = [r for r in rows if r.get("doc_kind") in bank_kinds]
    assert len(bank) >= 5
    for r in bank:
        assert len(str(r.get("headline") or "")) >= 16
    assert bank_kinds.issubset({r.get("doc_kind") for r in bank})


def test_finance_ops_and_pay_desk_tax_identity_rail() -> None:
    """Cycle 2010: Bill.com/Melio tax identity rail (Form W-9 + tax certificate).

    Compound TIN/VAT identity pack — not form_w9-only or tax_certificate-only
    re-stack after compliance_draft_gate / bank_rail.
    """
    tax_filter = "doc_kind = form_w9 or doc_kind = tax_certificate"
    tax_count = f"tax_identity: count(InvoiceDocument where {tax_filter})"

    ops = _workspace_block("finance_ops")
    assert "\n  tax_identity:\n" in ops
    region = ops.split("\n  tax_identity:\n", 1)[1].split("\n  po_packets:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = form_w9" in region
    assert "doc_kind = tax_certificate" in region
    assert "doc_kind = ach_authorization" not in region
    assert "doc_kind = insurance_certificate" not in region
    assert "status = draft" not in region
    assert "display: queue" in region
    assert tax_count in ops
    assert "tax_identity" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  bank_rail:\n") < ops.index("\n  tax_identity:\n")
    assert ops.index("\n  tax_identity:\n") < ops.index("po_packets:")

    desk = _workspace_block("pay_desk")
    assert "\n  tax_identity:\n" in desk
    region_d = desk.split("\n  tax_identity:\n", 1)[1].split("\n  remittances:", 1)[0]
    assert tax_filter in region_d
    assert "doc_kind = remittance" not in region_d
    assert tax_count in desk
    assert "tax_identity" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    assert desk.index("\n  bank_rail:\n") < desk.index("\n  tax_identity:\n")
    assert desk.index("\n  tax_identity:\n") < desk.index("\n  remittances:\n")

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    tax_kinds = {"form_w9", "tax_certificate"}
    tax = [r for r in rows if r.get("doc_kind") in tax_kinds]
    assert len(tax) >= 5
    for r in tax:
        assert len(str(r.get("headline") or "")) >= 16
    assert tax_kinds.issubset({r.get("doc_kind") for r in tax})


def test_invoice_document_list_dual_open_and_invoice_hub() -> None:
    text = SURFACES.read_text()
    assert 'surface invoice_document_list "Invoice Documents"' in text
    assert "open: InvoiceDocument via id | Invoice via invoice" in text
    assert 'surface invoice_document_detail "Invoice Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: InvoiceDocument" in text
    assert 'field preview_url "Cover"' in text


def test_invoice_seeds_mix_past_and_future_due_dates() -> None:
    rows = [json.loads(line) for line in INVOICE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12
    past_open = 0
    future = 0
    for row in rows:
        due = str(row.get("due_date") or "")
        assert due, f"due_date required on demo invoice: {row.get('invoice_number')}"
        assert len(due) == 10 and due[4] == "-", due
        status = str(row.get("status") or "")
        if due < "2026-08-11" and status not in {"paid", "rejected", "draft"}:
            past_open += 1
        if due >= "2026-08-11":
            future += 1
    assert past_open >= 3, past_open
    assert future >= 3, future


def test_dispute_desk_exposes_reason_bearing_exception_queue() -> None:
    """Goal B document recipe dispute_reason_desk — dedicated Disputes home."""
    text = SURFACES.read_text()
    assert 'workspace dispute_desk "Disputes"' in text
    desk = _workspace_block("dispute_desk")
    assert "dispute_pulse:" in desk
    assert "disputed: count(Invoice where status = disputed)" in desk
    assert "with_reason: count(Invoice where status = disputed and dispute_reason != null)" in desk
    assert "disputed_queue:" in desk
    assert "filter: status = disputed" in desk
    assert "settle_pipeline:" in desk
    assert "payment_attempts:" in desk
    assert desk.index("dispute_pulse:") < desk.index("disputed_queue:")
    assert desk.index("disputed_queue:") < desk.index("settle_pipeline:")
    # Cycle 1978: dispute_packet_watch on focus spine before settle trail
    assert (
        "focus: dispute_pulse, document_pulse, dispute_packets, disputed_queue, "
        "settle_pipeline, payment_attempts" in desk
    )
    # List + hub expose dispute reason (peer exception grain)
    inv_list = text.split('surface invoice_list "Invoices"', 1)[1].split("surface ", 1)[0]
    assert 'field dispute_reason "Dispute"' in inv_list
    hub = text.split('surface invoice_detail "Invoice"', 1)[1].split("surface ", 1)[0]
    assert 'field dispute_reason "Dispute Reason"' in hub
    # Personas can reach the desk
    personas = (ROOT / "examples/invoice_ops/dsl/personas.dsl").read_text()
    assert "dispute_desk" in personas


def test_finance_ops_and_dispute_desk_dispute_packet_watch() -> None:
    """Cycle 1978: Bill.com/Melio/Tipalti dispute evidence packets on ops + dispute desk."""
    ops = _workspace_block("finance_ops")
    assert "\n  dispute_packets:\n" in ops
    region = ops.split("\n  dispute_packets:\n", 1)[1].split("\n  debit_memos:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = dispute_packet" in region
    assert "display: queue" in region
    assert "dispute_packets: count(InvoiceDocument where doc_kind = dispute_packet)" in ops
    # Focus later prefers debit_memos (cycle 1981); region + metric remain.
    assert ops.index("\n  remittances:\n") < ops.index("\n  dispute_packets:\n")
    assert ops.index("\n  dispute_packets:\n") < ops.index("\n  debit_memos:\n")
    assert ops.index("\n  debit_memos:\n") < ops.index("composition:")

    desk = _workspace_block("dispute_desk")
    assert "document_pulse:" in desk
    assert "\n  dispute_packets:\n" in desk
    d_region = desk.split("\n  dispute_packets:\n", 1)[1].split("\n  disputed_queue:", 1)[0]
    assert "source: InvoiceDocument" in d_region
    assert "doc_kind = dispute_packet" in d_region
    assert "display: queue" in d_region
    assert "dispute_packets: count(InvoiceDocument where doc_kind = dispute_packet)" in desk
    assert desk.index("document_pulse:") < desk.index("\n  dispute_packets:\n")
    assert desk.index("\n  dispute_packets:\n") < desk.index("disputed_queue:")
    assert "dispute_packets" in desk.split("focus:", 1)[1].split("\n", 1)[0]

    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    packs = [r for r in rows if r.get("doc_kind") == "dispute_packet"]
    assert len(packs) >= 3, len(packs)
    disputed_invoices = {
        "3c000000-0000-4000-8000-000000000008",
        "3c000000-0000-4000-8000-000000000015",
        "3c000000-0000-4000-8000-000000000018",
    }
    linked = {str(r.get("invoice")) for r in packs}
    assert disputed_invoices <= linked, linked
    for r in packs:
        assert len(str(r.get("headline") or "")) >= 16
        assert r.get("preview_url")
        assert str(r.get("status")) == "published"


def test_disputed_invoice_seeds_carry_domain_true_reasons() -> None:
    rows = [json.loads(line) for line in INVOICE_SEEDS.read_text().splitlines() if line.strip()]
    disputed = [r for r in rows if str(r.get("status") or "") == "disputed"]
    assert len(disputed) >= 3, len(disputed)
    for row in disputed:
        reason = str(row.get("dispute_reason") or "")
        assert len(reason) >= 16, row.get("invoice_number")
        assert " " in reason, reason


def test_line_item_seeds_are_domain_true_descriptions() -> None:
    rows = [json.loads(line) for line in LINE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across invoices"
    matches: set[str] = set()
    tax_codes: set[str] = set()
    for row in rows:
        desc = str(row["description"])
        assert len(desc) >= 12, desc
        assert " " in desc, f"line description should be human prose, not slug: {desc}"
        assert int(row["quantity"]) >= 1
        assert float(row["unit_amount"]) > 0
        tax = str(row.get("tax_code") or "")
        assert tax, f"tax_code required on demo line: {desc}"
        assert tax.startswith("GB-"), tax
        match = str(row.get("po_match") or "")
        assert match in {"matched", "partial", "unmatched", "not_applicable"}, match
        matches.add(match)
        tax_codes.add(tax)
    assert "matched" in matches and "unmatched" in matches, matches
    assert len(tax_codes) >= 2, tax_codes


def test_invoice_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8, "Goal B document expects named packets across invoices"
    kinds: set[str] = set()
    statuses: set[str] = set()
    invoice_ids = {
        "3c000000-0000-4000-8000-000000000001",
        "3c000000-0000-4000-8000-000000000002",
        "3c000000-0000-4000-8000-000000000003",
        "3c000000-0000-4000-8000-000000000004",
        "3c000000-0000-4000-8000-000000000005",
        # Disputed invoices (cycle 1978 dispute_packet evidence)
        "3c000000-0000-4000-8000-000000000008",
        "3c000000-0000-4000-8000-000000000015",
        "3c000000-0000-4000-8000-000000000018",
    }
    with_cover = 0
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["invoice"]) in invoice_ids
        assert str(row["id"]).startswith("3f000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
        url = str(row.get("preview_url") or "")
        if url:
            with_cover += 1
            assert url.startswith("https://"), url
            assert "placehold.co" in url
    assert with_cover >= 8, "Goal B packet_cover_wall expects cover previews on packets"
    assert kinds >= {
        "remittance",
        "credit_memo",
        "po_packet",
        "tax_certificate",
        "payment_confirmation",
    }
    assert statuses >= {"draft", "published"}


def test_audit_review_declares_evidence_packets_before_trail() -> None:
    """Cycle 1942: audit desk puts packet covers + composition above payment trail."""
    block = _workspace_block("audit_review")
    assert "document_pulse:" in block
    assert "packet_covers:" in block
    assert "source: InvoiceDocument" in block
    assert "filter: preview_url != null" in block
    assert "display: grid" in block
    assert "composition:" in block
    assert "disputed_queue:" in block
    assert "payment_attempts:" in block
    # Order: document pulse → covers → composition → disputed → trail
    assert block.index("document_pulse:") < block.index("packet_covers:")
    assert block.index("packet_covers:") < block.index("composition:")
    assert block.index("composition:") < block.index("disputed_queue:")
    assert block.index("disputed_queue:") < block.index("payment_attempts:")
    assert (
        "focus: document_pulse, packet_covers, composition, disputed_queue, "
        "payment_attempts, settled_invoices"
    ) in block
    assert "media_shelf:" not in block
    # Chart stays under-fold (not focus spine)
    assert "audit_mix:" in block
    assert "audit_mix" not in block.split("focus:")[1].split("\n")[0]


def test_approval_desk_tax_certificate_watch() -> None:
    """Cycle 1959: reverse-charge tax certs before approve (Bill.com/Tipalti)."""
    desk = _workspace_block("approval_desk")
    assert "tax_certificates:" in desk
    region = desk.split("\n  tax_certificates:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = tax_certificate" in region
    assert "display: queue" in region
    assert "tax_certs: count(InvoiceDocument where doc_kind = tax_certificate)" in desk
    assert desk.index("document_pulse:") < desk.index("tax_certificates:")
    # Cycle 1965: PO packets sit above tax certs for hero still fold share
    assert desk.index("po_packets:") < desk.index("tax_certificates:")
    assert desk.index("tax_certificates:") < desk.index("composition:")
    assert (
        "focus: approval_load, document_pulse, match_evidence, goods_receipts, po_packets, composition, "
        "awaiting_approval, live_conversation" in desk
    )


def test_approval_and_ops_po_packet_watch() -> None:
    """Cycle 1965: signed PO packet watch before approve/ops (Bill.com/Coupa/Tipalti)."""
    ops = _workspace_block("finance_ops")
    assert "po_packets:" in ops
    ops_region = ops.split("\n  po_packets:\n", 1)[1].split("\n  tax_certificates:", 1)[0]
    assert "source: InvoiceDocument" in ops_region
    assert "doc_kind = po_packet" in ops_region
    assert "display: queue" in ops_region
    assert "po_packs: count(InvoiceDocument where doc_kind = po_packet)" in ops
    assert ops.index("draft_packets:") < ops.index("po_packets:")
    assert ops.index("po_packets:") < ops.index("tax_certificates:")
    assert ops.index("tax_certificates:") < ops.index("composition:")

    desk = _workspace_block("approval_desk")
    assert "po_packets:" in desk
    region = desk.split("\n  po_packets:\n", 1)[1].split("\n  tax_certificates:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = po_packet" in region
    assert "display: queue" in region
    assert "po_packs: count(InvoiceDocument where doc_kind = po_packet)" in desk
    assert desk.index("document_pulse:") < desk.index("po_packets:")
    assert desk.index("po_packets:") < desk.index("tax_certificates:")
    assert desk.index("tax_certificates:") < desk.index("composition:")
    assert desk.index("\n  goods_receipts:\n") < desk.index("po_packets:")
    assert (
        "focus: approval_load, document_pulse, match_evidence, goods_receipts, po_packets, composition, "
        "awaiting_approval, live_conversation" in desk
    )


def test_pay_desk_payment_confirmation_trail() -> None:
    """Cycle 1961: Bill.com/Melio payment confirmation trail on settle desk."""
    desk = _workspace_block("pay_desk")
    assert "payment_confirmations:" in desk
    region = desk.split("\n  payment_confirmations:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = payment_confirmation" in region
    assert "display: queue" in region
    assert "pay_confirms: count(InvoiceDocument where doc_kind = payment_confirmation)" in desk
    assert desk.index("draft_packets:") < desk.index("payment_confirmations:")
    assert desk.index("payment_confirmations:") < desk.index("composition:")
    assert desk.index("\n  remittances:\n") < desk.index("\n  credit_memos:\n")
    assert (
        "focus: settle_metrics, document_pulse, draft_packets, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, compliance_drafts, remittances, form_w9s, packing_slips, "
        "composition, ready_to_pay" in desk
    )
