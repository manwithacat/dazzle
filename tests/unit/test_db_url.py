"""Tests for the shared DB-URL scheme normalisation helpers (#1185)."""

import pytest

from dazzle.core.db_url import add_psycopg_driver, normalise_postgres_scheme


class TestNormalisePostgresScheme:
    """``normalise_postgres_scheme`` rewrites Heroku's ``postgres://`` alias."""

    def test_postgres_scheme_rewritten(self) -> None:
        assert (
            normalise_postgres_scheme("postgres://user:pass@host:5432/db")
            == "postgresql://user:pass@host:5432/db"
        )

    def test_only_leading_prefix_touched(self) -> None:
        # A 'postgres://' substring later in the URL is left alone.
        assert (
            normalise_postgres_scheme("postgresql://h/db?note=postgres://x")
            == "postgresql://h/db?note=postgres://x"
        )

    def test_already_postgresql_unchanged(self) -> None:
        url = "postgresql://user:pass@host/db"
        assert normalise_postgres_scheme(url) == url

    def test_idempotent(self) -> None:
        once = normalise_postgres_scheme("postgres://user@host/db")
        assert normalise_postgres_scheme(once) == once

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql+psycopg://user@host/db",
            "sqlite:///tmp/test.db",
            "mysql://user@host/db",
            "",
        ],
    )
    def test_non_postgres_passes_through(self, url: str) -> None:
        assert normalise_postgres_scheme(url) == url


class TestAddPsycopgDriver:
    """``add_psycopg_driver`` pins a bare ``postgresql://`` to psycopg v3."""

    def test_bare_postgresql_gets_driver(self) -> None:
        assert (
            add_psycopg_driver("postgresql://user:pass@host/db")
            == "postgresql+psycopg://user:pass@host/db"
        )

    def test_already_psycopg_unchanged(self) -> None:
        url = "postgresql+psycopg://user@host/db"
        assert add_psycopg_driver(url) == url

    def test_other_driver_unchanged(self) -> None:
        # An explicit non-psycopg driver must not be double-rewritten.
        url = "postgresql+asyncpg://user@host/db"
        assert add_psycopg_driver(url) == url

    def test_idempotent(self) -> None:
        once = add_psycopg_driver("postgresql://user@host/db")
        assert add_psycopg_driver(once) == once

    @pytest.mark.parametrize(
        "url",
        [
            "postgres://user@host/db",  # not normalised yet — left alone
            "sqlite:///tmp/test.db",
            "",
        ],
    )
    def test_non_bare_postgresql_passes_through(self, url: str) -> None:
        assert add_psycopg_driver(url) == url


def test_combined_pipeline() -> None:
    """The common ``normalise`` then ``add_driver`` chain matches expectations."""
    result = add_psycopg_driver(normalise_postgres_scheme("postgres://user@host/db"))
    assert result == "postgresql+psycopg://user@host/db"
