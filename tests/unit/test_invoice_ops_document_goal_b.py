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
        "doc_kind: enum[remittance, credit_memo, po_packet, tax_certificate, "
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
        "focus: packet_covers, ops_metrics, document_pulse, draft_packets, remittances, "
        "dispute_packets, credit_memos, composition, past_due, awaiting_approval" in ops
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
        "focus: settle_metrics, document_pulse, draft_packets, remittances, credit_memos, "
        "composition, ready_to_pay" in desk
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
    assert "credit_memos" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    desk = _workspace_block("pay_desk")
    assert "\n  credit_memos:\n" in desk
    assert "filter: doc_kind = credit_memo" in desk
    assert "credit_memos" in desk.split("focus:", 1)[1].split("\n", 1)[0]
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    cm = [r for r in rows if r.get("doc_kind") == "credit_memo"]
    assert len(cm) >= 2
    for r in cm:
        assert len(str(r.get("headline") or "")) >= 16


def test_finance_ops_and_pay_desk_remittance_advice_watch() -> None:
    """Cycle 1974: Bill.com/Melio remittance advice watch on ops + settle desks."""
    ops = _workspace_block("finance_ops")
    assert "\n  remittances:\n" in ops
    region = ops.split("\n  remittances:\n", 1)[1].split("\n  composition:", 1)[0]
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
    region = ops.split("\n  dispute_packets:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "source: InvoiceDocument" in region
    assert "doc_kind = dispute_packet" in region
    assert "display: queue" in region
    assert "dispute_packets: count(InvoiceDocument where doc_kind = dispute_packet)" in ops
    assert "dispute_packets" in ops.split("focus:", 1)[1].split("\n", 1)[0]
    assert ops.index("\n  remittances:\n") < ops.index("\n  dispute_packets:\n")
    assert ops.index("\n  dispute_packets:\n") < ops.index("composition:")

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
        "focus: approval_load, document_pulse, goods_receipts, po_packets, composition, "
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
        "focus: approval_load, document_pulse, goods_receipts, po_packets, composition, "
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
        "focus: settle_metrics, document_pulse, draft_packets, remittances, credit_memos, "
        "composition, ready_to_pay" in desk
    )
