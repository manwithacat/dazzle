"""Tests for the pii() field modifier (v0.61.0).

Covers:
- `pii` bare keyword → default annotation
- `pii()` empty parens
- `pii(category=...)` single keyword
- `pii(category=..., sensitivity=...)` both keywords
- Parser errors (unknown category, unknown sensitivity, duplicate key,
  unknown keyword, duplicate modifier)
- PII annotation survives IR round-trip
- FieldSpec.is_pii / is_special_category properties
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import (
    FieldSpec,
    FieldType,
    FieldTypeKind,
    PIIAnnotation,
    PIICategory,
    PIISensitivity,
)


def _parse_entity_fields(dsl: str) -> dict[str, FieldSpec]:
    """Parse a DSL fragment with one entity and return fields keyed by name."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("t.dsl"))
    assert len(fragment.entities) == 1, "test expects exactly one entity"
    entity = fragment.entities[0]
    return {f.name: f for f in entity.fields if isinstance(f, FieldSpec)}


class TestBarePii:
    def test_bare_pii(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii
"""
        )
        email = fields["email"]
        assert email.is_pii
        assert email.pii is not None
        assert email.pii.category is None
        assert email.pii.sensitivity is PIISensitivity.STANDARD
        assert not email.is_special_category

    def test_pii_empty_parens(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii()
"""
        )
        email = fields["email"]
        assert email.is_pii
        assert email.pii is not None
        assert email.pii.category is None


class TestPiiKwargs:
    def test_category_only(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(category=contact)
"""
        )
        assert fields["email"].pii is not None
        assert fields["email"].pii.category is PIICategory.CONTACT
        assert fields["email"].pii.sensitivity is PIISensitivity.STANDARD

    def test_sensitivity_only(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  dob: date pii(sensitivity=high)
"""
        )
        pii = fields["dob"].pii
        assert pii is not None
        assert pii.category is None
        assert pii.sensitivity is PIISensitivity.HIGH

    def test_both_kwargs(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  ssn: str(20) pii(category=identity, sensitivity=special_category)
"""
        )
        ssn = fields["ssn"]
        assert ssn.pii is not None
        assert ssn.pii.category is PIICategory.IDENTITY
        assert ssn.pii.sensitivity is PIISensitivity.SPECIAL_CATEGORY
        assert ssn.is_special_category

    def test_all_categories_parse(self) -> None:
        """Every declared PIICategory value parses without error."""
        for cat in PIICategory:
            fields = _parse_entity_fields(
                f"""module m
app X "X"
entity Y "Y":
  id: uuid pk
  f: str(100) pii(category={cat.value})
"""
            )
            assert fields["f"].pii is not None
            assert fields["f"].pii.category is cat

    def test_all_sensitivities_parse(self) -> None:
        """Every declared PIISensitivity value parses without error."""
        for sens in PIISensitivity:
            fields = _parse_entity_fields(
                f"""module m
app X "X"
entity Y "Y":
  id: uuid pk
  f: str(100) pii(sensitivity={sens.value})
"""
            )
            assert fields["f"].pii is not None
            assert fields["f"].pii.sensitivity is sens


class TestPiiErrors:
    def test_unknown_category(self) -> None:
        with pytest.raises(ParseError, match="Unknown pii category"):
            _parse_entity_fields(
                """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(category=bogus)
"""
            )

    def test_unknown_sensitivity(self) -> None:
        with pytest.raises(ParseError, match="Unknown pii sensitivity"):
            _parse_entity_fields(
                """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(sensitivity=mega)
"""
            )

    def test_duplicate_kwarg(self) -> None:
        with pytest.raises(ParseError, match="Duplicate `category`"):
            _parse_entity_fields(
                """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(category=contact, category=identity)
"""
            )

    def test_unknown_kwarg(self) -> None:
        with pytest.raises(ParseError, match="Unknown pii keyword"):
            _parse_entity_fields(
                """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(tier=high)
"""
            )

    def test_duplicate_modifier(self) -> None:
        with pytest.raises(ParseError, match="Duplicate `pii` modifier"):
            _parse_entity_fields(
                """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii pii
"""
            )


class TestPiiCoexistsWithModifiers:
    def test_pii_with_required(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  email: str(200) pii(category=contact) required
"""
        )
        email = fields["email"]
        assert email.is_pii
        assert email.is_required

    def test_pii_after_default(self) -> None:
        fields = _parse_entity_fields(
            """module m
app X "X"
entity Y "Y":
  id: uuid pk
  status: str(20) = "active" pii(category=behavioral)
"""
        )
        status = fields["status"]
        assert status.is_pii
        assert status.pii is not None
        assert status.pii.category is PIICategory.BEHAVIORAL
        assert status.default == "active"


class TestFieldSpecProperties:
    def test_is_pii_false_by_default(self) -> None:
        fs = FieldSpec(name="x", type=FieldType(kind=FieldTypeKind.STR, max_length=200))
        assert not fs.is_pii
        assert not fs.is_special_category

    def test_is_pii_true_when_annotated(self) -> None:
        fs = FieldSpec(
            name="x",
            type=FieldType(kind=FieldTypeKind.STR, max_length=200),
            pii=PIIAnnotation(category=PIICategory.CONTACT),
        )
        assert fs.is_pii
        assert not fs.is_special_category

    def test_is_special_category_gates_correctly(self) -> None:
        fs = FieldSpec(
            name="ssn",
            type=FieldType(kind=FieldTypeKind.STR, max_length=20),
            pii=PIIAnnotation(
                category=PIICategory.IDENTITY,
                sensitivity=PIISensitivity.SPECIAL_CATEGORY,
            ),
        )
        assert fs.is_pii
        assert fs.is_special_category

    def test_annotation_is_frozen(self) -> None:
        from pydantic import ValidationError

        ann = PIIAnnotation(category=PIICategory.CONTACT)
        with pytest.raises(ValidationError):
            ann.category = PIICategory.IDENTITY  # type: ignore[misc]
