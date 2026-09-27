"""#1666 — triple-open is three doors; carbon order lives on the attempt VIEW."""

from __future__ import annotations

from pathlib import Path

from tests.unit.dsl_source_lookup import declaration_block

ROOT = Path(__file__).resolve().parents[2]
STEM = (ROOT / "examples/invoice_ops/stems/story-driven-jobs.md").read_text()
CAP = (ROOT / "docs/reference/runtime-capabilities.md").read_text()


def test_attempt_detail_carbon_order() -> None:
    hub = declaration_block("invoice_ops", "surface", "payment_attempt_detail")
    assert hub.index("field attempt_number") < hub.index('field invoice "Invoice"')
    assert hub.index('field invoice "Invoice"') < hub.index("field tenant_id")
    assert "related" not in hub
    assert "not trail:" in hub
    assert "three hubs" in hub.lower()


def test_open_pipe_documented_as_doors() -> None:
    assert "Pipe order is **doors**" in CAP
    assert "`related` is reverse-FK children only" in CAP
    assert "three doors, not one folio" in STEM
    assert "Do not" in STEM and "`trail:`" in STEM
