"""Tests for dazzle.db.verify — FK integrity checking."""

from unittest.mock import AsyncMock

import pytest

from dazzle.db.verify import _build_orphan_query, db_verify_impl


class TestBuildOrphanQuery:
    def test_generates_valid_sql(self) -> None:
        sql = _build_orphan_query(
            child_table='"Exclusion"',
            fk_column='"student"',
            parent_table='"Student"',
            pk_column='"id"',
        )
        assert '"Exclusion"' in sql
        assert '"Student"' in sql
        assert '"student"' in sql
        assert "NOT EXISTS" in sql


class TestDbVerifyImpl:
    @pytest.mark.asyncio
    async def test_no_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        entities = [school, student]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await db_verify_impl(entities=entities, conn=conn)
        assert result["total_issues"] == 0
        assert len(result["checks"]) == 1
        assert result["checks"][0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_orphans_found(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        entities = [school, student]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=3)

        result = await db_verify_impl(entities=entities, conn=conn)
        assert result["total_issues"] == 3
        assert result["checks"][0]["status"] == "orphans"
        assert result["checks"][0]["orphan_count"] == 3

    @pytest.mark.asyncio
    async def test_missing_table_handled(self, make_entity) -> None:
        student = make_entity("Student", {"school": "School"})
        school = make_entity("School")

        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=Exception("relation does not exist"))

        result = await db_verify_impl(entities=[school, student], conn=conn)
        assert result["checks"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_warning_count_tallies_error_checks(self, make_entity) -> None:
        """#1035: column-mismatch / SQL errors emitted as `!` lines
        must increment warning_count so the CLI can exit non-zero
        instead of printing 'All FK references valid.'."""
        student = make_entity("Student", {"school": "School"})
        school = make_entity("School")

        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=Exception("column does not exist"))

        result = await db_verify_impl(entities=[school, student], conn=conn)
        assert result["warning_count"] == 1
        assert result["total_issues"] == 0  # no orphans, but warnings ≠ no issues

    @pytest.mark.asyncio
    async def test_warning_count_zero_on_clean_run(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await db_verify_impl(entities=[school, student], conn=conn)
        assert result["warning_count"] == 0

    @pytest.mark.asyncio
    async def test_warning_count_independent_of_orphan_count(self, make_entity) -> None:
        """A run can have BOTH orphans (counted as total_issues) and
        column-mismatch warnings (counted as warning_count) — both
        flag the verify command as failed."""
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        teacher = make_entity("Teacher", {"school": "School"})

        conn = AsyncMock()
        # School→student: 5 orphans. School→teacher: SQL error (column mismatch).
        conn.fetchval = AsyncMock(side_effect=[5, Exception("column 'school_id' does not exist")])

        result = await db_verify_impl(entities=[school, student, teacher], conn=conn)
        assert result["total_issues"] == 5
        assert result["warning_count"] == 1
