"""Tests for the opt-in audit-log hash chain (#1197).

`audit_integrity = "none"` (default) MUST leave behaviour byte-identical to
the pre-#1197 code path — same schema, same INSERT shape, no row_hash
references, no extra SELECT-prev-hash query.

`audit_integrity = "hash_chain"` adds a `row_hash` column via ALTER TABLE
and threads sha256 hashes forward across writes. `verify_chain()` walks the
table and reports tamper as a structured ChainVerifyResult.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.http.runtime.audit_log import (
    _AUDIT_ROW_COLUMNS,
    AuditLogger,
    ChainVerifyResult,
    _canonical_payload,
    _compute_row_hash,
)

# =============================================================================
# Mock infrastructure — modelled after the patterns in test_audit_log.py.
# The mock cursor also tracks rows for both 17-column (no integrity) and
# 18-column (with row_hash) INSERTs and supports SELECT-prev-hash / SELECT *.
# =============================================================================


_NO_HASH_COLS: tuple[str, ...] = _AUDIT_ROW_COLUMNS
_WITH_HASH_COLS: tuple[str, ...] = _AUDIT_ROW_COLUMNS + ("row_hash",)


def _make_mock_cursor() -> MagicMock:
    cursor = MagicMock()
    cursor._rows: list[dict[str, Any]] = []  # type: ignore[attr-defined]
    cursor._executed: list[tuple[str, tuple | None]] = []  # type: ignore[attr-defined]
    cursor._last_select_result: list[dict[str, Any]] = []  # type: ignore[attr-defined]

    def _execute(sql: str, params: tuple | None = None) -> None:
        cursor._executed.append((sql, params))  # type: ignore[attr-defined]
        stripped = sql.strip()
        if stripped.startswith("INSERT"):
            assert params is not None
            cols = _WITH_HASH_COLS if len(params) == len(_WITH_HASH_COLS) else _NO_HASH_COLS
            cursor._rows.append(dict(zip(cols, params, strict=False)))  # type: ignore[attr-defined]
        elif "SELECT row_hash FROM _dazzle_audit_log" in stripped:
            if cursor._rows:  # type: ignore[attr-defined]
                # Sort by timestamp DESC, take the last (most-recent) hash
                ordered = sorted(
                    cursor._rows,  # type: ignore[attr-defined]
                    key=lambda r: r.get("timestamp") or "",
                    reverse=True,
                )
                cursor._last_select_result = [{"row_hash": ordered[0].get("row_hash")}]  # type: ignore[attr-defined]
            else:
                cursor._last_select_result = []  # type: ignore[attr-defined]
        elif stripped.startswith("SELECT * FROM _dazzle_audit_log"):
            # verify_chain walk — ascending order
            cursor._last_select_result = sorted(  # type: ignore[attr-defined]
                cursor._rows,  # type: ignore[attr-defined]
                key=lambda r: ((r.get("timestamp") or ""), r.get("id") or ""),
            )
        else:
            cursor._last_select_result = []  # type: ignore[attr-defined]

    def _fetchone() -> Any:
        if cursor._last_select_result:  # type: ignore[attr-defined]
            return cursor._last_select_result[0]  # type: ignore[attr-defined]
        return None

    def _fetchall() -> list[dict[str, Any]]:
        return list(cursor._last_select_result)  # type: ignore[attr-defined]

    cursor.execute = MagicMock(side_effect=_execute)
    cursor.fetchone = MagicMock(side_effect=_fetchone)
    cursor.fetchall = MagicMock(side_effect=_fetchall)
    return cursor


def _make_mock_connection(cursor: MagicMock | None = None) -> MagicMock:
    conn = MagicMock()
    if cursor is None:
        cursor = _make_mock_cursor()
    conn.cursor.return_value = cursor
    conn.commit = MagicMock()
    conn.close = MagicMock()
    return conn


@pytest.fixture
def mock_conn():
    cursor = _make_mock_cursor()
    conn = _make_mock_connection(cursor)
    with patch("psycopg.connect", return_value=conn), patch("psycopg.rows.dict_row", create=True):
        yield conn, cursor


# =============================================================================
# audit_integrity = "none" — default path must remain byte-identical
# =============================================================================


class TestIntegrityNone:
    def test_default_is_none(self, mock_conn) -> None:
        """The default constructor uses 'none' integrity."""
        logger = AuditLogger(database_url="postgresql://localhost/test")
        assert logger._audit_integrity == "none"

    def test_no_alter_table_when_none(self, mock_conn) -> None:
        """Default path must NOT touch the schema with ALTER TABLE."""
        conn, cursor = mock_conn
        AuditLogger(database_url="postgresql://localhost/test")
        executed_sqls = [c[0] for c in cursor._executed]
        assert not any("ALTER TABLE" in sql for sql in executed_sqls), (
            f"Default path issued ALTER TABLE: {[s for s in executed_sqls if 'ALTER' in s]}"
        )
        # The CREATE TABLE is unchanged too — no row_hash column reference.
        create_sqls = [s for s in executed_sqls if "CREATE TABLE" in s]
        assert create_sqls
        for sql in create_sqls:
            assert "row_hash" not in sql

    @pytest.mark.asyncio
    async def test_insert_shape_unchanged_when_none(self, mock_conn) -> None:
        """Default path INSERTs the original 17 columns — no row_hash."""
        conn, cursor = mock_conn
        logger = AuditLogger(database_url="postgresql://localhost/test")
        for i in range(3):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="permit read",
                policy_effect="permit",
            )
        await logger._flush()
        inserts = [c for c in cursor._executed if c[0].strip().startswith("INSERT")]
        assert len(inserts) == 3
        for _sql, params in inserts:
            assert params is not None
            assert len(params) == 17  # no row_hash
        # And no SELECT-prev-hash was issued either.
        select_prev = [
            c for c in cursor._executed if "SELECT row_hash FROM _dazzle_audit_log" in c[0]
        ]
        assert select_prev == []


# =============================================================================
# audit_integrity = "hash_chain" — schema + chain semantics
# =============================================================================


class TestIntegrityHashChain:
    def test_alter_table_adds_row_hash(self, mock_conn) -> None:
        """Enabling integrity issues ALTER TABLE ADD COLUMN IF NOT EXISTS row_hash."""
        conn, cursor = mock_conn
        AuditLogger(database_url="postgresql://localhost/test", audit_integrity="hash_chain")
        executed_sqls = [c[0] for c in cursor._executed]
        assert any(
            "ALTER TABLE _dazzle_audit_log" in sql and "row_hash" in sql for sql in executed_sqls
        )

    def test_invalid_integrity_value_rejected(self, mock_conn) -> None:
        """Anything other than 'none' or 'hash_chain' raises at construction."""
        with pytest.raises(ValueError, match="audit_integrity"):
            AuditLogger(database_url="postgresql://localhost/test", audit_integrity="bogus")

    @pytest.mark.asyncio
    async def test_every_row_has_hash_after_write(self, mock_conn) -> None:
        """After N entries flush, each persisted row has a non-empty row_hash."""
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        for i in range(4):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="permit",
                policy_effect="permit",
            )
        await logger._flush()
        assert len(cursor._rows) == 4
        for row in cursor._rows:
            assert "row_hash" in row
            assert isinstance(row["row_hash"], str)
            assert len(row["row_hash"]) == 64  # sha256 hexdigest

    @pytest.mark.asyncio
    async def test_advisory_lock_precedes_chain_head_read(self, mock_conn) -> None:
        """#1383: the hash-chain write takes a per-transaction advisory lock as
        its first statement — before the chain-head SELECT — so concurrent worker
        flushes serialise (head-read + INSERT as one critical section) and the
        chain stays linear instead of forking."""
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="t-0",
            decision="allow",
            matched_policy="permit",
            policy_effect="permit",
        )
        await logger._flush()
        sqls = [c[0] for c in cursor._executed]
        lock_idx = next((i for i, s in enumerate(sqls) if "pg_advisory_xact_lock" in s), None)
        seed_idx = next(
            (i for i, s in enumerate(sqls) if "SELECT row_hash FROM _dazzle_audit_log" in s), None
        )
        assert lock_idx is not None, "advisory lock not taken for hash_chain write"
        assert seed_idx is not None
        assert lock_idx < seed_idx, "advisory lock must precede the chain-head read"

    @pytest.mark.asyncio
    async def test_chain_seed_is_empty_string(self, mock_conn) -> None:
        """The very first row's prev_hash is the empty string seed."""
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        await logger.log_decision(
            operation="create",
            entity_name="Task",
            entity_id="t-0",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        await logger._flush()
        first_row = cursor._rows[0]
        # Recompute with seed=""
        expected = _compute_row_hash("", first_row)
        assert first_row["row_hash"] == expected

    @pytest.mark.asyncio
    async def test_chain_threads_forward(self, mock_conn) -> None:
        """Row N's prev_hash = row N-1's row_hash, all the way through."""
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        for i in range(5):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger._flush()
        rows = cursor._rows
        prev = ""
        for row in rows:
            expected = _compute_row_hash(prev, row)
            assert row["row_hash"] == expected
            prev = row["row_hash"]

    @pytest.mark.asyncio
    async def test_batch_does_not_re_query_prev_hash(self, mock_conn) -> None:
        """A batch flush queries prev-hash ONCE (the seed), not per-row."""
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        # Reset executed log to ignore init-time DDL.
        cursor._executed.clear()
        for i in range(4):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger._flush()
        prev_selects = [
            c for c in cursor._executed if "SELECT row_hash FROM _dazzle_audit_log" in c[0]
        ]
        # One SELECT per flush call (not per row) — here exactly one flush.
        assert len(prev_selects) == 1


# =============================================================================
# verify_chain — tamper detection and structured result
# =============================================================================


class TestVerifyChain:
    @pytest.mark.asyncio
    async def test_verify_clean_chain_returns_ok(self, mock_conn) -> None:
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        for i in range(3):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger._flush()
        result = logger.verify_chain()
        assert isinstance(result, ChainVerifyResult)
        assert result.ok is True
        assert result.first_mismatch_id is None
        assert result.mismatched_count == 0
        assert result.total_rows == 3
        assert result.skipped_legacy_rows == 0

    @pytest.mark.asyncio
    async def test_tampered_row_detected(self, mock_conn) -> None:
        """Mutating row 2's `operation` column makes verify_chain flag row 2.

        The mutation does NOT touch the timestamp (which is part of the
        canonical payload AND the ORDER-BY key), so row 1's hash remains
        valid and row 2's recomputed hash is the only mismatch.
        """
        conn, cursor = mock_conn
        logger = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        for i in range(3):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"t-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger._flush()

        # Order the in-memory rows by their (already-distinct, ISO 8601)
        # timestamps so we know which one is "row 2" in chain order.
        ordered = sorted(cursor._rows, key=lambda r: r["timestamp"])
        tampered_row = ordered[1]
        # Mutate ONE field that is in the canonical payload but is NOT
        # the timestamp / id (which would also break ordering).
        tampered_row["operation"] = "DELETED_FOR_COVER_UP"
        tampered_id = tampered_row["id"]

        result = logger.verify_chain()
        assert result.ok is False
        assert result.mismatched_count >= 1
        assert result.first_mismatch_id == str(tampered_id)

    def test_verify_chain_on_disabled_logger_is_noop(self, mock_conn) -> None:
        """verify_chain on a "none"-mode logger reports ok=True, total=0."""
        logger = AuditLogger(database_url="postgresql://localhost/test")
        result = logger.verify_chain()
        assert result.ok is True
        assert result.total_rows == 0
        assert result.first_mismatch_id is None
        assert result.mismatched_count == 0


# =============================================================================
# Switching from "none" → "hash_chain" — legacy rows have NULL row_hash
# =============================================================================


class TestNoneToHashChainSwitch:
    """When integrity is switched ON over an existing table, pre-existing
    rows have ``row_hash IS NULL``. We DOCUMENT and PIN the policy:
    legacy NULL rows are skipped during verification and treated as a
    valid seed boundary — the first post-switch chained row uses
    prev_hash="" (same as an empty-table seed). This means tampering
    with a legacy row is NOT detected (it has no hash to compare
    against) — only post-switch rows are tamper-evident.
    """

    @pytest.mark.asyncio
    async def test_alter_succeeds_legacy_rows_have_null_row_hash(self, mock_conn) -> None:
        # Phase 1: write 2 rows with integrity OFF.
        conn, cursor = mock_conn
        logger_none = AuditLogger(database_url="postgresql://localhost/test")
        for i in range(2):
            await logger_none.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"legacy-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger_none._flush()
        # Pre-existing rows have no row_hash key at all — emulate the DB
        # state where the ALTER hasn't fired yet.
        assert all("row_hash" not in r for r in cursor._rows)
        # Stamp timestamps so ordering is deterministic.
        for idx, row in enumerate(cursor._rows):
            row["timestamp"] = f"2026-01-01T00:00:0{idx}Z"

        # Phase 2: same mock DB, new logger with integrity ON. The
        # ALTER fires (no error), and the existing rows now logically
        # have row_hash = NULL (modelled by setting None explicitly).
        for row in cursor._rows:
            row.setdefault("row_hash", None)
        logger_chain = AuditLogger(
            database_url="postgresql://localhost/test", audit_integrity="hash_chain"
        )
        # ALTER ran without error.
        executed_sqls = [c[0] for c in cursor._executed]
        assert any("ALTER TABLE" in sql and "row_hash" in sql for sql in executed_sqls)

        # Phase 3: write 2 more rows with integrity ON.
        for i in range(2):
            await logger_chain.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"chain-{i}",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger_chain._flush()

        # The 2 legacy rows should still have row_hash=None; the 2 new
        # rows should each have a 64-char hex hash.
        legacy = [r for r in cursor._rows if r.get("entity_id", "").startswith("legacy-")]
        chained = [r for r in cursor._rows if r.get("entity_id", "").startswith("chain-")]
        assert len(legacy) == 2
        assert all(r["row_hash"] is None for r in legacy)
        assert len(chained) == 2
        assert all(isinstance(r["row_hash"], str) and len(r["row_hash"]) == 64 for r in chained)

        # verify_chain: legacy rows skipped (counted in skipped_legacy_rows),
        # chained rows verified ok, total = 4.
        result = logger_chain.verify_chain()
        assert result.ok is True
        assert result.total_rows == 4
        assert result.skipped_legacy_rows == 2
        assert result.mismatched_count == 0
        assert result.first_mismatch_id is None


# =============================================================================
# Canonical-payload determinism — sort_keys + default=str
# =============================================================================


class TestCanonicalPayload:
    def test_payload_is_deterministic(self) -> None:
        """Same content, different dict-insertion order → same canonical payload."""
        row_a = {c: f"v-{c}" for c in _AUDIT_ROW_COLUMNS}
        row_b = {c: f"v-{c}" for c in reversed(_AUDIT_ROW_COLUMNS)}
        assert _canonical_payload(row_a) == _canonical_payload(row_b)

    def test_payload_excludes_row_hash(self) -> None:
        """row_hash is NOT part of the canonical payload (would be circular)."""
        row = {c: f"v-{c}" for c in _AUDIT_ROW_COLUMNS}
        row["row_hash"] = "DOES_NOT_MATTER"
        payload = _canonical_payload(row)
        assert "row_hash" not in payload
        assert "DOES_NOT_MATTER" not in payload

    def test_hash_is_sha256_hexdigest(self) -> None:
        row = {c: f"v-{c}" for c in _AUDIT_ROW_COLUMNS}
        prev = "ab" * 32
        h = _compute_row_hash(prev, row)
        expected = hashlib.sha256((prev + _canonical_payload(row)).encode()).hexdigest()
        assert h == expected
        assert len(h) == 64

    def test_payload_json_compact_no_whitespace(self) -> None:
        row = {c: f"v-{c}" for c in _AUDIT_ROW_COLUMNS}
        payload = _canonical_payload(row)
        # Compact: no spaces after separators
        assert ", " not in payload
        assert ": " not in payload
        # Round-trips
        parsed = json.loads(payload)
        assert parsed["operation"] == "v-operation"
