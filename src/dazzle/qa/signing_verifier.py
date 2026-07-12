"""Post-trial signing verification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from dazzle.qa.signing_seed import SeededDoc

DbReader = Callable[[str, str], "dict[str, Any] | None"]
PdfValidator = Callable[[str], "dict[str, Any]"]

# Expected final row status(es) for each inferred outcome. Values are a single
# status string or a frozenset of acceptable statuses.
#
# ``validator_rejected`` accepts both ``sent`` and ``viewed``: opening the
# link advances default lifecycle ``sent → viewed`` before POST sign; a
# rejected signature must leave the row non-terminal (not signed/declined).
_EXPECTED_STATUS: dict[str, str | frozenset[str] | None] = {
    "signed": "signed",
    "declined": "declined",
    "token_invalid": "sent",
    "token_expired": "sent",
    "validator_rejected": frozenset({"sent", "viewed"}),
    "not_engaged": None,
}


@dataclass
class SigningOutcome:
    detected: bool = False
    expected_outcome_inferred: str = "not_engaged"
    functional: dict[str, Any] = field(default_factory=dict)
    signature_integrity: dict[str, Any] = field(default_factory=dict)
    latency_ms: dict[str, int] = field(default_factory=dict)


def infer_expected_outcome(invoked: list[str]) -> str:
    """Infer the expected signing outcome from the actions the persona invoked."""
    for action in invoked:
        if action == "sign_document":
            return "signed"
        if action == "decline_signing":
            return "declined"
        if action == "tamper_token":
            return "token_invalid"
    return "not_engaged"


def _compute_latency(requests: list[dict[str, Any]]) -> dict[str, int]:
    latency: dict[str, int] = {}
    for req in requests:
        url = req.get("url", "")
        elapsed = req.get("elapsed_ms")
        if elapsed is None:
            continue
        if "/api/sign/" in url:
            latency.setdefault("post_sign", int(elapsed))
        elif "/sign/" in url and req.get("method") == "GET":
            latency.setdefault("get_sign", int(elapsed))
    return latency


def _has_audit_fields(row: dict[str, Any]) -> bool:
    """Signer_ip + signed_at populated → audit fields present.

    Proxy for 'audit row written' until the framework exposes a richer
    audit-table read API.
    """
    return bool(row.get("signer_ip")) and bool(row.get("signed_at"))


def _expected_outcome_for_seeded_doc(
    active_doc: SeededDoc | None,
    invoked: list[str],
) -> str:
    """Map seeded-doc harness flags to an expected outcome label.

    When the harness fixed token/validator state, tool-based inference would
    mis-score (e.g. expect "signed" after an attempt against an expired link).
    """
    if active_doc is not None and getattr(active_doc, "token_state", "fresh") == "expired":
        # TR-51: expired token — every attempt rejected; row stays untouched.
        return "token_expired"
    if active_doc is not None and getattr(active_doc, "token_state", "fresh") == "already_signed":
        # TR-49: pre-signed row; re-open must leave status=signed.
        return "signed"
    if active_doc is not None and getattr(active_doc, "validator_reject", False):
        # #1382: project signing_validator armed to reject — stay `sent`.
        return "validator_rejected"
    return infer_expected_outcome(invoked)


def verify_signing_outcome(
    *,
    action_sink: dict[str, Any],
    seeded_docs: list[SeededDoc],
    db_reader: DbReader,
    pdf_validator: PdfValidator,
) -> SigningOutcome:
    """Grade a finished signing trial.

    Never raises — every failure becomes a structured finding in the returned
    ``SigningOutcome``.  The caller (Task 10 CLI wiring) supplies concrete
    ``db_reader`` and ``pdf_validator`` implementations; tests inject mocks.
    """
    invoked: list[str] = action_sink.get("invoked", [])
    requests: list[dict[str, Any]] = action_sink.get("requests", [])
    active_doc: SeededDoc | None = action_sink.get("active_doc")

    expected = _expected_outcome_for_seeded_doc(active_doc, invoked)
    outcome = SigningOutcome(detected=False, expected_outcome_inferred=expected)

    if not any("/sign/" in r.get("url", "") for r in requests):
        return outcome

    outcome.detected = True
    outcome.latency_ms = _compute_latency(requests)
    if active_doc is None:
        outcome.functional = {
            "status": "harness_error",
            "reason": "no active_doc recorded by tools",
        }
        return outcome

    row = db_reader(active_doc.entity, active_doc.id)
    if row is None:
        outcome.functional = {
            "status": "harness_error",
            "reason": f"row {active_doc.entity}/{active_doc.id} not found post-flow",
        }
        return outcome

    expected_status = _EXPECTED_STATUS.get(expected)
    final_status = row.get("status")
    if expected_status is None:
        status_ok = True
        expected_repr: str | None = None
    elif isinstance(expected_status, frozenset):
        status_ok = final_status in expected_status
        expected_repr = "|".join(sorted(expected_status))
    else:
        status_ok = final_status == expected_status
        expected_repr = expected_status

    if expected_status is not None and not status_ok:
        outcome.functional = {
            "status": "fail",
            "final_row_status": final_status,
            "audit_row_present": _has_audit_fields(row),
            "reason": (
                f"expected status={expected_repr} for outcome={expected}, got {final_status}"
            ),
        }
    else:
        outcome.functional = {
            "status": "pass",
            "final_row_status": final_status,
            "audit_row_present": _has_audit_fields(row),
            "reason": None,
        }

    pdf_path = row.get("signed_document")
    if pdf_path:
        try:
            outcome.signature_integrity = pdf_validator(pdf_path)
        except Exception as exc:
            outcome.signature_integrity = {"valid": False, "error": repr(exc)}

    return outcome
