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

    @pytest.mark.parametrize(
        ("data", "kwargs", "use_fields_map", "expected_kept", "expected_dropped"),
        [
            (
                {"name": "Alice", "email": "a@b", "surface": "x"},
                {"opt_in": {"email"}},
                True,
                {"email": "a@b", "surface": "x"},
                ["name"],
            ),
            (
                {"ssn": "111", "surface": "x"},
                {"opt_in": {"ssn"}, "include_special_category": True},
                True,
                {"ssn": "111", "surface": "x"},
                None,
            ),
            (
                {"unknown_key": "value", "email": "e"},
                {},
                True,
                {"unknown_key": "value"},
                ["email"],
            ),
            ({}, {}, True, {}, []),
            (
                {"email": "a", "phone": "b"},
                {},
                False,
                {"email": "a", "phone": "b"},
                [],
            ),
        ],
        ids=[
            "test_opt_in_keeps_field",
            "test_special_category_explicit_unlock",
            "test_unknown_field_passes_through",
            "test_empty_input",
            "test_empty_fields_map",
        ],
    )
    def test_strip_pii_cases(
        self,
        fields_map: dict[str, FieldSpec],
        data: dict,
        kwargs: dict,
        use_fields_map: bool,
        expected_kept: dict,
        expected_dropped: list | None,
    ) -> None:
        fmap = fields_map if use_fields_map else {}
        result = strip_pii(data, fmap, **kwargs)
        assert result.kept == expected_kept
        if expected_dropped is not None:
            assert result.dropped_fields == expected_dropped
        if "include_special_category" in kwargs and kwargs["include_special_category"]:
            assert result.special_category_blocked == 0

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
