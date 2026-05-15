"""Tests for ref display name extraction (issue #402).

Verifies that _ref_display_name correctly resolves human-readable names
from FK reference dicts using the canonical display chain.
"""

import pytest

from dazzle.render.filters import _ref_display_name


class TestRefDisplayName:
    """Tests for the canonical ref display chain."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            # --- Single well-known field maps to its content ---
            ({"id": "abc", "name": "Alice"}, "Alice"),
            ({"id": "abc", "company_name": "Acme Ltd"}, "Acme Ltd"),
            ({"id": "abc", "first_name": "John", "last_name": "Doe"}, "John Doe"),
            ({"id": "abc", "first_name": "John"}, "John"),
            ({"id": "abc", "title": "Fix the bug"}, "Fix the bug"),
            ({"id": "abc", "email": "a@b.com"}, "a@b.com"),
            # --- Fallbacks ---
            ({"id": "abc-123"}, "abc-123"),  # only id → use id
            ({}, ""),  # empty dict
            # --- UK naming convention (#409) ---
            ({"id": "abc", "forename": "James", "surname": "Barlow"}, "James Barlow"),
            ({"id": "abc", "forename": "James"}, "James"),
            # --- Display-field override (#555): __display__ injected by IR ---
            (
                {"id": "abc", "name": "Fallback", "__display__": "Preferred Name"},
                "Preferred Name",
            ),
            (
                {
                    "id": "abc",
                    "name": "Alice",
                    "title": "CEO",
                    "__display__": "trading_name_value",
                },
                "trading_name_value",
            ),
            (
                {"id": "abc", "name": "Alice", "__display__": ""},
                "Alice",  # empty __display__ falls through to normal chain
            ),
            # --- Priority chain ---
            ({"name": "Alice", "company_name": "Acme"}, "Alice"),
            ({"company_name": "Acme", "title": "CEO"}, "Acme"),
            (
                {
                    "id": "abc",
                    "first_name": "John",
                    "last_name": "Doe",
                    "forename": "James",
                    "surname": "Barlow",
                },
                "John Doe",  # first_name/last_name beats forename/surname
            ),
            # --- First-string fallback (#479): non-standard display fields ---
            ({"id": "abc-123", "component_name": "Reading Comprehension"}, "Reading Comprehension"),
            (
                {
                    "id": "abc",
                    "created_at": "2026-01-01T00:00:00Z",  # timestamps skipped
                    "question_text": "What is 2+2?",
                },
                "What is 2+2?",
            ),
            ({"id": "abc", "blob": "x" * 200}, "abc"),  # >=200 chars skipped
        ],
        ids=[
            "name_field",
            "company_name_field",
            "first_last_name",
            "first_name_only",
            "title_field",
            "email_field",
            "fallback_to_id",
            "empty_dict",
            "forename_surname",
            "forename_only",
            "display_field_override",
            "display_field_overrides_well_known",
            "display_field_empty_falls_through",
            "priority_name_over_company_name",
            "priority_company_name_over_title",
            "first_name_takes_priority_over_forename",
            "first_string_fallback",
            "first_string_skips_timestamps",
            "first_string_skips_long_values",
        ],
    )
    def test_dict_input(self, value, expected) -> None:
        assert _ref_display_name(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, ""),
            ("some-uuid", "some-uuid"),  # non-dict scalars pass through
        ],
        ids=["none", "scalar_string"],
    )
    def test_non_dict_input(self, value, expected) -> None:
        assert _ref_display_name(value) == expected

    def test_custom_fallback(self) -> None:
        """The `fallback` kwarg overrides the default empty string."""
        assert _ref_display_name(None, fallback="N/A") == "N/A"
