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

    @pytest.mark.asyncio
    async def test_skips_virtual_entities(self, make_entity) -> None:
        """Virtual entities (#814) have no Postgres table — must not be truncated.

        Before the fix, db_reset_impl tried to ``TRUNCATE TABLE "SystemHealth"``
        and similar, causing every reset to log "relation does not exist" for
        each virtual entity and making ``dazzle qa trial --fresh-db`` look
        broken.
        """
        real = make_entity("Task")
        system_health = make_entity("SystemHealth")
        system_metric = make_entity("SystemMetric")

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_reset_impl(entities=[real, system_health, system_metric], conn=conn)
        # Only the real entity should be truncated; virtual ones skipped.
        assert result["truncated"] == 1
        truncate_calls = [c for c in conn.execute.call_args_list if "TRUNCATE" in str(c)]
        assert len(truncate_calls) == 1
        assert "Task" in str(truncate_calls[0])
        assert "SystemHealth" not in str(truncate_calls[0])
