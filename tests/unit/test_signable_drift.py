"""Signable schema-drift detection (#1340)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dazzle.core.linker import SIGNABLE_AUTO_FIELD_NAMES
from dazzle.db.signable_drift import detect_signable_drift, missing_signable_columns

from ._fake_pg import FakePgConn

pytestmark = pytest.mark.gate


def _FakeConn(tables: dict[str, set[str]]) -> FakePgConn:
    """psycopg3-shaped conn mapping table name -> live column set.

    ``_live_columns`` binds the table name as the single ``%s`` param.
    """

    def handler(_sql: str, params: tuple[str, ...]) -> list[dict[str, str]]:
        (table,) = params
        return [{"column_name": c} for c in tables.get(table, set())]

    return FakePgConn(handler)


class TestSignableColumnNames:
    def test_includes_the_three_columns_from_the_bug(self) -> None:
        # The columns #1340 reported as dropped must be in the canonical set.
        for col in ("signing_token_hash", "viewed_at", "expires_at"):
            assert col in SIGNABLE_AUTO_FIELD_NAMES


class TestMissingSignableColumns:
    def test_reports_missing_in_canonical_order(self) -> None:
        # A table frozen at a 7-column pre-signable shape (missing the 3).
        live = set(SIGNABLE_AUTO_FIELD_NAMES) - {
            "signing_token_hash",
            "viewed_at",
            "expires_at",
        }
        missing = missing_signable_columns(live)
        assert missing == [
            c
            for c in SIGNABLE_AUTO_FIELD_NAMES
            if c in {"signing_token_hash", "viewed_at", "expires_at"}
        ]
        # Order is the canonical injection order, not the set's.
        assert missing.index("viewed_at") < missing.index("expires_at")

    def test_no_missing_when_all_present(self) -> None:
        assert missing_signable_columns(set(SIGNABLE_AUTO_FIELD_NAMES)) == []


class TestDetectSignableDrift:
    def test_drift_reported_for_signable_entity_missing_columns(self) -> None:
        entity = SimpleNamespace(name="ParentConsent", signable=True)
        live = set(SIGNABLE_AUTO_FIELD_NAMES) - {"signing_token_hash", "viewed_at", "expires_at"}
        conn = _FakeConn({"ParentConsent": live})
        drifts = asyncio.run(detect_signable_drift(conn, [entity]))
        assert drifts == [
            {
                "entity": "ParentConsent",
                "missing": ["signing_token_hash", "viewed_at", "expires_at"],
            }
        ]

    def test_no_drift_when_table_complete(self) -> None:
        entity = SimpleNamespace(name="Contract", signable=True)
        conn = _FakeConn({"Contract": set(SIGNABLE_AUTO_FIELD_NAMES)})
        assert asyncio.run(detect_signable_drift(conn, [entity])) == []

    def test_non_signable_entity_skipped(self) -> None:
        entity = SimpleNamespace(name="Task", signable=False)
        conn = _FakeConn({"Task": set()})
        assert asyncio.run(detect_signable_drift(conn, [entity])) == []

    def test_absent_table_not_flagged_as_drift(self) -> None:
        # An unmigrated DB (table doesn't exist) is a different state, not drift.
        entity = SimpleNamespace(name="ParentConsent", signable=True)
        conn = _FakeConn({})  # no rows for any table
        assert asyncio.run(detect_signable_drift(conn, [entity])) == []
