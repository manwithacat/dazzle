"""HTMX form errors must not dump first_name (oral #198)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.htmx import json_or_htmx_error
from dazzle.render.filters import clerk_form_error_field_label

CONTACT = Path("examples/contact_manager")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "first_name"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def test_contact_first_name_form_label_is_live() -> None:
    block = (CONTACT / "dsl" / "app.dsl").read_text()
    assert 'entity Contact "Contact":' in block
    assert "first_name: str(100) required" in block
    create = block.split('surface contact_create "Create Contact":', 1)[1]
    assert 'field first_name "First Name"' in create.split("surface ", 1)[0]


def test_clerk_form_error_field_label_leftover_and_empty() -> None:
    assert clerk_form_error_field_label("first_name") == "First Name"
    assert clerk_form_error_field_label("signatory_email") == "Signatory Email"
    assert clerk_form_error_field_label("scope_summary") == "Scope Summary"
    assert clerk_form_error_field_label("zzz") == "zzz"
    assert clerk_form_error_field_label("ghost") == "ghost"
    assert clerk_form_error_field_label("") == ""
    assert clerk_form_error_field_label(None) == ""


def test_htmx_form_error_is_clerk_not_schema_key() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": ["body", "first_name"], "msg": "Field required"}],
    )
    body = bytes(resp.body).decode()
    assert "First Name: Field required" in body
    assert "first_name:" not in body
    nested = json_or_htmx_error(
        _request("POST"),
        [{"loc": ["body", "items", 0, "signatory_email"], "msg": "Field required"}],
    )
    nested_body = bytes(nested.body).decode()
    assert "Signatory Email: Field required" in nested_body
    assert "signatory_email:" not in nested_body


def test_leftover_zzz_invents_no_field() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": ["body", "zzz"], "msg": "Field required"}],
    )
    body = bytes(resp.body).decode()
    assert "zzz: Field required" in body
    assert "Zzz:" not in body
    ghost = json_or_htmx_error(
        _request("POST"),
        [{"loc": ["body", "ghost"], "msg": "Field required"}],
    )
    ghost_body = bytes(ghost.body).decode()
    assert "ghost: Field required" in ghost_body
    assert "Ghost:" not in ghost_body


def test_empty_loc_invents_no_field() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": ["body"], "msg": "Submission failed"}],
    )
    body = bytes(resp.body).decode()
    assert "Submission failed" in body
    assert "First Name:" not in body
    assert "Body:" not in body


def test_json_api_loc_stays_schema_key() -> None:
    resp = json_or_htmx_error(
        _request("POST", htmx=False),
        [{"loc": ["body", "first_name"], "msg": "Field required"}],
    )
    assert resp.status_code == 422
    payload = resp.body
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    text = bytes(payload).decode()
    assert "first_name" in text
    assert "First Name" not in text
