"""Pydantic type 422 speech must not dump integer/UUID/date (oral #204)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dazzle.http.runtime.htmx import clerk_pydantic_type_speech, json_or_htmx_error
from dazzle.http.runtime.model_generator import generate_create_schema, generate_update_schema
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
from dazzle.render.filters import clerk_form_error_field_label

SIMPLE = Path("examples/simple_task")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "due_date"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def _task_like() -> EntitySpec:
    return EntitySpec(
        name="Task",
        description="simple_task Task due_date / title",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
            FieldSpec(
                name="due_date",
                type=FieldType(kind="scalar", scalar_type=ScalarType.DATE),
            ),
            FieldSpec(
                name="duration_minutes",
                type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
            ),
        ],
    )


def test_simple_task_due_date_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    assert 'entity Task "Task":' in block
    assert "due_date: date" in block
    edit = block.split('surface task_edit "Edit Task":', 1)[1]
    assert 'field due_date "Due Date"' in edit.split("surface ", 1)[0]


def test_clerk_pydantic_type_speech_leftover_and_empty() -> None:
    assert (
        clerk_pydantic_type_speech(
            {
                "type": "date_from_datetime_parsing",
                "input": "zzz",
                "msg": "Input should be a valid date or datetime, input is too short",
            }
        )
        == "'zzz' is not a valid date"
    )
    assert clerk_form_error_field_label("due_date") == "Due Date"
    leftover = clerk_pydantic_type_speech(
        {
            "type": "int_parsing",
            "input": "ghost",
            "msg": "Input should be a valid integer, unable to parse string as an integer",
        }
    )
    assert leftover == "'ghost' is not a number"
    assert "Ghost" not in leftover
    assert "integer" not in leftover
    uuid_speech = clerk_pydantic_type_speech(
        {
            "type": "uuid_parsing",
            "input": "zzz",
            "msg": "Input should be a valid UUID, invalid character: found `z` at 1",
        }
    )
    assert uuid_speech == "'zzz' is not a valid id"
    assert "UUID" not in uuid_speech
    assert clerk_pydantic_type_speech({"type": "int_parsing", "input": None, "msg": "x"}) == (
        "is not a number"
    )
    assert clerk_pydantic_type_speech({"type": "bool_parsing", "input": "zzz", "msg": "x"}) == (
        "'zzz' is not yes or no"
    )
    # Enum AfterValidator / required stay put (oral #203 / #198).
    enum_msg = "Invalid value 'zzz' for 'Status'. Allowed: Todo, In Progress"
    assert clerk_pydantic_type_speech({"type": "value_error", "msg": enum_msg, "input": "zzz"}) == (
        enum_msg
    )
    assert clerk_pydantic_type_speech({"type": "missing", "msg": "Field required"}) == (
        "Field required"
    )


def test_update_due_date_speech_is_clerk_not_python_type() -> None:
    Schema = generate_update_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(due_date="zzz")
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("due_date",) in loc
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert kinds & {
        "date_from_datetime_parsing",
        "date_parsing",
        "date_from_datetime",
        "date_type",
    }


def test_create_int_speech_is_clerk_not_integer() -> None:
    Schema = generate_create_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(title="Ship", duration_minutes="zzz")
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("duration_minutes",) in loc
    assert any(err.get("type") == "int_parsing" for err in exc_info.value.errors())


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


def test_htmx_date_422_is_clerk_not_python_type() -> None:
    Schema = generate_update_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(due_date="zzz")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST"), errors)
    body = bytes(resp.body).decode()
    assert "Due Date: 'zzz' is not a valid date" in body
    assert "zzz" in body
    assert "Input should be a valid date" not in body
    assert "datetime" not in body
    assert "due_date:" not in body
    json_resp = json_or_htmx_error(
        SimpleNamespace(method="POST", headers={}, query_params={}),
        errors,
    )
    payload = json_resp.body
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    assert b'"due_date"' in payload
    assert b"Input should be a valid date" in payload
    assert b"is not a valid date" not in payload
    assert any(tuple(err.get("loc") or ()) == ("due_date",) for err in errors)


def test_htmx_int_422_is_clerk_not_integer() -> None:
    Schema = generate_create_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(title="Ship", duration_minutes="zzz")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(
        SimpleNamespace(
            method="POST",
            headers={"HX-Request": "true", "HX-Trigger-Name": "duration_minutes"},
            query_params={},
        ),
        errors,
    )
    body = bytes(resp.body).decode()
    assert "Duration Minutes: 'zzz' is not a number" in body
    assert "integer" not in body
    assert "duration_minutes:" not in body


def test_leftover_zzz_invents_no_type() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [
            {
                "loc": ["body", "zzz"],
                "type": "date_from_datetime_parsing",
                "msg": "Input should be a valid date or datetime, input is too short",
                "input": "ghost",
            }
        ],
    )
    body = bytes(resp.body).decode()
    assert "zzz: 'ghost' is not a valid date" in body
    assert "Zzz:" not in body
    assert "Ghost" not in body
    ghost = json_or_htmx_error(
        _request("POST"),
        [
            {
                "loc": ["body", "ghost"],
                "type": "int_parsing",
                "msg": "Input should be a valid integer, unable to parse string as an integer",
                "input": "zzz",
            }
        ],
    )
    ghost_body = bytes(ghost.body).decode()
    assert "ghost: 'zzz' is not a number" in ghost_body
    assert "Ghost:" not in ghost_body
