"""Tests for dazzle.qa.signing_verifier — post-trial grading module."""

from dataclasses import asdict
from unittest.mock import MagicMock

from dazzle.qa.signing_seed import SeededDoc
from dazzle.qa.signing_verifier import (
    SigningOutcome,
    infer_expected_outcome,
    verify_signing_outcome,
)


def test_infer_expected_outcome():
    assert infer_expected_outcome(["read_inbox", "open_signing_link", "sign_document"]) == "signed"
    assert infer_expected_outcome(["open_signing_link", "decline_signing"]) == "declined"
    assert infer_expected_outcome(["open_signing_link", "tamper_token"]) == "token_invalid"
    assert infer_expected_outcome(["read_inbox"]) == "not_engaged"
    assert infer_expected_outcome([]) == "not_engaged"


def test_returns_detected_false_when_no_sign_request():
    outcome = verify_signing_outcome(
        action_sink={"invoked": ["read_inbox"], "requests": []},
        seeded_docs=[],
        db_reader=MagicMock(),
        pdf_validator=MagicMock(),
    )
    assert outcome.detected is False
    assert outcome.expected_outcome_inferred == "not_engaged"


def test_grades_pass_when_status_matches():
    doc = SeededDoc("TestDoc", "abc", "tok", "http://x", "a@b.com")
    action_sink = {
        "invoked": ["read_inbox", "open_signing_link", "sign_document"],
        "requests": [
            {"method": "GET", "url": "http://x/sign/TestDoc/abc?token=tok", "status": 200},
            {"method": "POST", "url": "http://x/api/sign/TestDoc/abc", "status": 200},
        ],
        "active_doc": doc,
    }
    db_reader = MagicMock(
        return_value={
            "id": "abc",
            "status": "signed",
            "signed_at": "2026-05-27T15:00:00Z",
            "signer_ip": "127.0.0.1",
            "signed_document": "/files/abc.pdf",
        }
    )
    pdf_validator = MagicMock(return_value={"valid": True, "summary": "OK"})
    outcome = verify_signing_outcome(
        action_sink=action_sink,
        seeded_docs=[doc],
        db_reader=db_reader,
        pdf_validator=pdf_validator,
    )
    assert outcome.detected is True
    assert outcome.functional["status"] == "pass"
    assert outcome.signature_integrity["valid"] is True


def test_grades_fail_when_status_mismatches():
    doc = SeededDoc("TestDoc", "abc", "tok", "http://x", "a@b.com")
    outcome = verify_signing_outcome(
        action_sink={
            "invoked": ["open_signing_link", "sign_document"],
            "requests": [{"method": "POST", "url": "http://x/api/sign/TestDoc/abc", "status": 500}],
            "active_doc": doc,
        },
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "viewed"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.functional["status"] == "fail"


def test_outcome_serializes_to_dict():
    outcome = SigningOutcome(detected=False, expected_outcome_inferred="not_engaged")
    assert asdict(outcome)["detected"] is False
