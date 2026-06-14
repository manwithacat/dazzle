"""Tests for dazzle.db.cleanup — orphan record removal."""

import pytest

from dazzle.db.cleanup import db_cleanup_impl

from ._fake_pg import scalar_conn


class TestDbCleanupImpl:
    @pytest.mark.asyncio
    async def test_no_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = scalar_conn(0)

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 0

    @pytest.mark.asyncio
    async def test_deletes_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        # First iteration: 3 orphans found, then deleted.
        # Second iteration: 0 orphans (done). The DELETE between the two counts is
        # non-SELECT, so it doesn't consume a queued scalar.
        conn = scalar_conn([3, 0])

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 3
        assert result["iterations"] >= 1

    @pytest.mark.asyncio
    async def test_dry_run(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = scalar_conn(5)

        result = await db_cleanup_impl(entities=[school, student], conn=conn, dry_run=True)
        assert result["dry_run"] is True
        assert result["would_delete"] == 5
        assert conn.execute_calls("DELETE") == []

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self, make_entity) -> None:
        """Stops after MAX_ITERATIONS even if orphans remain."""
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        # Always returns orphans — should stop at cap
        conn = scalar_conn(1)

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["iterations"] <= 10

    @pytest.mark.asyncio
    async def test_no_checks_returns_zero(self, make_entity) -> None:
        """Entities with no refs should return 0 deleted, 0 iterations."""
        config = make_entity("Config")
        conn = scalar_conn(0)

        result = await db_cleanup_impl(entities=[config], conn=conn)
        assert result["total_deleted"] == 0
        assert result["iterations"] == 0


def test_build_delete_orphans_query_casts_to_text() -> None:
    """#1384: the DELETE query casts both FK comparison operands to text so a
    text FK vs uuid PK doesn't abort with 'operator does not exist: uuid = text'."""
    from dazzle.db.cleanup import _build_delete_orphans_query

    sql = _build_delete_orphans_query(
        child_table='"Exclusion"',
        fk_column='"student"',
        parent_table='"Student"',
        pk_column='"id"',
    )
    assert "::text = " in sql
    assert sql.count("::text") == 2
