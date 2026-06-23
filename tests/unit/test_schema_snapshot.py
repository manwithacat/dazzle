"""Unit tests for dazzle.db.schema_snapshot — pure MetaData introspection.

Tests build a hand-crafted MetaData; no CWD or DB access required.
"""

from typing import Any

import pytest
import sqlalchemy as sa

from dazzle.db.schema_snapshot import (
    _sa_type_to_token,
    project_schema,
    render_snapshot_literal,
    snapshot_from_module,
)

pytestmark = pytest.mark.migration_engine


def _meta() -> sa.MetaData:
    md = sa.MetaData()
    sa.Table(
        "Customer",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
    )
    sa.Table(
        "Invoice",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("customer", sa.Uuid(), sa.ForeignKey("Customer.id")),
    )
    return md


def test_project_schema_introspects_metadata() -> None:
    snap = project_schema(_meta())
    # Table names are the entity names VERBATIM (not pluralised/lowercased).
    assert set(snap) == {"Customer", "Invoice"}
    inv = snap["Invoice"]
    assert inv["columns"]["total"]["type"] == "integer"
    assert inv["columns"]["total"]["nullable"] is True
    assert inv["columns"]["id"]["pk"] is True
    # FK column is the field name VERBATIM; target is the referenced table name.
    assert inv["fks"]["customer"] == "Customer"


def test_project_schema_is_deterministic() -> None:
    assert project_schema(_meta()) == project_schema(_meta())  # sorted, stable


@pytest.mark.parametrize(
    "sa_type,expected",
    [
        (sa.Text(), "text"),
        (sa.Integer(), "integer"),
        (sa.BigInteger(), "bigint"),
        (sa.Boolean(), "boolean"),
        (sa.Float(), "float"),
        (sa.Numeric(), "numeric"),
        (sa.Numeric(10, 2), "numeric(10,2)"),
        (sa.Date(), "date"),
        (sa.DateTime(timezone=True), "timestamptz"),
        (sa.Uuid(), "uuid"),
        (sa.JSON(), "json"),
    ],
)
def test_sa_type_to_token(sa_type: sa.types.TypeEngine, expected: str) -> None:
    assert _sa_type_to_token(sa_type) == expected


def test_snapshot_literal_roundtrips() -> None:
    snap = project_schema(_meta())
    literal = render_snapshot_literal(snap)
    # The literal is valid Python that evaluates back to the same dict.
    assert eval(literal) == snap  # noqa: S307 — test-only, trusted input
    # Deterministic: same input → identical source.
    assert render_snapshot_literal(snap) == literal


def test_snapshot_from_module() -> None:
    # Create a mock module with SCHEMA_SNAPSHOT.
    import types

    mod = types.ModuleType("test_mod")
    snap = project_schema(_meta())
    mod.SCHEMA_SNAPSHOT = snap  # type: ignore[attr-defined]
    assert snapshot_from_module(mod) == snap

    # Module without SCHEMA_SNAPSHOT → empty dict.
    empty_mod = types.ModuleType("empty_mod")
    assert snapshot_from_module(empty_mod) == {}


# ---------------------------------------------------------------------------
# load_head_snapshot — TDD tests (Task 1.3)
# ---------------------------------------------------------------------------


def _make_versions_dir(
    tmp_path: pytest.TempPathFactory | pytest.FixtureRequest,
    *,
    revision: str = "abc001",
    include_snapshot: bool = True,
    snapshot_val: dict | None = None,
) -> "tuple[Any, Any]":
    """Helper: create a minimal alembic versions dir + ScriptDirectory.

    Returns ``(tmpdir_path, ScriptDirectory)`` so tests can inspect both.
    The file is written into ``<tmpdir>/versions/<revision>_init.py``.
    """
    import textwrap
    from pathlib import Path

    from alembic.script import ScriptDirectory

    tmpdir = Path(str(tmp_path))
    versions_dir = tmpdir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    if snapshot_val is None:
        snapshot_val = {
            "Widget": {
                "columns": {"id": {"type": "uuid", "nullable": False, "default": None, "pk": True}},
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }

    snap_line = f"SCHEMA_SNAPSHOT = {snapshot_val!r}" if include_snapshot else ""
    content = textwrap.dedent(f"""
        revision = {revision!r}
        down_revision = None
        branch_labels = None
        depends_on = None
        {snap_line}
        def upgrade(): pass
        def downgrade(): pass
    """).strip()

    (versions_dir / f"{revision}_init.py").write_text(content)
    sd = ScriptDirectory(str(tmpdir))
    return tmpdir, sd


def test_load_head_snapshot_returns_snapshot(tmp_path: pytest.TempPathFactory) -> None:
    """Head revision with SCHEMA_SNAPSHOT → load_head_snapshot returns it."""
    from dazzle.db.schema_snapshot import load_head_snapshot

    snap_val = {
        "Widget": {
            "columns": {"id": {"type": "uuid", "nullable": False, "default": None, "pk": True}},
            "fks": {},
            "uniques": [],
            "indexes": [],
        }
    }
    _, sd = _make_versions_dir(
        tmp_path, revision="snap001", include_snapshot=True, snapshot_val=snap_val
    )
    result = load_head_snapshot(sd)
    assert result == snap_val


def test_load_head_snapshot_no_constant_returns_empty(tmp_path: pytest.TempPathFactory) -> None:
    """Head revision without SCHEMA_SNAPSHOT → load_head_snapshot returns {}."""
    from dazzle.db.schema_snapshot import load_head_snapshot

    _, sd = _make_versions_dir(tmp_path, revision="nosnap001", include_snapshot=False)
    result = load_head_snapshot(sd)
    assert result == {}


def test_load_head_snapshot_no_head_returns_empty(tmp_path: pytest.TempPathFactory) -> None:
    """Empty versions dir (no revisions) → load_head_snapshot returns {}."""
    from pathlib import Path

    from alembic.script import ScriptDirectory

    from dazzle.db.schema_snapshot import load_head_snapshot

    tmpdir = Path(str(tmp_path))
    versions_dir = tmpdir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    sd = ScriptDirectory(str(tmpdir))
    result = load_head_snapshot(sd)
    assert result == {}


def test_load_head_snapshot_multi_head_picks_snapshot_bearer(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Multi-head (dual-lineage): picks the head whose module has SCHEMA_SNAPSHOT."""
    import textwrap
    from pathlib import Path

    from alembic.script import ScriptDirectory

    from dazzle.db.schema_snapshot import load_head_snapshot

    tmpdir = Path(str(tmp_path))
    versions_dir = tmpdir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    snap_val = {"Order": {"columns": {}, "fks": {}, "uniques": [], "indexes": []}}

    # Framework-lineage head: no SCHEMA_SNAPSHOT
    (versions_dir / "fw001_baseline.py").write_text(
        textwrap.dedent("""
            revision = 'fw001'
            down_revision = None
            branch_labels = None
            depends_on = None
            def upgrade(): pass
            def downgrade(): pass
        """).strip()
    )

    # Project-lineage head: has SCHEMA_SNAPSHOT
    (versions_dir / "proj001_init.py").write_text(
        textwrap.dedent(f"""
            revision = 'proj001'
            down_revision = None
            branch_labels = None
            depends_on = None
            SCHEMA_SNAPSHOT = {snap_val!r}
            def upgrade(): pass
            def downgrade(): pass
        """).strip()
    )

    sd = ScriptDirectory(str(tmpdir))
    heads = sd.get_heads()
    assert len(heads) == 2, f"Expected 2 heads, got {heads}"

    result = load_head_snapshot(sd)
    assert result == snap_val
