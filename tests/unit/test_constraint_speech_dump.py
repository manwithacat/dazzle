"""Constraint 422 speech must not dump IssueReport / ticket_number (oral #201)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.htmx import json_or_htmx_error
from dazzle.http.runtime.repository import ConstraintViolationError, _translate_integrity_error
from dazzle.render.breadcrumbs import clerk_entity_noun
from dazzle.render.filters import clerk_form_error_field_label


def clerk_missing_ref_speech(ref_entity: object, ref_id: object, field_name: object) -> str:
    noun = clerk_entity_noun("" if ref_entity is None else str(ref_entity))
    field_label = clerk_form_error_field_label(field_name)
    rid = "" if ref_id is None else str(ref_id)
    return f"Referenced {noun} with ID '{rid}' not found (field: {field_label})"


FIELDTEST = Path("examples/fieldtest_hub")
SUPPORT = Path("examples/support_tickets")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "issue"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def test_fieldtest_issue_report_ref_is_live() -> None:
    block = (FIELDTEST / "dsl" / "app.dsl").read_text()
    assert 'entity IssueReport "Issue Report":' in block
    assert 'entity IssueNote "Issue Note":' in block
    assert "issue: ref IssueReport required" in block
    create = block.split('surface issue_note_create "Add Issue Note":', 1)[1]
    assert 'field issue "Issue"' in create.split("surface ", 1)[0]


def test_support_ticket_number_unique_is_live() -> None:
    block = (SUPPORT / "dsl" / "app.dsl").read_text()
    assert 'entity Ticket "Support Ticket":' in block
    assert "ticket_number: str(20) unique" in block
    assert 'field ticket_number "Ticket #"' in block


def test_clerk_constraint_entity_noun_leftover_and_sentinel() -> None:
    assert clerk_entity_noun("IssueReport") == "Issue Report"
    assert clerk_entity_noun("Ticket") == "Ticket"
    assert clerk_entity_noun("zzz") == "zzz"
    assert clerk_entity_noun("ghost") == "ghost"
    assert clerk_entity_noun("") == ""
    assert clerk_entity_noun(None) == ""


def test_missing_ref_speech_is_clerk_not_schema() -> None:
    rid = "550e8400-e29b-41d4-a716-446655440000"
    speech = clerk_missing_ref_speech("IssueReport", rid, "issue")
    assert "Issue Report" in speech
    assert "Issue" in speech
    assert rid in speech
    assert "IssueReport" not in speech
    assert "issue)" not in speech
    assert "(field: issue)" not in speech


def test_leftover_zzz_invents_no_ref() -> None:
    speech = clerk_missing_ref_speech("zzz", "ghost-id", "ghost")
    assert "zzz" in speech
    assert "ghost-id" in speech
    assert "ghost" in speech
    assert "Zzz" not in speech
    assert "Ghost" not in speech


def test_unique_constraint_speech_is_clerk_not_schema() -> None:
    exc = Exception(
        'duplicate key value violates unique constraint "ticket_ticket_number_key" '
        "DETAIL: Key (ticket_number)=(AAA-001) already exists."
    )
    err = _translate_integrity_error(exc, "Ticket")
    speech = str(err)
    assert err.constraint_type == "unique"
    assert err.field == "ticket_number"
    assert "Ticket Number" in speech
    assert "already exists" in speech
    assert "ticket_number" not in speech


def test_fk_constraint_speech_is_clerk_not_schema() -> None:
    exc = Exception(
        'insert or update on table "IssueNote" violates foreign key constraint '
        '"issuenote_issue_fkey" DETAIL: Key (issue)=(abc) is not present in table '
        '"IssueReport".'
    )
    err = _translate_integrity_error(exc, "IssueNote")
    speech = str(err)
    assert err.constraint_type == "foreign_key"
    assert err.field == "issue"
    assert "Issue Note" in speech
    assert "Issue" in speech
    assert "IssueNote" not in speech
    assert "IssueReport" not in speech
    assert "'issue'" not in speech


def test_leftover_unique_invents_no_entity() -> None:
    exc = Exception(
        'duplicate key value violates unique constraint "zzz_ghost_key" '
        "DETAIL: Key (ghost)=(x) already exists."
    )
    err = _translate_integrity_error(exc, "zzz")
    speech = str(err)
    assert err.field == "ghost"
    assert "zzz" in speech
    assert "ghost" in speech
    assert "Zzz" not in speech
    assert "Ghost" not in speech


def test_htmx_missing_ref_is_clerk_not_schema() -> None:
    rid = "550e8400-e29b-41d4-a716-446655440000"
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": [], "msg": clerk_missing_ref_speech("IssueReport", rid, "issue")}],
        error_type="invariant_violation",
    )
    body = bytes(resp.body).decode()
    assert "Issue Report" in body
    assert "IssueReport" not in body
    assert rid in body


def test_htmx_unique_loc_is_clerk_prefix_field_stays_identifier() -> None:
    err = ConstraintViolationError(
        f"A Ticket with this {clerk_form_error_field_label('ticket_number')} already exists",
        field="ticket_number",
        constraint_type="unique",
    )
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": [err.field], "msg": str(err)}],
        error_type="constraint_violation",
    )
    body = bytes(resp.body).decode()
    assert "Ticket Number" in body
    assert "ticket_number:" not in body
    assert err.field == "ticket_number"


def test_json_api_field_stays_identifier() -> None:
    err = _translate_integrity_error(
        Exception(
            'duplicate key value violates unique constraint "ticket_ticket_number_key" '
            "DETAIL: Key (ticket_number)=(AAA-001) already exists."
        ),
        "Ticket",
    )
    resp = json_or_htmx_error(
        _request("POST", htmx=False),
        [{"loc": [err.field], "msg": str(err)}],
        error_type="constraint_violation",
    )
    text = bytes(resp.body).decode()
    assert '"ticket_number"' in text
    assert "Ticket Number" in text
    assert err.field == "ticket_number"
