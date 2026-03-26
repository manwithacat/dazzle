"""Tests for dazzle.db.reset — truncate entity tables in dependency order."""

from unittest.mock import AsyncMock

import pytest

from dazzle.db.reset import db_reset_impl


class TestDbResetImpl:
    @pytest.mark.asyncio
    async def test_truncates_in_leaf_first_order(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=10)

        result = await db_reset_impl(entities=[school, student, exclusion], conn=conn)

        assert result["truncated"] == 3
        # Verify leaf-first ordering in calls
        calls = [c for c in conn.execute.call_args_list if "TRUNCATE" in str(c)]
        assert len(calls) == 3
        # Exclusion (leaf) should be truncated first
        assert "Exclusion" in str(calls[0])
        assert "School" in str(calls[2])

    @pytest.mark.asyncio
    async def test_preserves_auth_tables(self, make_entity) -> None:
        """Entity named 'Task' should still be truncated — only internal auth tables preserved."""
        task = make_entity("Task")
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_reset_impl(entities=[task], conn=conn)
        assert result["truncated"] == 1

    @pytest.mark.asyncio
    async def test_custom_preserve_list(self, make_entity) -> None:
        e1 = make_entity("Config")
        e2 = make_entity("Task")

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_reset_impl(entities=[e1, e2], conn=conn, preserve={"Config"})
        assert result["truncated"] == 1
        assert result["preserved"] == ["Config"]

    @pytest.mark.asyncio
    async def test_dry_run(self, make_entity) -> None:
        task = make_entity("Task")
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=42)

        result = await db_reset_impl(entities=[task], conn=conn, dry_run=True)
        assert result["dry_run"] is True
        assert result["would_truncate"] == 1
        conn.execute.assert_not_called()
