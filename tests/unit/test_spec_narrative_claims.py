"""Claim-catalogue loader + integrity drift gate."""

from dazzle.spec_narrative.claims import load_claims
from dazzle.spec_narrative.detectors import REGISTRY

_ALLOWED_GROUPS = {"security", "data", "architecture", "compliance"}
_ALLOWED_AUDIENCES = {"investor", "founder", "technical"}


def test_claims_load():
    claims = load_claims()
    assert claims, "catalogue is empty"
    ids = [c.id for c in claims]
    assert len(ids) == len(set(ids)), "duplicate claim ids"
    assert "scope_filtering" in ids


def test_every_claim_detector_is_registered():
    for c in load_claims():
        assert c.detector in REGISTRY, f"claim {c.id!r} names unknown detector {c.detector!r}"


def test_claim_groups_and_audiences_are_known():
    for c in load_claims():
        assert c.group in _ALLOWED_GROUPS, f"{c.id}: bad group {c.group!r}"
        assert c.audience in _ALLOWED_AUDIENCES, f"{c.id}: bad audience {c.audience!r}"


def test_claims_have_text_and_evidence():
    for c in load_claims():
        assert c.claim.strip(), f"{c.id}: empty claim text"
        assert c.evidence.strip(), f"{c.id}: empty evidence command"
