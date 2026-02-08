"""Tests for _INTEGRITY_ERRORS tuple in repository module."""

import sqlite3

from dazzle_back.runtime.repository import _INTEGRITY_ERRORS


class TestIntegrityErrors:
    """Verify _INTEGRITY_ERRORS contains the correct exception types."""

    def test_contains_sqlite_integrity_error(self) -> None:
        assert sqlite3.IntegrityError in _INTEGRITY_ERRORS

    def test_is_tuple(self) -> None:
        assert isinstance(_INTEGRITY_ERRORS, tuple)

    def test_psycopg2_included_if_available(self) -> None:
        try:
            import psycopg2

            assert psycopg2.IntegrityError in _INTEGRITY_ERRORS
        except ImportError:
            # psycopg2 not installed — only sqlite3 should be present
            assert len(_INTEGRITY_ERRORS) == 1

    def test_catches_sqlite_integrity_error(self) -> None:
        """Verify the tuple works in an except clause."""
        caught = False
        try:
            raise sqlite3.IntegrityError("UNIQUE constraint failed: Task.slug")
        except _INTEGRITY_ERRORS:
            caught = True
        assert caught
