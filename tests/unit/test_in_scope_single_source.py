"""The in-scope framework table set has ONE source: the artifact registry.

framework_schema_snapshot.IN_SCOPE_TABLES and the parity test derive from it
(#1495 follow-on, ADR-0047) — collapsing the previously triplicated list.
"""

from __future__ import annotations

from dazzle.db.artifact_registry import in_baseline_tables
from dazzle.http.runtime.framework_schema_snapshot import IN_SCOPE_TABLES


def test_snapshot_in_scope_is_registry_derived() -> None:
    assert IN_SCOPE_TABLES == in_baseline_tables()
    assert set(IN_SCOPE_TABLES) == set(in_baseline_tables())
