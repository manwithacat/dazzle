"""Post-5.8 Goal B media — invoice_ops packet cover wall (not headshot shelf).

Cycle 1892 peer-pack: Bill.com / Melio / Tipalti money desks refuse teammate
headshot shelves as media depth; remittance/PO packet cover thumbs are the
money-grain media expression (recipe packet_cover_wall).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
DOC_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/InvoiceDocument.jsonl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_invoice_document_declares_preview_url() -> None:
    text = ENTITIES.read_text()
    assert 'entity InvoiceDocument "Invoice Document"' in text
    assert "preview_url: url" in text
    assert "role(finance)" in text
    assert "role(finance_admin)" in text


def test_finance_ops_packet_covers_first() -> None:
    """Goal B: packet cover wall wins the Finance Operations fold before metrics."""
    block = _workspace_block("finance_ops")
    assert "packet_covers:" in block
    assert "source: InvoiceDocument" in block
    assert "display: grid" in block
    assert "filter: preview_url != null" in block
    assert "sort: created_at desc" in block
    assert block.index("packet_covers:") < block.index("ops_metrics:")
    assert block.index("packet_covers:") < block.index("document_pulse:")
    assert block.index("packet_covers:") < block.index("composition:")
    # Peer refuse headshot shelf on pure money desk
    assert "media_shelf:" not in block
    assert (
        "focus: packet_covers, ops_metrics, document_pulse, draft_packets, remittances, "
        "credit_memos, composition, past_due, awaiting_approval" in block
    )


def test_invoice_document_seeds_have_https_preview_urls() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    with_preview = [r for r in rows if r.get("preview_url")]
    assert len(with_preview) >= 8, "packet_cover_wall expects covers across AP packets"
    for r in with_preview:
        url = str(r["preview_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url
