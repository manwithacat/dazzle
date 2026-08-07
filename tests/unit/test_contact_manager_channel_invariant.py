"""contact_manager: email optional + phone-or-email invariant (cycle 1745 panel).

Trial adoption criteria require name + at least one reachable channel.
The entity already declared ``invariant: email != null or phone != null`` but
kept ``email … required``, so the create form blocked phone-only prospects.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"
ONBOARD = ROOT / "examples/contact_manager/dsl/onboarding.dsl"


def test_contact_email_not_required_field() -> None:
    text = APP.read_text(encoding="utf-8")
    # Field line must be unique-but-not-required.
    assert "email: email unique required" not in text
    assert "email: email unique pii(category=contact)" in text
    assert "invariant: email != null or phone != null" in text


def test_create_purpose_mentions_channel_choice() -> None:
    text = APP.read_text(encoding="utf-8")
    assert "email or phone" in text
    assert 'purpose: "Add a new contact — name plus email or phone' in text


def test_onboarding_matches_channel_rule() -> None:
    text = ONBOARD.read_text(encoding="utf-8")
    assert "email or phone" in text
    assert "First name + email are the only required fields" not in text
