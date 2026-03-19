"""Tests for ref display name extraction (issue #402).

Verifies that _ref_display_name correctly resolves human-readable names
from FK reference dicts using the canonical display chain.
"""

from __future__ import annotations

from dazzle_ui.runtime.template_renderer import _ref_display_name


class TestRefDisplayName:
    """Tests for the canonical ref display chain."""

    def test_name_field(self) -> None:
        assert _ref_display_name({"id": "abc", "name": "Alice"}) == "Alice"

    def test_company_name_field(self) -> None:
        assert _ref_display_name({"id": "abc", "company_name": "Acme Ltd"}) == "Acme Ltd"

    def test_first_last_name(self) -> None:
        result = _ref_display_name({"id": "abc", "first_name": "John", "last_name": "Doe"})
        assert result == "John Doe"

    def test_first_name_only(self) -> None:
        result = _ref_display_name({"id": "abc", "first_name": "John"})
        assert result == "John"

    def test_title_field(self) -> None:
        assert _ref_display_name({"id": "abc", "title": "Fix the bug"}) == "Fix the bug"

    def test_email_field(self) -> None:
        assert _ref_display_name({"id": "abc", "email": "a@b.com"}) == "a@b.com"

    def test_fallback_to_id(self) -> None:
        assert _ref_display_name({"id": "abc-123"}) == "abc-123"

    def test_empty_dict(self) -> None:
        assert _ref_display_name({}) == ""

    def test_none_value(self) -> None:
        assert _ref_display_name(None) == ""

    def test_scalar_string(self) -> None:
        """Non-dict values pass through as strings."""
        assert _ref_display_name("some-uuid") == "some-uuid"

    def test_priority_name_over_company_name(self) -> None:
        """name takes priority over company_name."""
        result = _ref_display_name({"name": "Alice", "company_name": "Acme"})
        assert result == "Alice"

    def test_priority_company_name_over_title(self) -> None:
        """company_name takes priority over title."""
        result = _ref_display_name({"company_name": "Acme", "title": "CEO"})
        assert result == "Acme"

    def test_forename_surname(self) -> None:
        """UK naming convention: forename + surname (#409)."""
        result = _ref_display_name({"id": "abc", "forename": "James", "surname": "Barlow"})
        assert result == "James Barlow"

    def test_forename_only(self) -> None:
        result = _ref_display_name({"id": "abc", "forename": "James"})
        assert result == "James"

    def test_first_name_takes_priority_over_forename(self) -> None:
        """first_name/last_name is checked before forename/surname."""
        result = _ref_display_name(
            {
                "id": "abc",
                "first_name": "John",
                "last_name": "Doe",
                "forename": "James",
                "surname": "Barlow",
            }
        )
        assert result == "John Doe"

    def test_first_string_fallback(self) -> None:
        """Entities with non-standard display fields use first string value (#479)."""
        result = _ref_display_name({"id": "abc-123", "component_name": "Reading Comprehension"})
        assert result == "Reading Comprehension"

    def test_first_string_skips_timestamps(self) -> None:
        """Timestamp fields are skipped in the first-string fallback."""
        result = _ref_display_name(
            {
                "id": "abc",
                "created_at": "2026-01-01T00:00:00Z",
                "question_text": "What is 2+2?",
            }
        )
        assert result == "What is 2+2?"

    def test_first_string_skips_long_values(self) -> None:
        """Very long strings (>=200 chars) are skipped — likely not display names."""
        result = _ref_display_name({"id": "abc", "blob": "x" * 200})
        assert result == "abc"

    def test_custom_fallback(self) -> None:
        assert _ref_display_name(None, fallback="N/A") == "N/A"

    def test_display_field_override(self) -> None:
        """Entity display_field injects __display__ key, used first (#555)."""
        result = _ref_display_name(
            {"id": "abc", "name": "Fallback", "__display__": "Preferred Name"}
        )
        assert result == "Preferred Name"

    def test_display_field_overrides_well_known(self) -> None:
        """__display__ takes priority over all well-known fields."""
        result = _ref_display_name(
            {"id": "abc", "name": "Alice", "title": "CEO", "__display__": "trading_name_value"}
        )
        assert result == "trading_name_value"

    def test_display_field_empty_falls_through(self) -> None:
        """Empty __display__ falls through to normal chain."""
        result = _ref_display_name({"id": "abc", "name": "Alice", "__display__": ""})
        assert result == "Alice"
