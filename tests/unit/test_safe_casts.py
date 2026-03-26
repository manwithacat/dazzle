"""Tests for the safe cast registry."""

from dazzle_back.runtime.safe_casts import get_using_clause, is_safe_cast


class TestSafeCastRegistry:
    def test_text_to_uuid_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "UUID")

    def test_text_to_timestamptz_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "TIMESTAMPTZ")

    def test_text_to_date_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "DATE")

    def test_text_to_jsonb_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "JSONB")

    def test_text_to_boolean_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "BOOLEAN")

    def test_text_to_integer_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "INTEGER")

    def test_double_to_numeric_is_safe(self) -> None:
        assert is_safe_cast("DOUBLE PRECISION", "NUMERIC")

    def test_uuid_to_text_is_not_safe(self) -> None:
        assert not is_safe_cast("UUID", "TEXT")

    def test_integer_to_boolean_is_not_safe(self) -> None:
        assert not is_safe_cast("INTEGER", "BOOLEAN")

    def test_case_insensitive(self) -> None:
        assert is_safe_cast("text", "uuid")


class TestGetUsingClause:
    def test_text_to_uuid_clause(self) -> None:
        clause = get_using_clause("TEXT", "UUID", "my_col")
        assert clause == '"my_col"::uuid'

    def test_text_to_timestamptz_clause(self) -> None:
        clause = get_using_clause("TEXT", "TIMESTAMPTZ", "created_at")
        assert clause == '"created_at"::timestamptz'

    def test_double_to_numeric_has_no_clause(self) -> None:
        clause = get_using_clause("DOUBLE PRECISION", "NUMERIC", "amount")
        assert clause is None

    def test_unknown_cast_returns_none(self) -> None:
        clause = get_using_clause("UUID", "TEXT", "id")
        assert clause is None
