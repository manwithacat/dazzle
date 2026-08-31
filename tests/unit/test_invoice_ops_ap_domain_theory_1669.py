"""#1669 — invoice_ops AP money theory lives in a stem, not new entities."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEMS = ROOT / "examples/invoice_ops/stems"
INDEX = (STEMS / "INDEX.md").read_text()
THEORY = (STEMS / "ap-domain-theory.md").read_text()
ENTITIES = (ROOT / "examples/invoice_ops/dsl/entities.dsl").read_text()


def test_index_lists_ap_domain_theory() -> None:
    assert "ap-domain-theory.md" in INDEX
    assert (STEMS / "ap-domain-theory.md").is_file()


def test_stem_names_four_judgements() -> None:
    assert "Settle is finance remittance" in THEORY
    assert "Dispute outcome is approved | rejected" in THEORY
    assert "Retryable fail does not move Invoice" in THEORY
    assert "`po_match: not_applicable` is a kind" in THEORY


def test_stem_forbids_taste_entities_and_rails() -> None:
    assert "CreditNote" in THEORY
    assert "Northrail Pay" in THEORY
    assert "requester a pay button" in THEORY
    assert "fifth PO status" in THEORY


def test_dsl_still_has_enums_the_stem_explains() -> None:
    """Theory amends stems; enums stay. No CreditNote entity from this run."""
    assert "po_match: enum[matched, partial, unmatched, not_applicable]" in ENTITIES
    assert 'entity PaymentAttempt "Payment Attempt"' in ENTITIES
    assert "status: enum[pending,succeeded,failed]" in ENTITIES
    assert "entity CreditNote" not in ENTITIES
