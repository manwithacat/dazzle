"""Tests for the `slug:` field primitive (#1288 Phase 1 + validator).

Covers:
    * Parser accepts `slug` as a field type and produces FieldTypeKind.SLUG
    * Entity converter injects ValidatorKind.SLUG into the validator list
    * Generated Pydantic model rejects malformed slugs at the request boundary
    * Slug validator helper enforces every documented rule
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.converters.entity_converter import _extract_validators
from dazzle.http.runtime.model_generator import generate_create_schema
from dazzle.http.runtime.slug_validator import (
    SLUG_MAX_LEN,
    SLUG_MIN_LEN,
    validate_slug,
)
from dazzle.http.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
    ValidatorKind,
)

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_accepts_slug_field_type():
    """`slug` is a recognized field type and produces FieldTypeKind.SLUG."""
    src = """
module test_app

app test_app "Test"

entity Tenant "Tenant":
  id: uuid pk
  handle: slug required
"""
    _module, _app, _title, _config, _uses, fragment = parse_dsl(src, Path("<test>"))
    tenant = next(e for e in fragment.entities if e.name == "Tenant")
    handle = next(f for f in tenant.fields if f.name == "handle")
    assert handle.type.kind == ir.FieldTypeKind.SLUG


# ---------------------------------------------------------------------------
# Converter — validator inject
# ---------------------------------------------------------------------------


def test_entity_converter_injects_slug_validator():
    """A slug-typed field gets ValidatorKind.SLUG added to its validator list."""
    slug_field = ir.FieldSpec(
        name="handle",
        type=ir.FieldType(kind=ir.FieldTypeKind.SLUG),
        modifiers=[ir.FieldModifier.REQUIRED],
    )
    validators = _extract_validators(slug_field)
    kinds = [v.kind for v in validators]
    assert ValidatorKind.SLUG in kinds


# ---------------------------------------------------------------------------
# Pydantic model generation — runtime enforcement
# ---------------------------------------------------------------------------


def _slug_entity() -> EntitySpec:
    return EntitySpec(
        name="Tenant",
        verbose_name="Tenant",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=False,
            ),
            FieldSpec(
                name="handle",
                type=FieldType(kind="scalar", scalar_type=ScalarType.SLUG),
                required=True,
            ),
        ],
    )


def test_generated_model_accepts_valid_slug():
    Schema = generate_create_schema(_slug_entity())
    instance = Schema(handle="acme-corp")
    assert instance.handle == "acme-corp"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "value",
    [
        "ab",  # too short
        "a" * (SLUG_MAX_LEN + 1),  # too long
        "-leading",
        "trailing-",
        "double--hyphen",
        "UPPER",
        "has space",
        "has_underscore",
    ],
)
def test_generated_model_rejects_invalid_slug(value):
    Schema = generate_create_schema(_slug_entity())
    with pytest.raises(ValidationError):
        Schema(handle=value)


# ---------------------------------------------------------------------------
# Validator helper unit tests
# ---------------------------------------------------------------------------


def test_validate_slug_happy_path():
    assert validate_slug("acme") == "acme"
    assert validate_slug("a" * SLUG_MIN_LEN) == "a" * SLUG_MIN_LEN
    assert validate_slug("a" * SLUG_MAX_LEN) == "a" * SLUG_MAX_LEN
    assert validate_slug("acme-corp-2026") == "acme-corp-2026"


def test_validate_slug_length_messages():
    with pytest.raises(ValueError, match="at least"):
        validate_slug("ab")
    with pytest.raises(ValueError, match="at most"):
        validate_slug("a" * (SLUG_MAX_LEN + 1))


def test_validate_slug_double_hyphen_message():
    with pytest.raises(ValueError, match="double hyphens"):
        validate_slug("ac--me")


def test_validate_slug_format_message():
    with pytest.raises(ValueError, match="lowercase"):
        validate_slug("UPPER")
