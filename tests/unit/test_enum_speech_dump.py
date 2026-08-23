"""Enum 422 speech must not dump in_progress (oral #203)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dazzle.http.runtime.htmx import json_or_htmx_error
from dazzle.http.runtime.model_generator import (
    clerk_enum_speech,
    generate_create_schema,
    generate_update_schema,
)
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
from dazzle.render.filters import clerk_form_error_field_label, clerk_stage_label

SIMPLE = Path("examples/simple_task")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "status"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def _task_like() -> EntitySpec:
    return EntitySpec(
        name="Task",
        description="simple_task Task status / priority enums",
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
                name="status",
                type=FieldType(kind="enum", enum_values=["todo", "in_progress", "review", "done"]),
                default="todo",
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="enum", enum_values=["low", "medium", "high", "urgent"]),
                default="medium",
            ),
        ],
    )


def test_simple_task_status_enum_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    assert 'entity Task "Task":' in block
    assert "status: enum[todo,in_progress,review,done]=todo" in block
    edit = block.split('surface task_edit "Edit Task":', 1)[1]
    assert 'field status "Status"' in edit.split("surface ", 1)[0]


def test_simple_task_priority_enum_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    assert "priority: enum[low,medium,high,urgent]=medium" in block
    create = block.split('surface task_create "Create Task":', 1)[1]
    assert 'field priority "Priority"' in create.split("surface ", 1)[0]


def test_clerk_enum_speech_leftover_and_empty() -> None:
    assert clerk_enum_speech("zzz", "status", ["todo", "in_progress"]) == (
        "Invalid value 'zzz' for 'Status'. Allowed: Todo, In Progress"
    )
    assert clerk_stage_label("in_progress") == "In Progress"
    assert clerk_form_error_field_label("status") == "Status"
    leftover = clerk_enum_speech("ghost", "zzz", ["ghost", "2abc"])
    assert "ghost" in leftover
    assert "zzz" in leftover
    assert "2abc" in leftover
    assert "Zzz" not in leftover
    assert "Ghost" not in leftover
    assert clerk_enum_speech("zzz", "", []) == "Invalid value 'zzz'. Allowed: "
    assert clerk_enum_speech(None, None, None) == "Invalid value ''. Allowed: "


def test_update_status_speech_is_clerk_not_schema() -> None:
    Schema = generate_update_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(status="zzz")
    speech = str(exc_info.value)
    assert "Invalid value 'zzz' for 'Status'" in speech
    assert "In Progress" in speech
    assert "Todo" in speech
    assert "Review" in speech
    assert "Done" in speech
    assert "for 'status'" not in speech
    assert "in_progress" not in speech
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("status",) in loc


def test_create_priority_speech_is_clerk_not_schema() -> None:
    Schema = generate_create_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(title="Ship", priority="zzz")
    speech = str(exc_info.value)
    assert "Invalid value 'zzz' for 'Priority'" in speech
    assert "Low" in speech
    assert "Urgent" in speech
    assert "for 'priority'" not in speech
    assert "low, medium" not in speech
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("priority",) in loc


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


def test_htmx_enum_422_is_clerk_not_schema() -> None:
    Schema = generate_update_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(status="zzz")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST"), errors)
    body = bytes(resp.body).decode()
    assert "Status" in body
    assert "In Progress" in body
    assert "zzz" in body
    assert "status:" not in body
    assert "in_progress" not in body
    json_resp = json_or_htmx_error(
        SimpleNamespace(method="POST", headers={}, query_params={}),
        errors,
    )
    payload = json_resp.body
    assert b'"status"' in payload
    assert b"In Progress" in payload
    assert b"in_progress" not in payload
    assert any(tuple(err.get("loc") or ()) == ("status",) for err in errors)
