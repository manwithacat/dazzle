"""Tests for ``_strategy_value_obviously_wrong`` — #821.

Blueprint authoring drift regularly produces strategy/field-intent
mismatches. The heuristic guard drops obviously-bad values so rows
land in the DB with the offending field NULL rather than crashing
the seed on a type-cast failure.
"""

from __future__ import annotations

from dazzle.core.ir.demo_blueprint import FieldPattern, FieldStrategy
from dazzle.demo_data.blueprint_generator import _strategy_value_obviously_wrong


def _pat(field_name: str, strategy: FieldStrategy) -> FieldPattern:
    return FieldPattern(field_name=field_name, strategy=strategy)


class TestStrategyValueWrong:
    """Catches the common blueprint authoring-drift patterns."""

    def test_date_relative_on_date_field_is_ok(self) -> None:
        p = _pat("created_at", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is False

    def test_date_relative_on_ref_field_is_wrong(self) -> None:
        p = _pat("created_by", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_date_relative_on_numeric_field_is_wrong(self) -> None:
        p = _pat("error_rate", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_date_relative_on_url_field_is_wrong(self) -> None:
        p = _pat("avatar_url", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, "2026-01-23") is True

    def test_lorem_on_ref_field_is_wrong(self) -> None:
        """E.g. assigned_to (ref User) populated by free_text_lorem."""
        p = _pat("assigned_to", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "Aut fugit.") is True

    def test_uuid_on_ref_field_is_ok(self) -> None:
        p = _pat("assigned_to", FieldStrategy.FOREIGN_KEY)
        assert _strategy_value_obviously_wrong(p, "550e8400-e29b-41d4-a716-446655440000") is False

    def test_lorem_on_text_field_is_ok(self) -> None:
        p = _pat("description", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "Some description text") is False

    def test_non_date_string_on_date_field_is_ok(self) -> None:
        """Only the YYYY-MM-DD shape triggers date-mismatch; other
        strings on date-looking fields are not rejected by this
        heuristic."""
        p = _pat("deadline", FieldStrategy.STATIC_LIST)
        assert _strategy_value_obviously_wrong(p, "later") is False

    def test_none_value_not_flagged(self) -> None:
        p = _pat("created_by", FieldStrategy.DATE_RELATIVE)
        assert _strategy_value_obviously_wrong(p, None) is False

    def test_created_by_detected_as_ref_name(self) -> None:
        p = _pat("created_by", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "lorem") is True

    def test_foreign_id_suffix_detected_as_ref(self) -> None:
        p = _pat("system_id", FieldStrategy.FREE_TEXT_LOREM)
        assert _strategy_value_obviously_wrong(p, "lorem") is True
