"""End-to-end runtime-path test for the #1431 DSL-snapshot migration engine (Task 3.3).

This exercises the REAL runtime path — ``dazzle db revision`` (engine, default) and
``dazzle db upgrade`` — against a scratch Postgres database, not a unit stub. It proves:

1. The engine revision file carries a module-level ``SCHEMA_SNAPSHOT = <literal>``.
2. The forward migration of a *new* entity is a ``create_table`` for that table.
3. The revision contains NO destructive op (drop_table / drop_column) for the
   pre-existing, unrelated table — the engine emits intentful diff-derived ops only.
4. ``dazzle db upgrade`` applies the engine revision cleanly against the live DB.

It also verifies the engine is suppressed when the DSL hasn't changed (no-op revision),
and that ``--legacy-autogenerate`` still routes to the additive-guardrailed autogenerate
path (no ``SCHEMA_SNAPSHOT`` constant).

Scratch-DB lifecycle mirrors tests/integration/test_authstore_alembic_parity_pg.py.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

pytestmark = [pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_engine_{uuid.uuid4().hex[:8]}"
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


_BASE_DSL = """\
module scratch_app

app scratch_app "Scratch App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
"""

_DSL_WITH_NOTE = (
    _BASE_DSL
    + """
entity Note "Note":
  id: uuid pk
  body: str(500) required
"""
)


def _write_project(root: Path, dsl: str, db_url: str) -> None:
    """Write a minimal Dazzle project (dazzle.toml + one DSL file) at *root*."""
    (root / "dazzle.toml").write_text(
        f"""
[project]
name = "scratch_app"
title = "Scratch App"
version = "0.1.0"
root = "scratch_app"

[dsl]
entry = "dsl/app.dsl"

[database]
url = "{db_url}"
""",
        encoding="utf-8",
    )
    dsl_dir = root / "dsl"
    dsl_dir.mkdir(exist_ok=True)
    (dsl_dir / "app.dsl").write_text(dsl, encoding="utf-8")


def _versions_dir(root: Path) -> Path:
    return root / ".dazzle" / "migrations" / "versions"


def _project_revision_files(root: Path) -> list[Path]:
    """Project revision files, newest LAST (by mtime).

    Files are named ``<date>_<hex>_...`` — the hex suffix is random, so a plain
    name sort does not track creation order. Sort by mtime so ``[-1]`` is the
    most recently generated revision.
    """
    vdir = _versions_dir(root)
    if not vdir.exists():
        return []
    return sorted(
        (p for p in vdir.glob("*.py") if not p.name.startswith("__")),
        key=lambda p: p.stat().st_mtime,
    )


@pytest.fixture
def in_project(
    tmp_path: Path, scratch_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, str]]:
    """Create a scratch project + DB, chdir into it, set DATABASE_URL."""
    project = tmp_path / "scratch_proj"
    project.mkdir()
    psycopg_url = scratch_url.replace("postgresql://", "postgresql+psycopg://", 1)
    _write_project(project, _BASE_DSL, psycopg_url)
    monkeypatch.chdir(project)
    monkeypatch.setenv("DATABASE_URL", psycopg_url)
    # Ensure no stray env profile selection hijacks URL resolution.
    monkeypatch.delenv("DAZZLE_ENV", raising=False)

    # Stamp the scratch DB at the framework baseline head WITHOUT running the
    # framework chain. The framework alembic chain is not standalone — 0005+ ALTER
    # `sessions`, which only AuthStore._init_db creates (see
    # test_authstore_alembic_parity_pg). The engine create_table ops for the
    # project's own entities don't depend on those tables, so stamping is the
    # correct "baseline snapshot" starting state (the brief's step-1 stamp) and
    # satisfies alembic's "DB is up to date" precondition for autogenerate.
    from dazzle.cli.db import stamp_command

    stamp_command(revision="head")
    yield project, psycopg_url


def test_engine_revision_embeds_snapshot_and_is_additive(
    in_project: tuple[Path, str],
) -> None:
    """The headline runtime-path assertion (CRITICAL #1 in the task brief)."""
    from dazzle.cli.db import revision_command, upgrade_command

    project, _ = in_project

    # Entity table names are the verbatim DSL entity name (metadata_loader
    # convention) — "Task" / "Note", not lowercased.

    # 1. Baseline: engine revision for the initial DSL, then apply it.
    revision_command(message="baseline", autogenerate=True, legacy_autogenerate=False)
    upgrade_command(revision="head", no_rls=True)

    baseline_files = _project_revision_files(project)
    assert baseline_files, "baseline engine revision file was not written"
    baseline_text = baseline_files[-1].read_text(encoding="utf-8")
    assert "SCHEMA_SNAPSHOT" in baseline_text, "baseline must embed SCHEMA_SNAPSHOT"
    assert "create_table('Task'" in baseline_text, "baseline must create the Task table"

    # 2. Evolve the DSL — add an unrelated entity.
    (project / "dsl" / "app.dsl").write_text(_DSL_WITH_NOTE, encoding="utf-8")

    # 3. Engine revision for the delta.
    revision_command(message="add note", autogenerate=True, legacy_autogenerate=False)

    files = _project_revision_files(project)
    new_files = [p for p in files if p not in set(baseline_files)]
    assert len(new_files) == 1, "exactly one new engine revision must be written"
    delta_text = new_files[0].read_text(encoding="utf-8")

    # SCHEMA_SNAPSHOT is embedded as a module-level constant.
    assert "SCHEMA_SNAPSHOT" in delta_text
    # The new snapshot reflects the Note table (current full state).
    assert "'Note'" in delta_text

    # The forward migration creates ONLY the new table.
    assert "create_table('Note'" in delta_text, (
        f"expected create_table for Note; got:\n{delta_text}"
    )

    # No destructive op for the pre-existing, unrelated 'Task' table — the engine
    # diffs against the prior snapshot, so it never re-touches unchanged tables.
    assert "drop_table('Task'" not in delta_text
    assert "drop_column('Task'" not in delta_text
    assert "create_table('Task'" not in delta_text

    # 4. The engine revision applies cleanly against the live DB.
    upgrade_command(revision="head", no_rls=True)

    # Verify the Note table physically exists.
    psycopg_url = in_project[1]
    plain = psycopg_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(plain) as conn:
        row = conn.execute("SELECT to_regclass('public.\"Note\"')").fetchone()
    assert row is not None and row[0] is not None, "Note table must exist after upgrade"


def test_engine_revision_suppressed_when_dsl_unchanged(
    in_project: tuple[Path, str],
) -> None:
    """No-op: re-running the engine with an unchanged DSL writes no new file."""
    from dazzle.cli.db import revision_command, upgrade_command

    project, _ = in_project

    revision_command(message="baseline", autogenerate=True, legacy_autogenerate=False)
    upgrade_command(revision="head", no_rls=True)
    after_baseline = _project_revision_files(project)

    # Re-run with no DSL change — engine must suppress the empty revision.
    revision_command(message="noop", autogenerate=True, legacy_autogenerate=False)
    after_noop = _project_revision_files(project)

    assert after_noop == after_baseline, "engine must suppress a no-op revision"


def test_legacy_autogenerate_path_has_no_snapshot(
    in_project: tuple[Path, str],
) -> None:
    """--legacy-autogenerate routes to the autogenerate path (no SCHEMA_SNAPSHOT)."""
    from dazzle.cli.db import revision_command

    project, _ = in_project

    revision_command(message="legacy baseline", autogenerate=True, legacy_autogenerate=True)
    files = _project_revision_files(project)
    assert files, "legacy autogenerate must still write a revision"
    text = files[-1].read_text(encoding="utf-8")
    # The legacy path produces an autogenerate diff with NO snapshot constant.
    assert "SCHEMA_SNAPSHOT" not in text
    assert "create_table" in text


def test_unsafe_not_null_add_renders_data_seam(
    in_project: tuple[Path, str],
) -> None:
    """Task 5.1: adding a NOT NULL field with no default emits the expand/contract
    scaffold with a hand-author DATA MIGRATION seam in the generated upgrade()."""
    from dazzle.cli.db import revision_command, upgrade_command

    project, _ = in_project

    # Baseline: create the Task table.
    revision_command(message="baseline", autogenerate=True, legacy_autogenerate=False)
    upgrade_command(revision="head", no_rls=True)
    baseline_files = _project_revision_files(project)

    # Evolve: add a NOT NULL field with NO default (`required`, no `=`) → unsafe.
    unsafe_dsl = (
        _BASE_DSL + "  owner: str(120) required\n"  # appended under the Task entity block
    )
    (project / "dsl" / "app.dsl").write_text(unsafe_dsl, encoding="utf-8")

    revision_command(message="add owner not null", autogenerate=True, legacy_autogenerate=False)

    files = _project_revision_files(project)
    new_files = [p for p in files if p not in set(baseline_files)]
    assert len(new_files) == 1, "exactly one new revision expected"
    text = new_files[0].read_text(encoding="utf-8")

    # The raw seam marker must be fully expanded (never left in the file).
    assert "__DAZZLE_DATA_MIGRATION_SEAM__" not in text, "raw seam marker must be expanded"
    # The hand-author data-migration block is present.
    assert "# === DATA MIGRATION (hand-author) ===" in text, (
        f"expected DATA MIGRATION seam in unsafe revision; got:\n{text}"
    )
    assert "# === END DATA MIGRATION ===" in text
    # Expand/contract scaffold: add the column NULLABLE, then finalize NOT NULL.
    assert "add_column('Task'" in text
    assert "nullable=True" in text, "expand step adds the column NULLABLE"
    assert "nullable=False" in text, "contract step finalizes NOT NULL"

    # The scaffold applies cleanly against an EMPTY table (no rows to backfill),
    # proving the generated migration is runnable as-emitted.
    upgrade_command(revision="head", no_rls=True)


def test_engine_resolves_field_rename_not_drop_add(
    in_project: tuple[Path, str],
) -> None:
    """MERGE-SAFETY GATE (#1431 P3+4): a was: field rename is a RENAME, not drop+add.

    Proves end-to-end that when a DSL field is renamed with a ``was:`` hint the
    #1431 snapshot-diff engine emits an ``alter_column`` / ``new_column_name``
    rename op — NOT ``drop_column`` + ``add_column`` — and that ``dazzle db
    upgrade`` applies it cleanly, preserving existing row data under the new
    column name (data-survival proof).
    """
    import psycopg

    from dazzle.cli.db import revision_command, upgrade_command

    project, psycopg_url = in_project
    plain_url = psycopg_url.replace("postgresql+psycopg://", "postgresql://", 1)

    # -----------------------------------------------------------------------
    # 1. Baseline: project has Task with a `title` field.  Apply the baseline
    #    migration so the table exists in Postgres with the `title` column.
    # -----------------------------------------------------------------------
    revision_command(message="baseline", autogenerate=True, legacy_autogenerate=False)
    upgrade_command(revision="head", no_rls=True)

    baseline_files = _project_revision_files(project)
    assert baseline_files, "baseline revision file was not written"
    baseline_text = baseline_files[-1].read_text(encoding="utf-8")
    assert "create_table('Task'" in baseline_text, "baseline must create Task table"

    # -----------------------------------------------------------------------
    # 2. Insert a row so we can prove data survives the rename.
    # -----------------------------------------------------------------------
    with psycopg.connect(plain_url) as conn:
        conn.execute(
            "INSERT INTO \"Task\" (id, title, completed) VALUES (gen_random_uuid(), 'hello', false)"
        )
        conn.commit()

    # -----------------------------------------------------------------------
    # 3. Rewrite the DSL: rename `title` → `name` with the `was:` hint.
    #
    #    Syntax (from the parser — field modifiers then the was: clause):
    #      name: str(200) required was: title
    # -----------------------------------------------------------------------
    renamed_dsl = """\
module scratch_app

app scratch_app "Scratch App"

entity Task "Task":
  id: uuid pk
  name: str(200) required was: title
  completed: bool=false
"""
    (project / "dsl" / "app.dsl").write_text(renamed_dsl, encoding="utf-8")

    # -----------------------------------------------------------------------
    # 4. Generate the rename revision.
    # -----------------------------------------------------------------------
    revision_command(
        message="rename title to name",
        autogenerate=True,
        legacy_autogenerate=False,
    )

    files = _project_revision_files(project)
    rename_files = [p for p in files if p not in set(baseline_files)]
    assert len(rename_files) == 1, (
        f"exactly one new revision expected for the rename; got {len(rename_files)}"
    )
    rename_text = rename_files[0].read_text(encoding="utf-8")

    # -----------------------------------------------------------------------
    # 5. Assert the generated migration is a RENAME, not drop+add.
    #
    #    The engine renders RenameColumn as AlterColumnOp(modify_name=...) which
    #    Alembic writes to file as:
    #      op.alter_column('Task', 'title', ..., new_column_name='name')
    # -----------------------------------------------------------------------
    assert "new_column_name='name'" in rename_text, (
        f"expected a rename op (new_column_name='name') in the revision; got:\n{rename_text}"
    )
    # The migration must NOT use drop_column or add_column for the renamed field —
    # that would be data loss (the merge-safety failure this gate catches).
    assert "drop_column" not in rename_text, (
        "rename revision must not contain drop_column (data loss!)"
    )
    assert "add_column" not in rename_text, (
        "rename revision must not contain add_column (drop+add instead of rename = data loss!)"
    )
    assert "SCHEMA_SNAPSHOT" in rename_text, "rename revision must embed SCHEMA_SNAPSHOT"

    # -----------------------------------------------------------------------
    # 6. Apply the rename migration and verify data survival.
    # -----------------------------------------------------------------------
    upgrade_command(revision="head", no_rls=True)

    with psycopg.connect(plain_url) as conn:
        # Column `name` must exist; `title` must be gone.
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'Task' "
            "ORDER BY column_name"
        ).fetchall()
        col_names = {r[0] for r in cols}
        assert "name" in col_names, f"column 'name' must exist after upgrade; got: {col_names}"
        assert "title" not in col_names, (
            f"column 'title' must be gone after rename; got: {col_names}"
        )

        # The previously inserted row must survive with its data intact.
        row = conn.execute('SELECT name FROM "Task" LIMIT 1').fetchone()
        assert row is not None, "the pre-rename row must survive the upgrade"
        assert row[0] == "hello", f"row data must survive the rename intact; got name={row[0]!r}"
