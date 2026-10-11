"""Signing ceremony must not dump EngagementLetter as the principal (oral #196)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dazzle.core.project import load_project
from dazzle.signing.routes import (
    clerk_signing_heading,
    clerk_signing_mid,
)

SUPPORT = Path("examples/support_tickets")
_LETTER_ID = UUID("a1000000-0000-4000-8000-000000000001")
_SIGNING_PAD = Path("src/dazzle/page/runtime/static/js/islands/signing-pad.js")


def test_support_sla_waiver_ceremony_noun_is_live() -> None:
    spec = load_project(SUPPORT)
    waiver = next(e for e in spec.domain.entities if e.name == "SlaWaiver")
    assert waiver.title == "SLA Waiver"
    assert clerk_signing_heading("SlaWaiver", waiver) == "SLA Waiver"
    assert clerk_signing_mid("SlaWaiver", waiver) == "sla waiver"


def test_authority_checkbox_signs_this_document() -> None:
    js = _SIGNING_PAD.read_text(encoding="utf-8")
    assert "authorised to sign this " in js
    assert "on behalf of " not in js
