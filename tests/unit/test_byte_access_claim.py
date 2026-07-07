"""Tests for the byte_access claim and its detector (#1551 task 7)."""

from dazzle.spec_narrative.claims import load_claims
from dazzle.spec_narrative.detectors import REGISTRY


def test_byte_access_claim_exists():
    ids = [c.id for c in load_claims()]
    assert "byte_access" in ids, "byte_access claim is missing from claims.toml"


def test_byte_access_detector_is_registered():
    assert "has_byte_access_boundary" in REGISTRY, (
        "has_byte_access_boundary detector is missing from REGISTRY"
    )


def test_byte_access_claim_detector_matches_registry():
    """The claim's detector field names a registered detector (mirrors claim-integrity test)."""
    claims_by_id = {c.id: c for c in load_claims()}
    claim = claims_by_id["byte_access"]
    assert claim.detector in REGISTRY, (
        f"byte_access claim names detector {claim.detector!r} which is not in REGISTRY"
    )


def test_byte_access_detector_returns_true_for_app_with_file_fields():
    """The detector activates for apps that have at least one FILE-type field."""
    from pathlib import Path

    from dazzle.core.appspec_loader import load_project_appspec

    repo = Path(__file__).resolve().parents[2]
    # project_tracker has an Attachment entity with a `file: file required` field
    app = load_project_appspec(repo / "examples" / "project_tracker")
    assert REGISTRY["has_byte_access_boundary"](app) is True


def test_byte_access_detector_returns_false_for_file_less_app():
    """The detector does not activate for apps with no FILE-type fields."""
    from pathlib import Path

    from dazzle.core.appspec_loader import load_project_appspec

    repo = Path(__file__).resolve().parents[2]
    # simple_task has no file fields — the byte_access claim must not fire
    app = load_project_appspec(repo / "examples" / "simple_task")
    assert REGISTRY["has_byte_access_boundary"](app) is False
