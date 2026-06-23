"""Three-way parity gate (Task 4, framework-migration-baseline, ADR-0044).

Asserts that the three canonical sources of the framework schema are identical
over the in-scope tables::

    (a) alembic upgrade head   ≡
    (b) ensure_framework_schema ≡
    (c) FRAMEWORK_SCHEMA_SNAPSHOT  (committed module)

The gate uses ``introspect_schema(engine, only=IN_SCOPE_TABLES)`` on two
disposable scratch Postgres databases — one built by alembic, one by the
orchestrator — and compares both against the committed snapshot dict.

On any mismatch the test FAILS with a human-readable diff built via
``dazzle.db.schema_diff.diff``, showing exactly which table/column/index
differs across the three paths.

Skip condition: ``TEST_DATABASE_URL`` or ``DATABASE_URL`` must be set.
CI marker: ``postgres`` (matches the existing PG suite gate in pyproject.toml).

Adversarial review checklist (Task 4):
  ✓ Gate compares ALL 30 in-scope tables (not a subset).
  ✓ Readable-diff path is exercised (test_readable_diff_on_mismatch).
  ✓ Excluded tables are not falsely flagged (only= filter).
  ✓ Scratch DBs are self-cleaning (finally blocks with pg_terminate_backend).
  ✓ Runs under the CI postgres marker.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

# ---------------------------------------------------------------------------
# In-scope table set — must stay in sync with framework_schema_snapshot.py
# and the global-constraints list in the migration-baseline plan.
# ---------------------------------------------------------------------------

IN_SCOPE_TABLES: frozenset[str] = frozenset(
    {
        "_dazzle_params",
        # auth
        "users",
        "sessions",
        "memberships",
        "organizations",
        "membership_events",
        "invitations",
        "connections",
        "connection_secret_events",
        "scim_groups",
        "scim_group_members",
        "saml_consumed_assertions",
        "password_reset_tokens",
        "magic_links",
        "email_verification_tokens",
        "user_preferences",
        "join_requests",
        # process
        "process_runs",
        "process_tasks",
        # audit / misc
        "_dazzle_audit_log",
        "_dazzle_atomic_audit",
        "dazzle_files",
        "refresh_tokens",
        "devices",
        "_grants",
        "_grant_events",
        "_dazzle_otp_codes",
        "_dazzle_recovery_codes",
        "_dazzle_event_inbox",
        "_dazzle_event_outbox",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_if_no_pg() -> None:
    if not _PG_URL:
        pytest.skip("TEST_DATABASE_URL / DATABASE_URL not set — skipping PG parity gate")


def _admin_url() -> str:
    """Normalise to a plain psycopg URL (no +psycopg dialect prefix)."""
    url = _PG_URL or ""
    return url.replace("postgresql+psycopg://", "postgresql://")


def _sa_url(plain_url: str) -> str:
    """Convert plain postgres:// URL to postgresql+psycopg:// for SQLAlchemy."""
    if plain_url.startswith("postgresql://"):
        return plain_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return plain_url


@pytest.fixture()
def scratch_url_alembic() -> Generator[str, None, None]:
    """Disposable scratch DB for the alembic-head path."""
    _skip_if_no_pg()
    admin = _admin_url()
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_parity_alembic_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


@pytest.fixture()
def scratch_url_orchestrator() -> Generator[str, None, None]:
    """Disposable scratch DB for the ensure_framework_schema path."""
    _skip_if_no_pg()
    admin = _admin_url()
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_parity_orch_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


def _alembic_head(plain_url: str) -> None:
    """Run ``alembic upgrade head`` (framework versions only) on *plain_url*."""
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", str(fw / "versions"))  # framework only
    cfg.set_main_option("sqlalchemy.url", _sa_url(plain_url))
    command.upgrade(cfg, "head")


def _ensure_orch(plain_url: str) -> None:
    """Run ``ensure_framework_schema`` on *plain_url*."""
    from dazzle.http.runtime.framework_schema import ensure_framework_schema

    with psycopg.connect(plain_url) as conn:
        conn.autocommit = False
        ensure_framework_schema(conn)


def _introspect(plain_url: str) -> dict[str, Any]:
    """Introspect the in-scope framework tables from *plain_url*."""
    from dazzle.db.schema_snapshot import introspect_schema

    eng = sa.create_engine(_sa_url(plain_url))
    try:
        return introspect_schema(eng, only=set(IN_SCOPE_TABLES))
    finally:
        eng.dispose()


def _format_diff(
    snap_a: dict[str, Any],
    snap_b: dict[str, Any],
    label_a: str,
    label_b: str,
) -> str:
    """Return a human-readable diff string using schema_diff.diff.

    Lists every SchemaOp that transforms *snap_a* into *snap_b*.  An empty
    list means the snapshots are equal.  Each op is rendered on its own line
    with a short prefix indicating direction::

        (+) AddTable(table='foo')
        (-) DropColumn(table='bar', name='x', ...)
        (~) AlterColumn(table='baz', name='y', ...)
    """
    from dazzle.db.schema_diff import (
        AddColumn,
        AddForeignKey,
        AddIndex,
        AddTable,
        AddUnique,
        AlterColumn,
        DropColumn,
        DropForeignKey,
        DropIndex,
        DropTable,
        DropUnique,
        RenameColumn,
        RenameTable,
        diff,
    )

    ops = diff(snap_a, snap_b)
    if not ops:
        return f"[no diff] {label_a} == {label_b}"

    lines = [f"DIFF: {label_a}  →  {label_b}  ({len(ops)} operations):"]
    for op in ops:
        if isinstance(op, (AddTable, AddColumn, AddForeignKey, AddIndex, AddUnique)):
            lines.append(f"  (+) {op!r}")
        elif isinstance(op, (DropTable, DropColumn, DropForeignKey, DropIndex, DropUnique)):
            lines.append(f"  (-) {op!r}")
        elif isinstance(op, (RenameTable, RenameColumn)):
            lines.append(f"  (>) {op!r}")
        elif isinstance(op, AlterColumn):
            lines.append(f"  (~) {op!r}")
        else:
            lines.append(f"  (?) {op!r}")
    return "\n".join(lines)


def _format_index_diff(
    snap_a: dict[str, Any],
    snap_b: dict[str, Any],
    label_a: str,
    label_b: str,
) -> str:
    """Return a human-readable index-level diff between two rich snapshots.

    The rich index format is ``{name: {unique, columns, predicate}}``.  The
    schema_diff module uses the old lossy list format so cannot render these
    differences; this helper fills that gap and is included in every mismatch
    failure message alongside the schema_diff output.
    """
    lines: list[str] = []
    all_tables = sorted(set(snap_a) | set(snap_b))
    for tname in all_tables:
        idxs_a: dict[str, Any] = (snap_a.get(tname) or {}).get("indexes") or {}
        idxs_b: dict[str, Any] = (snap_b.get(tname) or {}).get("indexes") or {}
        if not isinstance(idxs_a, dict) or not isinstance(idxs_b, dict):
            # Fallback: old list format — skip rich comparison for this table.
            continue
        names_a = set(idxs_a)
        names_b = set(idxs_b)
        for name in sorted(names_a - names_b):
            lines.append(f"  (-) index dropped in {label_b}: {tname}.{name} = {idxs_a[name]!r}")
        for name in sorted(names_b - names_a):
            lines.append(f"  (+) index added in {label_b}:   {tname}.{name} = {idxs_b[name]!r}")
        for name in sorted(names_a & names_b):
            if idxs_a[name] != idxs_b[name]:
                lines.append(
                    f"  (~) index changed: {tname}.{name}\n"
                    f"      {label_a}: {idxs_a[name]!r}\n"
                    f"      {label_b}: {idxs_b[name]!r}"
                )
    if not lines:
        return "[no index diff]"
    return f"INDEX DIFF ({label_a} → {label_b}):\n" + "\n".join(lines)


def _assert_equal(
    snap_a: dict[str, Any],
    snap_b: dict[str, Any],
    label_a: str,
    label_b: str,
) -> None:
    """Assert *snap_a == snap_b* over the in-scope tables, with a readable diff on failure."""
    # First check the table key sets.
    tables_a = set(snap_a.keys())
    tables_b = set(snap_b.keys())
    if tables_a != tables_b:
        only_a = sorted(tables_a - tables_b)
        only_b = sorted(tables_b - tables_a)
        msg = (
            f"Table-set mismatch between {label_a} and {label_b}:\n"
            f"  Only in {label_a}: {only_a}\n"
            f"  Only in {label_b}: {only_b}\n"
        )
        pytest.fail(msg)

    # Then do a full structural diff.
    if snap_a != snap_b:
        diff_text = _format_diff(snap_a, snap_b, label_a, label_b)
        # Also emit a rich index-level diff since schema_diff uses the old
        # lossy list format and cannot name dropped/changed indexes.
        idx_diff_text = _format_index_diff(snap_a, snap_b, label_a, label_b)
        pytest.fail(
            f"Schema mismatch between {label_a} and {label_b}.\n\n"
            f"{diff_text}\n\n"
            f"{idx_diff_text}\n\n"
            "Fix: ensure_framework_schema and the alembic baseline must produce "
            "identical DDL; regenerate FRAMEWORK_SCHEMA_SNAPSHOT if the DDL is correct."
        )


# ---------------------------------------------------------------------------
# Main parity test — all three paths must agree
# ---------------------------------------------------------------------------


class TestFrameworkBaselineParityPG:
    """Three-way parity: alembic-head ≡ orchestrator ≡ committed snapshot."""

    def test_three_way_parity(
        self,
        scratch_url_alembic: str,
        scratch_url_orchestrator: str,
    ) -> None:
        """Core gate: all three schema sources agree on all 30 in-scope tables.

        (a) alembic upgrade head on a fresh DB
        (b) ensure_framework_schema on a fresh DB
        (c) FRAMEWORK_SCHEMA_SNAPSHOT (committed module)

        A single mismatch is a FAIL with a readable diff.
        """
        # Build path (a): alembic head
        _alembic_head(scratch_url_alembic)
        snap_alembic = _introspect(scratch_url_alembic)

        # Build path (b): orchestrator
        _ensure_orch(scratch_url_orchestrator)
        snap_orch = _introspect(scratch_url_orchestrator)

        # Load path (c): committed snapshot
        from dazzle.http.runtime.framework_schema_snapshot import (
            FRAMEWORK_SCHEMA_SNAPSHOT,
        )
        from dazzle.http.runtime.framework_schema_snapshot import (
            IN_SCOPE_TABLES as SNAP_IN_SCOPE,
        )

        snap_committed: dict[str, Any] = FRAMEWORK_SCHEMA_SNAPSHOT

        # Sanity: the committed snapshot must cover all 30 in-scope tables.
        assert set(snap_committed.keys()) == IN_SCOPE_TABLES, (
            f"FRAMEWORK_SCHEMA_SNAPSHOT key set does not match IN_SCOPE_TABLES.\n"
            f"  Missing from snapshot: {sorted(IN_SCOPE_TABLES - set(snap_committed.keys()))}\n"
            f"  Extra in snapshot:     {sorted(set(snap_committed.keys()) - IN_SCOPE_TABLES)}\n"
        )
        # Also verify the snapshot module's own IN_SCOPE_TABLES matches ours.
        assert SNAP_IN_SCOPE == IN_SCOPE_TABLES, (
            "framework_schema_snapshot.IN_SCOPE_TABLES diverged from the test's IN_SCOPE_TABLES"
        )

        # (a) ≡ (b)
        _assert_equal(snap_alembic, snap_orch, "alembic-head", "orchestrator")

        # (a) ≡ (c)
        _assert_equal(snap_alembic, snap_committed, "alembic-head", "committed-snapshot")

        # (b) ≡ (c) — redundant given transitivity, but explicit for clarity
        _assert_equal(snap_orch, snap_committed, "orchestrator", "committed-snapshot")

    def test_all_in_scope_tables_covered(
        self,
        scratch_url_orchestrator: str,
    ) -> None:
        """Sanity: introspect_schema with only=IN_SCOPE_TABLES returns exactly 30 tables."""
        _ensure_orch(scratch_url_orchestrator)
        snap = _introspect(scratch_url_orchestrator)

        missing = sorted(IN_SCOPE_TABLES - set(snap.keys()))
        assert not missing, (
            f"ensure_framework_schema did not create these in-scope tables: {missing}"
        )
        assert len(snap) == len(IN_SCOPE_TABLES), (
            f"introspect_schema returned {len(snap)} tables, expected {len(IN_SCOPE_TABLES)}"
        )

    def test_excluded_tables_not_in_snapshot(
        self,
        scratch_url_orchestrator: str,
    ) -> None:
        """Excluded tables (ops-DB, event-bus prefixed, tenant) must not appear.

        We introspect WITHOUT the only= filter and verify the excluded table
        names are absent from the in-scope set.
        """
        from dazzle.db.schema_snapshot import introspect_schema

        _ensure_orch(scratch_url_orchestrator)
        eng = sa.create_engine(_sa_url(scratch_url_orchestrator))
        try:
            all_tables = set(introspect_schema(eng).keys())  # no filter
        finally:
            eng.dispose()

        # Verify the no-filter introspection ran without error (smoke check).
        assert len(all_tables) >= len(IN_SCOPE_TABLES), (
            "introspect_schema(no filter) returned fewer tables than the in-scope set"
        )

        # These must NOT be in IN_SCOPE_TABLES even if they exist in the DB.
        excluded_examples = {
            "tenants",  # tenant registry — excluded
            "api_requests",  # ops-DB — not created here anyway
            "health_checks",  # ops-DB — not created here anyway
        }
        for tbl in excluded_examples:
            assert tbl not in IN_SCOPE_TABLES, (
                f"Excluded table '{tbl}' found in IN_SCOPE_TABLES — "
                "it must not be included in the parity gate"
            )

    def test_no_unlisted_table_in_orchestrator(
        self,
        scratch_url_orchestrator: str,
    ) -> None:
        """No-unlisted-table guard: orchestrator must not create tables outside IN_SCOPE_TABLES.

        If ensure_framework_schema adds a new table without it being listed in
        IN_SCOPE_TABLES, that table would go unguarded by the parity gate.  This
        test catches exactly that case: it introspects without the only= filter
        and asserts the result set (minus alembic_version) equals IN_SCOPE_TABLES.

        A new framework table MUST be added to IN_SCOPE_TABLES and the committed
        FRAMEWORK_SCHEMA_SNAPSHOT before this test will pass again.
        """
        from dazzle.db.schema_snapshot import introspect_schema

        _ensure_orch(scratch_url_orchestrator)
        eng = sa.create_engine(_sa_url(scratch_url_orchestrator))
        try:
            all_snap = introspect_schema(eng)  # no filter
        finally:
            eng.dispose()

        all_table_names = set(all_snap.keys()) - {"alembic_version"}
        unlisted = sorted(all_table_names - IN_SCOPE_TABLES)
        assert not unlisted, (
            f"ensure_framework_schema created table(s) NOT listed in IN_SCOPE_TABLES:\n"
            f"  {unlisted}\n"
            "Add them to IN_SCOPE_TABLES in both the test and "
            "framework_schema_snapshot.py, then regenerate FRAMEWORK_SCHEMA_SNAPSHOT."
        )


# ---------------------------------------------------------------------------
# Readable-diff proof test — verifies the diff path produces useful output
# ---------------------------------------------------------------------------


class TestReadableDiffPath:
    """Verify that the readable-diff helper produces meaningful output on mismatch."""

    def test_readable_diff_on_column_mismatch(self) -> None:
        """_format_diff must describe a column-type change in readable form."""
        snap_a: dict[str, Any] = {
            "test_table": {
                "columns": {
                    "id": {"type": "text", "nullable": False, "default": None, "pk": True},
                    "name": {"type": "text", "nullable": True, "default": None, "pk": False},
                },
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        snap_b: dict[str, Any] = {
            "test_table": {
                "columns": {
                    "id": {"type": "text", "nullable": False, "default": None, "pk": True},
                    "name": {"type": "integer", "nullable": True, "default": None, "pk": False},
                },
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        diff_text = _format_diff(snap_a, snap_b, "A", "B")
        assert "DIFF" in diff_text, "Expected DIFF header in output"
        assert "AlterColumn" in diff_text, "Expected AlterColumn op in output"
        assert "name" in diff_text, "Expected column name in output"

    def test_readable_diff_on_missing_table(self) -> None:
        """_format_diff must report AddTable when a table is only in B."""
        snap_a: dict[str, Any] = {}
        snap_b: dict[str, Any] = {
            "new_table": {
                "columns": {"id": {"type": "text", "nullable": False, "default": None, "pk": True}},
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        diff_text = _format_diff(snap_a, snap_b, "A", "B")
        assert "AddTable" in diff_text
        assert "new_table" in diff_text

    def test_readable_diff_on_equal_snapshots(self) -> None:
        """_format_diff must report no diff when snapshots are equal."""
        snap: dict[str, Any] = {
            "t": {
                "columns": {"id": {"type": "text", "nullable": False, "default": None, "pk": True}},
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        diff_text = _format_diff(snap, snap, "A", "B")
        assert "no diff" in diff_text.lower(), (
            f"Expected '[no diff]' in output for equal snapshots, got: {diff_text!r}"
        )

    def test_assert_equal_raises_on_mismatch(self) -> None:
        """_assert_equal must call pytest.fail with readable text on mismatch."""
        snap_a: dict[str, Any] = {
            "t": {
                "columns": {"id": {"type": "text", "nullable": False, "default": None, "pk": True}},
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        snap_b: dict[str, Any] = {
            "t": {
                "columns": {
                    "id": {"type": "text", "nullable": False, "default": None, "pk": True},
                    "extra": {"type": "text", "nullable": True, "default": None, "pk": False},
                },
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        with pytest.raises(pytest.fail.Exception) as exc_info:
            _assert_equal(snap_a, snap_b, "A", "B")
        msg = str(exc_info.value)
        assert "AddColumn" in msg or "extra" in msg, (
            f"Expected readable column diff in failure message, got: {msg}"
        )
