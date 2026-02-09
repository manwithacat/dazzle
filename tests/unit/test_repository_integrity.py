"""Tests for _INTEGRITY_ERRORS tuple in repository module."""

from dazzle_back.runtime.repository import _INTEGRITY_ERRORS


class TestIntegrityErrors:
    """Verify _INTEGRITY_ERRORS contains the correct exception types."""

    def test_is_tuple(self) -> None:
        assert isinstance(_INTEGRITY_ERRORS, tuple)

    def test_psycopg_included_if_available(self) -> None:
        try:
            from psycopg import errors as _psycopg_errors

            assert _psycopg_errors.IntegrityError in _INTEGRITY_ERRORS
        except ImportError:
            # psycopg not installed — tuple should be empty
            assert len(_INTEGRITY_ERRORS) == 0

    def test_catches_psycopg_integrity_error(self) -> None:
        """Verify the tuple works in an except clause with psycopg errors."""
        try:
            from psycopg.errors import IntegrityError
        except ImportError:
            return  # psycopg not installed, skip

        caught = False
        try:
            raise IntegrityError("duplicate key value violates unique constraint")
        except _INTEGRITY_ERRORS:
            caught = True
        assert caught

    def test_does_not_contain_sqlite_integrity_error(self) -> None:
        """SQLite IntegrityError should NOT be in the tuple (PG-only runtime)."""
        import sqlite3

        assert sqlite3.IntegrityError not in _INTEGRITY_ERRORS
