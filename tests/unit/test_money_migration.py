"""
Tests for the legacy money-column drift detector (#840).

Pre-v0.58 stored money(CCY) as a single DOUBLE PRECISION column; v0.58+
splits into {name}_minor BIGINT + {name}_currency TEXT. The detector
walks the DSL's money fields and classifies each table against its
live-DB shape as clean / drift / partial.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.db.money_migration import (
    _build_repair_sql,
    _safe_ccy_literal,
    detect_money_drifts,
    repair_money_drifts,
)

from ._fake_pg import FakePgConn


def _money_conn(by_column: dict[str, dict[str, Any]]) -> FakePgConn:
    """conn whose ``_live_column_type`` probe maps the bound column -> a row.

    ``_live_column_type`` binds ``(table, column)`` to the two ``%s`` params and
    reads ``row["data_type"]``; a column absent from ``by_column`` reads as a
    non-existent column (no row).
    """

    def handler(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if not sql.lstrip().upper().startswith("SELECT"):
            return []  # repair DDL (ALTER/UPDATE) — recorded, no rows
        _table, column = params
        row = by_column.get(column)
        return [row] if row else []

    return FakePgConn(handler)


def _applied_ddl(conn: FakePgConn) -> list[tuple[str, tuple[Any, ...]]]:
    """Recorded statements that aren't reads — the applied repair DDL."""
    return [c for c in conn.executed if not c[0].lstrip().upper().startswith("SELECT")]


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
        conn = _money_conn(
            {
                "revenue_minor": {"data_type": "bigint"},
                "revenue_currency": {"data_type": "text"},
            }
        )
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert drifts == []

    @pytest.mark.asyncio()
    async def test_legacy_shape_reports_drift(self) -> None:
        conn = _money_conn({"revenue": {"data_type": "double precision"}})
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

        conn = _money_conn(
            {
                "revenue": {"data_type": "numeric"},
                "revenue_minor": {"data_type": "bigint"},
            }
        )
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert len(drifts) == 1
        assert drifts[0]["status"] == "partial"
        assert drifts[0]["repair_sql"] == ""

    @pytest.mark.asyncio()
    async def test_non_numeric_legacy_column_ignored(self) -> None:
        """If the column exists but isn't numeric, it's an unrelated column — skip."""

        conn = _money_conn({"revenue": {"data_type": "text"}})
        drifts = await detect_money_drifts(conn, [_money_entity("Company", "revenue")])
        assert drifts == []

    @pytest.mark.asyncio()
    async def test_non_money_entities_skipped(self) -> None:
        conn = _money_conn({})
        drifts = await detect_money_drifts(conn, [_non_money_entity("Article")])
        assert drifts == []
        # No queries emitted since the entity has no money fields.
        assert conn.executed == []


class TestRepairMoneyDriftsDryRun:
    @pytest.mark.asyncio()
    async def test_dry_run_returns_drifts_without_executing(self) -> None:
        conn = _money_conn({"revenue": {"data_type": "double precision"}})
        result = await repair_money_drifts(conn, [_money_entity("Company", "revenue")], apply=False)
        assert result["drift_count"] == 1
        assert result["applied_count"] == 0
        assert result["errors"] == []
        assert _applied_ddl(conn) == []

    @pytest.mark.asyncio()
    async def test_apply_runs_four_statements(self) -> None:
        conn = _money_conn({"revenue": {"data_type": "double precision"}})
        result = await repair_money_drifts(conn, [_money_entity("Company", "revenue")], apply=True)
        assert result["drift_count"] == 1
        assert result["applied_count"] == 4
        assert len(_applied_ddl(conn)) == 4
