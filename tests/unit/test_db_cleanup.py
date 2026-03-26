"""Tests for dazzle.db.cleanup — orphan record removal."""

from unittest.mock import AsyncMock

import pytest

from dazzle.db.cleanup import db_cleanup_impl


class TestDbCleanupImpl:
    @pytest.mark.asyncio
    async def test_no_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 0

    @pytest.mark.asyncio
    async def test_deletes_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        # First iteration: 3 orphans found, then deleted
        # Second iteration: 0 orphans (done)
        conn.fetchval = AsyncMock(side_effect=[3, 0])
        conn.execute = AsyncMock(return_value="DELETE 3")

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 3
        assert result["iterations"] >= 1

    @pytest.mark.asyncio
    async def test_dry_run(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_cleanup_impl(entities=[school, student], conn=conn, dry_run=True)
        assert result["dry_run"] is True
        assert result["would_delete"] == 5
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self, make_entity) -> None:
        """Stops after MAX_ITERATIONS even if orphans remain."""
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        # Always returns orphans — should stop at cap
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock(return_value="DELETE 1")

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["iterations"] <= 10

    @pytest.mark.asyncio
    async def test_no_checks_returns_zero(self, make_entity) -> None:
        """Entities with no refs should return 0 deleted, 0 iterations."""
        config = make_entity("Config")
        conn = AsyncMock()

        result = await db_cleanup_impl(entities=[config], conn=conn)
        assert result["total_deleted"] == 0
        assert result["iterations"] == 0
