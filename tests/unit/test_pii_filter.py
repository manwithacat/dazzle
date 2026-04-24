"""Tests for dazzle.compliance.analytics.pii_filter (v0.61.0)."""

from __future__ import annotations

import pytest

from dazzle.compliance.analytics import PIIFilterResult, strip_pii
from dazzle.core.ir import (
    FieldSpec,
    FieldType,
    FieldTypeKind,
    PIIAnnotation,
    PIICategory,
    PIISensitivity,
)


@pytest.fixture
def fields_map() -> dict[str, FieldSpec]:
    """A mix of PII-annotated and non-annotated fields."""
    return {
        "name": FieldSpec(
            name="name",
            type=FieldType(kind=FieldTypeKind.STR, max_length=200),
            pii=PIIAnnotation(category=PIICategory.IDENTITY),
        ),
        "email": FieldSpec(
            name="email",
            type=FieldType(kind=FieldTypeKind.STR, max_length=200),
            pii=PIIAnnotation(category=PIICategory.CONTACT),
        ),
        "ssn": FieldSpec(
            name="ssn",
            type=FieldType(kind=FieldTypeKind.STR, max_length=20),
            pii=PIIAnnotation(
                category=PIICategory.IDENTITY,
                sensitivity=PIISensitivity.SPECIAL_CATEGORY,
            ),
        ),
        "surface": FieldSpec(
            name="surface",
            type=FieldType(kind=FieldTypeKind.STR, max_length=50),
        ),
    }


class TestStripPii:
    def test_default_strips_all_pii(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii(
            {"name": "Alice", "email": "a@b", "surface": "dashboard"},
            fields_map,
        )
        assert result.kept == {"surface": "dashboard"}
        assert sorted(result.dropped_fields) == ["email", "name"]
        assert result.special_category_blocked == 0

    def test_opt_in_keeps_field(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii(
            {"name": "Alice", "email": "a@b", "surface": "x"},
            fields_map,
            opt_in={"email"},
        )
        assert result.kept == {"email": "a@b", "surface": "x"}
        assert result.dropped_fields == ["name"]

    def test_special_category_blocked_even_when_opted_in(
        self, fields_map: dict[str, FieldSpec]
    ) -> None:
        result = strip_pii(
            {"ssn": "111-22-3333", "surface": "x"},
            fields_map,
            opt_in={"ssn"},
        )
        assert "ssn" not in result.kept
        assert result.kept == {"surface": "x"}
        assert result.special_category_blocked == 1

    def test_special_category_explicit_unlock(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii(
            {"ssn": "111", "surface": "x"},
            fields_map,
            opt_in={"ssn"},
            include_special_category=True,
        )
        assert result.kept == {"ssn": "111", "surface": "x"}
        assert result.special_category_blocked == 0

    def test_unknown_field_passes_through(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii(
            {"unknown_key": "value", "email": "e"},
            fields_map,
        )
        assert result.kept == {"unknown_key": "value"}
        assert result.dropped_fields == ["email"]

    def test_empty_input(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii({}, fields_map)
        assert result.kept == {}
        assert result.dropped_fields == []

    def test_empty_fields_map(self) -> None:
        # Every key in data is unknown → passed through.
        result = strip_pii({"email": "a", "phone": "b"}, {})
        assert result.kept == {"email": "a", "phone": "b"}
        assert result.dropped_fields == []

    def test_opt_in_accepts_frozenset(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii(
            {"email": "a"},
            fields_map,
            opt_in=frozenset({"email"}),
        )
        assert result.kept == {"email": "a"}

    def test_result_is_immutable_structure(self, fields_map: dict[str, FieldSpec]) -> None:
        result = strip_pii({"name": "A"}, fields_map)
        assert isinstance(result, PIIFilterResult)
        # Dataclass is frozen — writes must raise FrozenInstanceError.
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.kept = {}  # type: ignore[misc]


class TestPiiFilterResult:
    def test_default_init(self) -> None:
        r = PIIFilterResult(kept={"a": 1})
        assert r.dropped_fields == []
        assert r.special_category_blocked == 0
