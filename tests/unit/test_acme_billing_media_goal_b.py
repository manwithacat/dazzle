"""Post-5.8 Goal B media — acme_billing invoice packet wall (novel vs headshot)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/acme_billing/dsl/surfaces.dsl"
ENT = ROOT / "examples/acme_billing/dsl/entities.dsl"
SEEDS = ROOT / "examples/acme_billing/dsl/seeds/demo_data/Invoice.jsonl"


def _billing_block() -> str:
    text = APP.read_text()
    marker = 'workspace billing "Acme Billing":'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_invoice_declares_preview_url() -> None:
    text = ENT.read_text()
    assert "preview_url: url" in text
    assert "photo_url" not in text.split("entity Invoice")[1].split("entity ")[0]


def test_billing_invoice_packets_first() -> None:
    """Novel media: invoice document thumbs win fold — not User headshots."""
    block = _billing_block()
    assert "invoice_packets:" in block
    assert "source: Invoice" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert "photo_url" not in block
    assert block.index("invoice_packets:") < block.index("portfolio_metrics:")
    assert "invoice_packets" in block
    assert "as admin:" in block
    assert "as org_owner:" in block
    assert "as auditor:" in block


def test_invoice_seeds_have_preview_urls() -> None:
    rows = [json.loads(line) for line in SEEDS.read_text().splitlines() if line.strip()]
    with_preview = [r for r in rows if r.get("preview_url")]
    assert len(with_preview) >= 8, "Goal B media expects packet previews on invoices"
    assert all("placehold.co" in r["preview_url"] for r in with_preview)
