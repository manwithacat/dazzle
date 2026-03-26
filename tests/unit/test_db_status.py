# tests/unit/test_db_status.py
"""Tests for dazzle.db.status — row counts and database size."""

from unittest.mock import AsyncMock

import pytest

from dazzle.db.status import db_status_impl


class TestDbStatusImpl:
    @pytest.mark.asyncio
    async def test_returns_entity_row_counts(self, make_entity) -> None:
        e1 = make_entity("User")
        e2 = make_entity("Task")
        entities = [e1, e2]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(
            side_effect=[
                12,  # User count
                150,  # Task count
                "2.1 MB",  # DB size
            ]
        )

        result = await db_status_impl(entities=entities, conn=conn)

        assert result["total_entities"] == 2
        assert result["total_rows"] == 162
        assert len(result["entities"]) == 2
        assert result["entities"][0]["name"] == "User"
        assert result["entities"][0]["rows"] == 12
        assert result["entities"][1]["name"] == "Task"
        assert result["entities"][1]["rows"] == 150
        assert result["database_size"] == "2.1 MB"

    @pytest.mark.asyncio
    async def test_handles_missing_table(self, make_entity) -> None:
        e1 = make_entity("Missing")
        conn = AsyncMock()
        conn.fetchval = AsyncMock(
            side_effect=[
                Exception("relation does not exist"),
                "1 MB",
            ]
        )

        result = await db_status_impl(entities=[e1], conn=conn)
        assert result["entities"][0]["rows"] == 0
        assert result["entities"][0]["error"] is not None
