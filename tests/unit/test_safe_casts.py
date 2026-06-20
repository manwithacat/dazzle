"""Tests for the safe cast registry."""

import pytest

from dazzle.http.runtime.safe_casts import get_using_clause, is_safe_cast


class TestSafeCastRegistry:
    @pytest.mark.parametrize(
        ("from_type", "to_type", "expected"),
        [
            ("TEXT", "UUID", True),
            ("TEXT", "TIMESTAMPTZ", True),
            ("TEXT", "DATE", True),
            ("TEXT", "JSONB", True),
            ("TEXT", "BOOLEAN", True),
            ("TEXT", "INTEGER", True),
            ("DOUBLE PRECISION", "NUMERIC", True),
            ("UUID", "TEXT", False),
            ("INTEGER", "BOOLEAN", False),
            ("text", "uuid", True),  # case-insensitive
        ],
        ids=[
            "text_to_uuid",
            "text_to_timestamptz",
            "text_to_date",
            "text_to_jsonb",
            "text_to_boolean",
            "text_to_integer",
            "double_to_numeric",
            "uuid_to_text_unsafe",
            "integer_to_boolean_unsafe",
            "case_insensitive",
        ],
    )
    def test_is_safe_cast(self, from_type, to_type, expected) -> None:
        assert is_safe_cast(from_type, to_type) is expected


class TestGetUsingClause:
    @pytest.mark.parametrize(
        ("from_type", "to_type", "col_name", "expected"),
        [
            ("TEXT", "UUID", "my_col", '"my_col"::uuid'),
            ("TEXT", "TIMESTAMPTZ", "created_at", '"created_at"::timestamptz'),
            ("DOUBLE PRECISION", "NUMERIC", "amount", None),
            ("UUID", "TEXT", "id", None),  # unknown cast
        ],
        ids=[
            "text_to_uuid",
            "text_to_timestamptz",
            "double_to_numeric_no_clause",
            "unknown_cast_returns_none",
        ],
    )
    def test_using_clause(self, from_type, to_type, col_name, expected) -> None:
        assert get_using_clause(from_type, to_type, col_name) == expected
