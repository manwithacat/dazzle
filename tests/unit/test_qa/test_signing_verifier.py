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


def test_expired_seed_overrides_inference_and_expects_untouched_row():
    """TR-51: with token_state='expired' the expectation is fixed by the
    seeding — even when the persona ATTEMPTED a signature, the verifier
    must expect rejection (row stays 'sent'), not infer 'signed'."""
    doc = SeededDoc("SlaWaiver", "abc", "tok", "http://x", "a@b.com", token_state="expired")
    action_sink = {
        "invoked": ["read_inbox", "open_signing_link", "sign_document"],
        "requests": [
            {"method": "GET", "url": "http://x/sign/SlaWaiver/abc?token=tok", "status": 403},
            {"method": "POST", "url": "http://x/api/sign/SlaWaiver/abc", "status": 403},
        ],
        "active_doc": doc,
    }
    outcome = verify_signing_outcome(
        action_sink=action_sink,
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "sent"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.expected_outcome_inferred == "token_expired"
    assert outcome.functional["status"] == "pass"
    assert outcome.functional["final_row_status"] == "sent"


def test_expired_seed_fails_if_row_was_mutated():
    """If an expired-token trial somehow ends with the row signed, that's
    a security-relevant FAIL — the expired link accepted a signature."""
    doc = SeededDoc("SlaWaiver", "abc", "tok", "http://x", "a@b.com", token_state="expired")
    outcome = verify_signing_outcome(
        action_sink={
            "invoked": ["open_signing_link", "sign_document"],
            "requests": [
                {"method": "POST", "url": "http://x/api/sign/SlaWaiver/abc", "status": 200}
            ],
            "active_doc": doc,
        },
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "signed"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.expected_outcome_inferred == "token_expired"
    assert outcome.functional["status"] == "fail"


def test_already_signed_seed_expects_signed_without_persona_sign():
    """TR-49: pre-signed seed fixes expectation to signed even if persona
    only opens the link (no sign_document invocation)."""
    doc = SeededDoc("SlaWaiver", "abc", "tok", "http://x", "a@b.com", token_state="already_signed")
    outcome = verify_signing_outcome(
        action_sink={
            "invoked": ["read_inbox", "open_signing_link"],
            "requests": [
                {"method": "GET", "url": "http://x/sign/SlaWaiver/abc?token=tok", "status": 200},
            ],
            "active_doc": doc,
        },
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "signed"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.expected_outcome_inferred == "signed"
    assert outcome.functional["status"] == "pass"
    assert outcome.functional["final_row_status"] == "signed"


def test_validator_reject_seed_overrides_inference_and_expects_untouched_row():
    """#1382 / TR-50: with validator_reject the expectation is fixed by the
    seeding — even when the persona attempted a signature, the verifier must
    expect the project signing_validator to block it (row stays sent|viewed),
    not infer 'signed'. Otherwise a successful rejection mis-scores as a
    failure and the persona's 'no authority check' verdict reads as a
    false-critical."""
    doc = SeededDoc("SlaWaiver", "abc", "tok", "http://x", "a@b.com", validator_reject=True)
    action_sink = {
        "invoked": ["read_inbox", "open_signing_link", "sign_document"],
        "requests": [
            {"method": "GET", "url": "http://x/sign/SlaWaiver/abc?token=tok", "status": 200},
            {"method": "POST", "url": "http://x/api/sign/SlaWaiver/abc", "status": 400},
        ],
        "active_doc": doc,
    }
    for status in ("sent", "viewed"):
        outcome = verify_signing_outcome(
            action_sink=action_sink,
            seeded_docs=[doc],
            db_reader=MagicMock(return_value={"id": "abc", "status": status}),
            pdf_validator=MagicMock(),
        )
        assert outcome.expected_outcome_inferred == "validator_rejected"
        assert outcome.functional["status"] == "pass", status
        assert outcome.functional["final_row_status"] == status


def test_validator_reject_seed_fails_if_row_was_signed():
    """If a validator-reject trial somehow ends with the row signed, the
    authority check failed to fire — a genuine FAIL (the real defect the
    scenario is meant to catch), not the false-critical it emitted before."""
    doc = SeededDoc("SlaWaiver", "abc", "tok", "http://x", "a@b.com", validator_reject=True)
    outcome = verify_signing_outcome(
        action_sink={
            "invoked": ["open_signing_link", "sign_document"],
            "requests": [
                {"method": "POST", "url": "http://x/api/sign/SlaWaiver/abc", "status": 200}
            ],
            "active_doc": doc,
        },
        seeded_docs=[doc],
        db_reader=MagicMock(return_value={"id": "abc", "status": "signed"}),
        pdf_validator=MagicMock(),
    )
    assert outcome.expected_outcome_inferred == "validator_rejected"
    assert outcome.functional["status"] == "fail"


def test_outcome_serializes_to_dict():
    outcome = SigningOutcome(detected=False, expected_outcome_inferred="not_engaged")
    assert asdict(outcome)["detected"] is False
