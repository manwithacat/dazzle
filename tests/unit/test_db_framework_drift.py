"""`dazzle db verify`'s missing-framework-objects report (#1850) — DB-free half."""

from __future__ import annotations

import pytest

from dazzle.db.framework_drift import compare_framework_schema

pytestmark = pytest.mark.gate

_EXPECTED = {
    "dazzle_files": {
        "columns": {"id": {}, "uploaded_by": {}},
        "indexes": {"idx_files_entity": {}},
    },
    "_dazzle_usage_events": {"columns": {"id": {}}, "indexes": {}},
}


def test_reports_missing_tables_columns_and_indexes_only() -> None:
    drifts = compare_framework_schema(
        _EXPECTED,
        live_columns={"dazzle_files": {"id", "legacy_extra"}, "devices": {"id"}},
        live_indexes={"dazzle_files": set()},
    )
    assert drifts == [
        {"table": "_dazzle_usage_events", "missing_table": True, "columns": [], "indexes": []},
        {
            "table": "dazzle_files",
            "missing_table": False,
            "columns": ["uploaded_by"],
            "indexes": ["idx_files_entity"],
        },
    ]


def test_matching_schema_reports_nothing() -> None:
    assert (
        compare_framework_schema(
            _EXPECTED,
            live_columns={"dazzle_files": {"id", "uploaded_by"}, "_dazzle_usage_events": {"id"}},
            live_indexes={"dazzle_files": {"idx_files_entity", "dazzle_files_pkey"}},
        )
        == []
    )
