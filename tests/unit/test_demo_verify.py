"""Tests for ``dazzle demo verify`` — the static blueprint checker (#821)."""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.core.ir.demo_blueprint import (
    DemoDataBlueprint,
    EntityBlueprint,
    FieldPattern,
    FieldStrategy,
)
from dazzle.core.ir.fields import FieldType, FieldTypeKind
from dazzle.demo_data.verify import verify_blueprint


def _mock_appspec(entities: list[MagicMock]) -> MagicMock:
    appspec = MagicMock()
    appspec.domain.entities = entities
    return appspec


def _mock_entity(name: str, fields: list[MagicMock]) -> MagicMock:
    e = MagicMock()
    e.name = name
    e.fields = fields
    return e


def _mock_field(
    name: str,
    kind: FieldTypeKind,
    *,
    required: bool = False,
    pk: bool = False,
    enum_values: list[str] | None = None,
    max_length: int | None = None,
) -> MagicMock:
    f = MagicMock()
    f.name = name
    f.required = required
    f.pk = pk
    f.type = FieldType(kind=kind, enum_values=enum_values or [], max_length=max_length)
    return f


def _blueprint_with(entity_name: str, patterns: list[FieldPattern]) -> DemoDataBlueprint:
    return DemoDataBlueprint(
        project_id="test",
        domain_description="test",
        entities=[EntityBlueprint(name=entity_name, row_count_default=5, field_patterns=patterns)],
    )


class TestStrategyTypeMismatch:
    def test_date_relative_on_str_is_error(self) -> None:
        appspec = _mock_appspec([_mock_entity("Task", [_mock_field("title", FieldTypeKind.STR)])])
        bp = _blueprint_with(
            "Task",
            [FieldPattern(field_name="title", strategy=FieldStrategy.DATE_RELATIVE)],
        )
        report = verify_blueprint(bp, appspec)
        errors = report.errors()
        assert len(errors) == 1
        assert errors[0].rule == "strategy_type_mismatch"

    def test_enum_weighted_on_enum_is_ok(self) -> None:
        appspec = _mock_appspec(
            [
                _mock_entity(
                    "Task",
                    [_mock_field("status", FieldTypeKind.ENUM, enum_values=["a", "b"])],
                )
            ]
        )
        bp = _blueprint_with(
            "Task",
            [
                FieldPattern(
                    field_name="status",
                    strategy=FieldStrategy.ENUM_WEIGHTED,
                    params={"enum_values": ["a", "b"], "weights": [1, 1]},
                )
            ],
        )
        assert not verify_blueprint(bp, appspec).has_errors

    def test_foreign_key_on_ref_is_ok(self) -> None:
        appspec = _mock_appspec(
            [_mock_entity("Task", [_mock_field("assignee", FieldTypeKind.REF)])]
        )
        bp = _blueprint_with(
            "Task",
            [FieldPattern(field_name="assignee", strategy=FieldStrategy.FOREIGN_KEY)],
        )
        assert not verify_blueprint(bp, appspec).has_errors

    def test_free_text_lorem_on_ref_is_error(self) -> None:
        """The very pattern that crashed /trial-cycle seed runs."""
        appspec = _mock_appspec(
            [_mock_entity("Ticket", [_mock_field("assigned_to", FieldTypeKind.REF)])]
        )
        bp = _blueprint_with(
            "Ticket",
            [FieldPattern(field_name="assigned_to", strategy=FieldStrategy.FREE_TEXT_LOREM)],
        )
        assert verify_blueprint(bp, appspec).has_errors


class TestUnknownRefs:
    def test_unknown_field_flagged(self) -> None:
        appspec = _mock_appspec([_mock_entity("Task", [_mock_field("title", FieldTypeKind.STR)])])
        bp = _blueprint_with(
            "Task",
            [FieldPattern(field_name="nonexistent", strategy=FieldStrategy.FREE_TEXT_LOREM)],
        )
        errors = verify_blueprint(bp, appspec).errors()
        assert any(v.rule == "unknown_field" for v in errors)

    def test_unknown_entity_flagged(self) -> None:
        appspec = _mock_appspec([])
        bp = _blueprint_with(
            "Ghost",
            [FieldPattern(field_name="x", strategy=FieldStrategy.FREE_TEXT_LOREM)],
        )
        errors = verify_blueprint(bp, appspec).errors()
        assert any(v.rule == "unknown_entity" for v in errors)


class TestEnumValueCheck:
    def test_enum_value_not_in_entity_flagged(self) -> None:
        appspec = _mock_appspec(
            [
                _mock_entity(
                    "Task",
                    [_mock_field("status", FieldTypeKind.ENUM, enum_values=["open", "done"])],
                )
            ]
        )
        bp = _blueprint_with(
            "Task",
            [
                FieldPattern(
                    field_name="status",
                    strategy=FieldStrategy.ENUM_WEIGHTED,
                    params={"enum_values": ["open", "archived"]},
                )
            ],
        )
        errors = verify_blueprint(bp, appspec).errors()
        assert any(v.rule == "enum_value_not_in_entity" for v in errors)


class TestLengthCap:
    def test_lorem_exceeds_field_length_warns(self) -> None:
        """Contact.phone: str(20) with 2-5-word lorem — what we fixed in contact_manager."""
        appspec = _mock_appspec(
            [_mock_entity("Contact", [_mock_field("phone", FieldTypeKind.STR, max_length=20)])]
        )
        bp = _blueprint_with(
            "Contact",
            [
                FieldPattern(
                    field_name="phone",
                    strategy=FieldStrategy.FREE_TEXT_LOREM,
                    params={"min_words": 2, "max_words": 5},
                )
            ],
        )
        warnings = verify_blueprint(bp, appspec).warnings()
        assert any(v.rule == "lorem_may_exceed_length_cap" for v in warnings)

    def test_short_lorem_within_cap_ok(self) -> None:
        appspec = _mock_appspec(
            [_mock_entity("Note", [_mock_field("title", FieldTypeKind.STR, max_length=200)])]
        )
        bp = _blueprint_with(
            "Note",
            [
                FieldPattern(
                    field_name="title",
                    strategy=FieldStrategy.FREE_TEXT_LOREM,
                    params={"min_words": 2, "max_words": 5},
                )
            ],
        )
        warnings = verify_blueprint(bp, appspec).warnings()
        assert not any(v.rule == "lorem_may_exceed_length_cap" for v in warnings)


class TestRequiredFieldCoverage:
    def test_required_field_without_pattern_warns(self) -> None:
        appspec = _mock_appspec(
            [
                _mock_entity(
                    "Task",
                    [
                        _mock_field("title", FieldTypeKind.STR, required=True),
                        _mock_field("priority", FieldTypeKind.STR, required=True),
                    ],
                )
            ]
        )
        bp = _blueprint_with(
            "Task",
            [FieldPattern(field_name="title", strategy=FieldStrategy.FREE_TEXT_LOREM)],
        )
        warnings = verify_blueprint(bp, appspec).warnings()
        assert any(
            v.rule == "required_field_not_covered" and v.field == "priority" for v in warnings
        )

    def test_pk_field_not_flagged(self) -> None:
        appspec = _mock_appspec(
            [_mock_entity("Task", [_mock_field("id", FieldTypeKind.UUID, pk=True)])]
        )
        bp = _blueprint_with("Task", [])
        warnings = verify_blueprint(bp, appspec).warnings()
        assert not any(v.field == "id" for v in warnings)


class TestReportShape:
    def test_has_errors_true_when_errors(self) -> None:
        appspec = _mock_appspec([])
        bp = _blueprint_with(
            "Ghost", [FieldPattern(field_name="x", strategy=FieldStrategy.UUID_GENERATE)]
        )
        report = verify_blueprint(bp, appspec)
        assert report.has_errors

    def test_has_errors_false_on_clean_blueprint(self) -> None:
        appspec = _mock_appspec(
            [_mock_entity("Task", [_mock_field("id", FieldTypeKind.UUID, pk=True)])]
        )
        bp = _blueprint_with(
            "Task", [FieldPattern(field_name="id", strategy=FieldStrategy.UUID_GENERATE)]
        )
        assert not verify_blueprint(bp, appspec).has_errors
