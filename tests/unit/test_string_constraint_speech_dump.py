"""Length/pattern 422 speech must not dump String / slug must (oral #205)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field, ValidationError

from dazzle.http.runtime.htmx import (
    clerk_pydantic_constraint_speech,
    clerk_pydantic_type_speech,
    json_or_htmx_error,
)
from dazzle.http.runtime.model_generator import generate_create_schema
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
from dazzle.render.filters import clerk_form_error_field_label

SIMPLE = Path("examples/simple_task")
JOIN = Path("examples/domain_join_co")


def _request(method: str, *, htmx: bool = True, trigger: str = "title") -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = trigger
    return SimpleNamespace(method=method, headers=headers, query_params={})


def _task_like() -> EntitySpec:
    return EntitySpec(
        name="Task",
        description="simple_task Task title max_length",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                required=True,
            ),
        ],
    )


def _workspace_like() -> EntitySpec:
    return EntitySpec(
        name="Workspace",
        description="domain_join_co Workspace slug",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="slug",
                type=FieldType(kind="scalar", scalar_type=ScalarType.SLUG),
                required=True,
            ),
            FieldSpec(
                name="name",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=120),
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


def test_simple_task_title_max_length_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    assert 'entity Task "Task":' in block
    assert "title: str(200) required" in block
    create = block.split('surface task_create "Create Task":', 1)[1]
    assert 'field title "Title"' in create.split("surface ", 1)[0]
    edit = block.split('surface task_edit "Edit Task":', 1)[1]
    assert 'field title "Title"' in edit.split("surface ", 1)[0]


def test_domain_join_workspace_slug_is_live() -> None:
    block = (JOIN / "dsl" / "domain.dsl").read_text()
    assert 'entity Workspace "Workspace":' in block
    assert "slug: slug required" in block
    listing = block.split('surface workspace_list "Workspaces":', 1)[1]
    assert 'field slug "Slug"' in listing.split("surface ", 1)[0]


def test_clerk_constraint_speech_leftover_and_empty() -> None:
    assert (
        clerk_pydantic_constraint_speech(
            {
                "type": "string_too_long",
                "input": "zzzzzz",
                "msg": "String should have at most 5 characters",
                "ctx": {"max_length": 5},
            }
        )
        == "'zzzzzz' is too long (at most 5 characters)"
    )
    assert clerk_form_error_field_label("title") == "Title"
    leftover = clerk_pydantic_constraint_speech(
        {
            "type": "string_too_short",
            "input": "ab",
            "msg": "String should have at least 3 characters",
            "ctx": {"min_length": 3},
        }
    )
    assert leftover == "'ab' is too short (at least 3 characters)"
    assert "String should" not in leftover
    pattern = clerk_pydantic_constraint_speech(
        {
            "type": "string_pattern_mismatch",
            "input": "ZZZ",
            "msg": "String should match pattern '^[a-z0-9-]+$'",
            "ctx": {"pattern": "^[a-z0-9-]+$"},
        }
    )
    assert pattern == "'ZZZ' is not the expected format"
    assert "^[a-z0-9-]+$" not in pattern
    assert "String should" not in pattern
    long_dump = clerk_pydantic_constraint_speech(
        {
            "type": "string_too_long",
            "input": "x" * 201,
            "msg": "String should have at most 200 characters",
            "ctx": {"max_length": "200"},
        }
    )
    assert long_dump == "too long (at most 200 characters)"
    assert "String" not in (long_dump or "")
    slug_fmt = clerk_pydantic_constraint_speech(
        {
            "type": "value_error",
            "input": "ZZZ",
            "msg": (
                "Value error, slug must be lowercase letters, digits, and hyphens; "
                "must start and end with a letter or digit"
            ),
        }
    )
    assert slug_fmt == "'ZZZ' must be lowercase letters, digits, and hyphens"
    assert "Value error" not in (slug_fmt or "")
    assert "slug must" not in (slug_fmt or "")
    # Enum AfterValidator / type-parse stay on their helpers (oral #203 / #204).
    enum_msg = "Invalid value 'zzz' for 'Status'. Allowed: Todo, In Progress"
    assert clerk_pydantic_constraint_speech({"type": "value_error", "msg": enum_msg}) is None
    assert clerk_pydantic_type_speech({"type": "value_error", "msg": enum_msg}) == enum_msg
    assert clerk_pydantic_constraint_speech({"type": "missing", "msg": "Field required"}) is None
    assert (
        clerk_pydantic_constraint_speech(
            {"type": "date_from_datetime_parsing", "input": "zzz", "msg": "x"}
        )
        is None
    )


def test_create_title_speech_is_clerk_not_string_type() -> None:
    Schema = generate_create_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(title="x" * 201)
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "string_too_long" in kinds
    loc = [tuple(err.get("loc") or ()) for err in exc_info.value.errors()]
    assert ("title",) in loc


def test_create_slug_speech_is_value_error_not_regex() -> None:
    Schema = generate_create_schema(_workspace_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(slug="ZZZ", name="Acme")
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "value_error" in kinds
    msgs = " ".join(str(err.get("msg") or "") for err in exc_info.value.errors())
    assert "slug must" in msgs.lower()


class _PatternProbe(BaseModel):
    code: str = Field(min_length=3, pattern=r"^[a-z0-9-]+$")


def test_pattern_model_is_string_pattern_mismatch() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _PatternProbe(code="ZZZ")
    kinds = {err.get("type") for err in exc_info.value.errors()}
    assert "string_pattern_mismatch" in kinds


def test_htmx_title_422_is_clerk_not_string() -> None:
    Schema = generate_create_schema(_task_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(title="x" * 201)
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST"), errors)
    body = bytes(resp.body).decode()
    assert "Title: too long (at most 200 characters)" in body
    assert "String should" not in body
    assert "string_too_long" not in body
    assert "title:" not in body
    json_resp = json_or_htmx_error(
        SimpleNamespace(method="POST", headers={}, query_params={}),
        errors,
    )
    payload = json_resp.body
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    assert b'"title"' in payload
    assert b"String should have at most 200 characters" in payload
    assert b"too long (at most 200 characters)" not in payload


def test_htmx_slug_422_is_clerk_not_schema_type() -> None:
    Schema = generate_create_schema(_workspace_like())
    with pytest.raises(ValidationError) as exc_info:
        Schema(slug="ZZZ", name="Acme")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST", trigger="slug"), errors)
    body = bytes(resp.body).decode()
    assert "Slug: 'ZZZ' must be lowercase letters, digits, and hyphens" in body
    assert "Value error" not in body
    assert "slug must" not in body
    assert "slug:" not in body
    json_resp = json_or_htmx_error(
        SimpleNamespace(method="POST", headers={}, query_params={}),
        errors,
    )
    payload = json_resp.body
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    assert b'"slug"' in payload
    assert b"slug must" in payload
    assert b"Value error" in payload


def test_htmx_pattern_422_does_not_dump_regex() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _PatternProbe(code="ZZZ")
    errors = _jsonable_errors(exc_info.value)
    resp = json_or_htmx_error(_request("POST", trigger="code"), errors)
    body = bytes(resp.body).decode()
    assert "'ZZZ' is not the expected format" in body
    assert "^[a-z0-9-]+$" not in body
    assert "String should match pattern" not in body


def test_leftover_zzz_invents_no_constraint() -> None:
    resp = json_or_htmx_error(
        _request("POST"),
        [
            {
                "loc": ["body", "zzz"],
                "type": "string_too_long",
                "msg": "String should have at most 5 characters",
                "input": "ghost",
                "ctx": {"max_length": 5},
            }
        ],
    )
    body = bytes(resp.body).decode()
    assert "zzz: 'ghost' is too long (at most 5 characters)" in body
    assert "Zzz:" not in body
    assert "Ghost" not in body
    slug = json_or_htmx_error(
        _request("POST", trigger="slug"),
        [
            {
                "loc": ["body", "ghost"],
                "type": "value_error",
                "msg": "Value error, slug must be lowercase letters, digits, and hyphens",
                "input": "ZZZ",
            }
        ],
    )
    slug_body = bytes(slug.body).decode()
    assert "ghost: 'ZZZ' must be lowercase letters, digits, and hyphens" in slug_body
    assert "Ghost:" not in slug_body
    assert "slug must" not in slug_body
