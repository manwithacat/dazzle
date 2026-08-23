"""Decimal scale 422 speech must not dump Decimal input should (oral #206)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dazzle.http.runtime.htmx import (
    clerk_pydantic_constraint_speech,
    clerk_pydantic_type_speech,
    json_or_htmx_error,
)
from dazzle.http.runtime.model_generator import generate_create_schema
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
from dazzle.render.filters import clerk_form_error_field_label

INVOICE = Path("examples/invoice_ops")


def _request(method: str, *, htmx: bool = True, trigger: str = "amount") -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = trigger
    return SimpleNamespace(method=method, headers=headers, query_params={})


def _invoice_like() -> EntitySpec:
    return EntitySpec(
        name="Invoice",
        description="invoice_ops Invoice amount decimal(15,2)",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="invoice_number",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=40),
                required=True,
            ),
            FieldSpec(
                name="amount",
                type=FieldType(
                    kind="scalar",
                    scalar_type=ScalarType.DECIMAL,
                    precision=15,
                    scale=2,
                ),
                required=True,
            ),
        ],
    )


def _jsonable_errors(exc: ValidationError) -> list[dict[str, object]]:
    """Match exception_handlers: stringify pydantic ctx ValueError."""
    errors: list[dict[str, object]] = []
    for err in exc.errors():
        clean: dict[str, object] = {}
        for k, v in err.items():
            if k == "ctx" and isinstance(v, dict):
                clean[k] = {ck: str(cv) for ck, cv in v.items()}
            else:
                clean[k] = v
        errors.append(clean)
    return errors


def test_invoice_ops_amount_scale_is_live() -> None:
    block = (INVOICE / "dsl" / "entities.dsl").read_text()
    assert 'entity Invoice "Invoice":' in block
    assert "amount: decimal(15,2) required" in block
    surfaces = (INVOICE / "dsl" / "surfaces.dsl").read_text()
    create = surfaces.split('surface invoice_create "New Invoice":', 1)[1]
    assert 'field amount "Amount"' in create.split("surface ", 1)[0]


def test_clerk_decimal_speech_leftover_and_empty() -> None:
    assert (
        clerk_pydantic_constraint_speech(
            {
                "type": "decimal_max_places",
                "input": "12.345",
                "msg": "Decimal input should have no more than 2 decimal places",
                "ctx": {"decimal_places": 2},
            }
        )
        == "'12.345' has too many decimal places (at most 2)"
    )
    assert clerk_form_error_field_label("amount") == "Amount"
    leftover = clerk_pydantic_constraint_speech(
        {
            "type": "decimal_max_digits",
            "input": "123456789012345.12",
            "msg": "Decimal input should have no more than 15 digits in total",
            "ctx": {"max_digits": 15},
        }
    )
    assert leftover == "'123456789012345.12' has too many digits (at most 15)"
    assert "Decimal input" not in leftover
    empty = clerk_pydantic_constraint_speech(
        {
            "type": "decimal_max_places",
            "input": "x" * 60,
            "msg": "Decimal input should have no more than 2 decimal places",
            "ctx": {"decimal_places": "2"},
        }
    )
    assert empty == "has too many decimal places (at most 2)"
    assert "Decimal" not in (empty or "")
    # Type-parse leftover stays on the type helper (oral #204).
    assert (
        clerk_pydantic_constraint_speech(
            {"type": "decimal_parsing", "input": "zzz", "msg": "Input should be a valid decimal"}
        )
        is None
    )
    assert (
        clerk_pydantic_type_speech(
            {"type": "decimal_parsing", "input": "zzz", "msg": "Input should be a valid decimal"}
        )
        == "'zzz' is not a number"
    )
    assert clerk_pydantic_constraint_speech({"type": "missing", "msg": "Field required"}) is None
    assert (
        clerk_pydantic_constraint_speech(
            {
                "type": "string_too_long",
                "input": "x" * 201,
                "msg": "String should have at most 200 characters",
                "ctx": {"max_length": 200},
            }
        )
        == "too long (at most 200 characters)"
    )


def test_create_amount_speech_is_decimal_max_places() -> None:
    Schema = generate_create_schema(_invoice_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(invoice_number="INV-1", amount="12.345")
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "decimal_max_places" in kinds
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("amount",) in loc


def test_create_amount_digits_speech_is_decimal_max_digits() -> None:
    Schema = generate_create_schema(_invoice_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(invoice_number="INV-1", amount="123456789012345.12")
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "decimal_max_digits" in kinds


def test_htmx_amount_422_is_clerk_not_decimal_type() -> None:
    Schema = generate_create_schema(_invoice_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(invoice_number="INV-1", amount="12.345")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST"), errors)
    body = bytes(resp.body).decode()
    assert "Amount: '12.345' has too many decimal places (at most 2)" in body
    assert "Decimal input" not in body
    assert "decimal_max_places" not in body
    assert "amount:" not in body
    json_resp = json_or_htmx_error(
        SimpleNamespace(method="POST", headers={}, query_params={}),
        errors,
    )
    payload = json_resp.body
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    assert b'"amount"' in payload
    assert b"Decimal input should have no more than 2 decimal places" in payload
    assert b"has too many decimal places" not in payload


def test_htmx_leftover_zzz_is_type_parse_not_scale() -> None:
    Schema = generate_create_schema(_invoice_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(invoice_number="INV-1", amount="zzz")
    errors = _jsonable_errors(exc_info.value)
    kinds = {err.get("type") for err in errors}
    assert "decimal_parsing" in kinds
    assert "decimal_max_places" not in kinds
    resp = json_or_htmx_error(_request("POST"), errors)
    body = bytes(resp.body).decode()
    assert "Amount: 'zzz' is not a number" in body
    assert "Decimal input" not in body
    assert "Ghost" not in body


def test_leftover_zzz_invents_no_scale() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [
            {
                "loc": ["body", "zzz"],
                "type": "decimal_max_places",
                "msg": "Decimal input should have no more than 2 decimal places",
                "input": "12.345",
                "ctx": {"decimal_places": 2},
            }
        ],
    )
    body = bytes(resp.body).decode()
    assert "zzz: '12.345' has too many decimal places (at most 2)" in body
    assert "Zzz:" not in body
    assert "Amount:" not in body
    ghost = json_or_htmx_error(
        _request("POST", trigger="ghost"),
        [
            {
                "loc": ["body", "ghost"],
                "type": "decimal_max_digits",
                "msg": "Decimal input should have no more than 15 digits in total",
                "input": "123456789012345.12",
                "ctx": {"max_digits": 15},
            }
        ],
    )
    ghost_body = bytes(ghost.body).decode()
    assert "ghost: '123456789012345.12' has too many digits (at most 15)" in ghost_body
    assert "Ghost:" not in ghost_body
    assert "Decimal input" not in ghost_body


def test_two_place_amount_rides() -> None:
    Schema = generate_create_schema(_invoice_like())
    row = Schema(invoice_number="INV-1", amount="12.34")
    assert str(row.amount) == "12.34"


def test_live_invoice_create_schema_rejects_extra_pence() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entity

    spec = load_project_appspec(INVOICE)
    invoice = next(e for e in spec.domain.entities if e.name == "Invoice")
    Schema = generate_create_schema(convert_entity(invoice))
    with pytest.raises(ValidationError) as exc_info:
        Schema(
            tenant_id=uuid4(),
            invoice_number="INV-1",
            supplier=uuid4(),
            amount="12.345",
        )
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "decimal_max_places" in kinds
