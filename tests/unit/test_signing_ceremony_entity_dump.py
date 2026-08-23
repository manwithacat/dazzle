"""Signing ceremony must not dump EngagementLetter as the principal (oral #196)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dazzle.core.ir import EntitySpec
from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.signing.routes import (
    _signing_page,
    _stub_document_body,
    clerk_signing_heading,
    clerk_signing_mid,
)

CONTACT = Path("examples/contact_manager")
SUPPORT = Path("examples/support_tickets")
_LETTER_ID = UUID("a1000000-0000-4000-8000-000000000001")
_SIGNING_PAD = Path("src/dazzle/page/runtime/static/js/islands/signing-pad.js")


def _letter() -> EntitySpec:
    spec = load_project(CONTACT)
    return next(e for e in spec.domain.entities if e.name == "EngagementLetter")


def test_contact_engagement_letter_ceremony_noun_is_live() -> None:
    letter = _letter()
    assert letter.title == "Engagement Letter"
    assert entity_slug("EngagementLetter") == "engagementletter"
    assert clerk_signing_heading("EngagementLetter", letter) == "Engagement Letter"
    assert clerk_signing_mid("EngagementLetter", letter) == "engagement letter"


def test_support_sla_waiver_ceremony_noun_is_live() -> None:
    spec = load_project(SUPPORT)
    waiver = next(e for e in spec.domain.entities if e.name == "SlaWaiver")
    assert waiver.title == "SLA Waiver"
    assert clerk_signing_heading("SlaWaiver", waiver) == "SLA Waiver"
    assert clerk_signing_mid("SlaWaiver", waiver) == "sla waiver"


def test_signing_page_heading_not_pascal() -> None:
    html = _signing_page(
        entity_name="EngagementLetter",
        record_id=str(_LETTER_ID),
        token="tok",
        document_body="<p>body</p>",
        entity=_letter(),
    )
    assert "<title>Sign Engagement Letter</title>" in html
    assert "<h1>Sign Engagement Letter</h1>" in html
    assert "Sign EngagementLetter" not in html
    assert "&quot;entity&quot;: &quot;EngagementLetter&quot;" in html
    assert "&quot;entityName&quot;: &quot;engagement letter&quot;" in html


def test_stub_document_heading_not_pascal() -> None:
    body = _stub_document_body(
        entity_name="EngagementLetter",
        record_id=_LETTER_ID,
        entity=_letter(),
    )
    assert "<h1>Engagement Letter</h1>" in body
    assert "<h1>EngagementLetter</h1>" not in body


def test_authority_checkbox_signs_this_document() -> None:
    js = _SIGNING_PAD.read_text(encoding="utf-8")
    assert "authorised to sign this " in js
    assert "on behalf of " not in js


def test_leftover_zzz_invents_no_entity() -> None:
    letter = _letter()
    assert clerk_signing_heading("zzz", letter) == "zzz"
    assert clerk_signing_mid("zzz", letter) == "zzz"
    html = _signing_page(
        entity_name="zzz",
        record_id=str(_LETTER_ID),
        token="tok",
        document_body="<p>body</p>",
        entity=letter,
    )
    assert "<title>Sign zzz</title>" in html
    assert "&quot;entityName&quot;: &quot;zzz&quot;" in html
    assert "engagement letter" not in html.lower()
    stub = _stub_document_body(entity_name="zzz", record_id=_LETTER_ID, entity=letter)
    assert "<h1>zzz</h1>" in stub
    assert "Engagement Letter" not in stub
