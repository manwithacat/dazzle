"""
Tests for the legacy money-column drift detector (#840).

Pre-v0.58 stored money(CCY) as a single DOUBLE PRECISION column; v0.58+
splits into {name}_minor BIGINT + {name}_currency TEXT. The detector
walks the DSL's money fields and classifies each table against its
live-DB shape as clean / drift / partial.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dazzle.db.money_migration import (
    _build_repair_sql,
    _safe_ccy_literal,
    detect_money_drifts,
    repair_money_drifts,
)


def _money_entity(name: str, field: str, currency: str = "GBP") -> SimpleNamespace:
    field_type = SimpleNamespace(kind="MONEY", currency_code=currency)
    field_obj = SimpleNamespace(name=field, type=field_type)
    return SimpleNamespace(name=name, fields=[field_obj])


def _non_money_entity(name: str) -> SimpleNamespace:
    field_type = SimpleNamespace(kind="STR", currency_code=None)
    field_obj = SimpleNamespace(name="title", type=field_type)
    return SimpleNamespace(name=name, fields=[field_obj])


class TestSafeCcyLiteral:
    def test_valid_three_letter_code(self) -> None:
        assert _safe_ccy_literal("GBP") == "'GBP'"
        assert _safe_ccy_literal("usd") == "'USD'"

    def test_bogus_code_falls_back_to_gbp(self) -> None:
        assert _safe_ccy_literal("' OR 1=1 --") == "'GBP'"
        assert _safe_ccy_literal("XX") == "'GBP'"  # wrong length
        assert _safe_ccy_literal("EUR1") == "'GBP'"  # too long

    def test_empty_falls_back(self) -> None:
        assert _safe_ccy_literal("") == "'GBP'"


class TestRepairSqlBuilder:
    def test_emits_four_statements_in_order(self) -> None:
        sql = _build_repair_sql("Company", "revenue", "GBP")
        statements = [s.strip() for s in sql.rstrip(";").split(";\n") if s.strip()]
        assert len(statements) == 4
        assert statements[0].startswith("ALTER TABLE") and "ADD COLUMN" in statements[0]
        assert "revenue_minor" in statements[0]
        assert "revenue_currency" in statements[1]
        assert statements[2].startswith("UPDATE")
        assert "'GBP'" in statements[2]
        assert statements[3].startswith("ALTER TABLE") and "DROP COLUMN" in statements[3]

    def test_quotes_identifiers(self) -> None:
        sql = _build_repair_sql("Company", "revenue", "GBP")
        assert '"Company"' in sql
        assert '"revenue"' in sql
        assert '"revenue_minor"' in sql


class TestDetectMoneyDrifts:
    @pytest.mark.asyncio()
    async def test_clean_db_reports_no_drift(self) -> None:
        # Live DB already has the new shape — no legacy column, has _minor/_currency.
        async def fetchrow(sql, table, column):
            if column == "revenue":
                return None
            if column == "revenue_minor":
                return {"data_type": "bigint"}
            if column == "revenue_currency":
                return {"data_type": "text"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert drifts == []

    @pytest.mark.asyncio()
    async def test_legacy_shape_reports_drift(self) -> None:
        async def fetchrow(sql, table, column):
            if column == "revenue":
                return {"data_type": "double precision"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue", "USD")])
        assert len(drifts) == 1
        assert drifts[0]["status"] == "drift"
        assert drifts[0]["entity"] == "Company"
        assert drifts[0]["field"] == "revenue"
        assert drifts[0]["currency"] == "USD"
        assert "ADD COLUMN" in drifts[0]["repair_sql"]
        assert "'USD'" in drifts[0]["repair_sql"]

    @pytest.mark.asyncio()
    async def test_partial_migration_flagged(self) -> None:
        """Legacy column + one of the new columns → partial, no repair SQL."""

        async def fetchrow(sql, table, column):
            if column == "revenue":
                return {"data_type": "numeric"}
            if column == "revenue_minor":
                return {"data_type": "bigint"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert len(drifts) == 1
        assert drifts[0]["status"] == "partial"
        assert drifts[0]["repair_sql"] == ""

    @pytest.mark.asyncio()
    async def test_non_numeric_legacy_column_ignored(self) -> None:
        """If the column exists but isn't numeric, it's an unrelated column — skip."""

        async def fetchrow(sql, table, column):
            if column == "revenue":
                return {"data_type": "text"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert drifts == []

    @pytest.mark.asyncio()
    async def test_non_money_entities_skipped(self) -> None:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        drifts = await detect_money_drifts(conn, [_non_money_entity("Article")])
        assert drifts == []
        # No queries emitted since the entity has no money fields.
        conn.fetchrow.assert_not_called()


class TestRepairMoneyDriftsDryRun:
    @pytest.mark.asyncio()
    async def test_dry_run_returns_drifts_without_executing(self) -> None:
        async def fetchrow(sql, table, column):
            if column == "revenue":
                return {"data_type": "double precision"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        conn.execute = AsyncMock()
        result = await repair_money_drifts(conn, [_money_entity("Company", "revenue")], apply=False)
        assert result["drift_count"] == 1
        assert result["applied_count"] == 0
        assert result["errors"] == []
        conn.execute.assert_not_called()

    @pytest.mark.asyncio()
    async def test_apply_runs_four_statements(self) -> None:
        async def fetchrow(sql, table, column):
            if column == "revenue":
                return {"data_type": "double precision"}
            return None

        conn = AsyncMock()
        conn.fetchrow = fetchrow
        conn.execute = AsyncMock()
        result = await repair_money_drifts(conn, [_money_entity("Company", "revenue")], apply=True)
        assert result["drift_count"] == 1
        assert result["applied_count"] == 4
        assert conn.execute.await_count == 4
