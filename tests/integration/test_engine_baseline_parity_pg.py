"""Engine-baseline correctness oracle: ``db baseline`` ≡ ``create_all`` (#1431/#1460).

The migration engine's unit tests assert on Alembic *op-trees*. That is blind to a
whole class of bug: a structurally-valid op-tree that produces the *wrong schema*
(the #1460 silent-FK-drop and the latent new-table-FK drop were both exactly this).

This gate closes that gap with a property oracle: SQLAlchemy's ``create_all`` is a
trusted reference implementation of "DSL metadata → schema", so for any project,

    db baseline + upgrade   (introspected on real PG)
        ≡
    create_all(metadata)    (introspected on real PG)

restricted to the project's own tables (framework-owned tables are created by the
framework baseline / ``ensure_framework_schema``, not the project baseline, so they
are excluded from both sides before comparing).

The comparison is **name-insensitive** — ``create_all`` (sa_schema naming) and the
engine (schema_render naming) legitimately name constraints/indexes differently, so
we compare FKs by ``column → referenced_table``, indexes by *shape*
(columns + uniqueness + predicate), and columns by ``type/nullable/pk/default``.

Run the whole engine regression path with ``pytest -m migration_engine``.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.postgres, pytest.mark.migration_engine]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


# ---------------------------------------------------------------------------
# DSL corpus — inline projects that exercise the FK bug classes directly, plus
# a sweep of real example apps (broad, free coverage that grows with examples).
# ---------------------------------------------------------------------------

_DSL_CYCLIC = """\
module app

app repro "Repro":
  security_profile: standard

entity Org "Org":
  id: uuid pk
  name: str(80) required
  owner: ref Person optional

entity Person "Person":
  id: uuid pk
  full_name: str(80) required
  org: ref Org optional

entity Node "Node":
  id: uuid pk
  label: str(80) required
  parent: ref Node optional
"""

_DSL_MULTI_FK = """\
module app

app multi "Multi":
  security_profile: standard

entity Author "Author":
  id: uuid pk
  name: str(80) required

entity Category "Category":
  id: uuid pk
  name: str(80) required

entity Book "Book":
  id: uuid pk
  title: str(120) required
  author: ref Author required
  category: ref Category optional
"""

_DSL_PLAIN = """\
module app

app plain "Plain":
  security_profile: standard

entity Task "Task":
  id: uuid pk
  title: str(200) required
  done: bool=false
"""

# (label, dsl-text) — inline projects written to a scratch dir.
_INLINE_CORPUS: list[tuple[str, str]] = [
    ("cyclic_self_ref", _DSL_CYCLIC),
    ("multi_fk", _DSL_MULTI_FK),
    ("plain", _DSL_PLAIN),
]

# A handful of real example apps — diverse, real-world schema shapes.
_EXAMPLE_APPS: list[str] = ["simple_task", "contact_manager", "support_tickets"]


# ---------------------------------------------------------------------------
# PG / URL plumbing (mirrors test_framework_baseline_parity_pg.py)
# ---------------------------------------------------------------------------


def _skip_if_no_pg() -> None:
    if not _PG_URL:
        pytest.skip("TEST_DATABASE_URL / DATABASE_URL not set — skipping engine parity gate")


def _admin_url() -> str:
    return (_PG_URL or "").replace("postgresql+psycopg://", "postgresql://")


def _sa_url(plain_url: str) -> str:
    if plain_url.startswith("postgresql://"):
        return plain_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return plain_url


def _make_scratch_db() -> tuple[str, str]:
    """Create a disposable DB; return (plain_url, db_name)."""
    admin = _admin_url()
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_engine_parity_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep
    return f"{base}/{name}", name


def _drop_scratch_db(name: str) -> None:
    admin = _admin_url()
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            (name,),
        )
        a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------


def _write_inline_project(project: Path, dsl: str) -> None:
    (project / "dsl").mkdir(parents=True, exist_ok=True)
    (project / "dazzle.toml").write_text(
        '[project]\nroot = "app"\nname = "Parity"\n', encoding="utf-8"
    )
    (project / "dsl" / "app.dsl").write_text(dsl, encoding="utf-8")


def _copy_example_project(name: str, project: Path) -> None:
    """Copy an example's dsl/ + dazzle.toml into a fresh project (no migrations)."""
    import shutil

    src = Path(__file__).resolve().parents[2] / "examples" / name
    (project / "dsl").mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "dazzle.toml", project / "dazzle.toml")
    for f in (src / "dsl").glob("*.dsl"):
        shutil.copy(f, project / "dsl" / f.name)


# ---------------------------------------------------------------------------
# The two paths
# ---------------------------------------------------------------------------


def _introspect_project_tables(plain_url: str) -> dict[str, Any]:
    """Introspect *plain_url* and drop framework-owned tables (snake_case runtime
    tables created by ensure_framework_schema, never by a project baseline)."""
    from dazzle.db.schema_snapshot import introspect_schema
    from dazzle.http.alembic.framework_tables import is_framework_table

    eng = sa.create_engine(_sa_url(plain_url))
    try:
        full = introspect_schema(eng)
    finally:
        eng.dispose()
    return {t: s for t, s in full.items() if not is_framework_table(t)}


def _reference_via_create_all(project: Path, plain_url: str, monkeypatch: Any) -> dict[str, Any]:
    """The trusted reference: create_all of the project's DSL metadata."""
    from dazzle.http.alembic.metadata_loader import load_target_metadata

    monkeypatch.chdir(project)
    md = load_target_metadata()
    eng = sa.create_engine(_sa_url(plain_url))
    try:
        md.create_all(eng)
    finally:
        eng.dispose()
    return _introspect_project_tables(plain_url)


def _engine_baseline(project: Path, plain_url: str, monkeypatch: Any) -> dict[str, Any]:
    """The engine path: framework schema materialized, then db baseline + upgrade."""
    from dazzle.cli.db import baseline_command, stamp_command, upgrade_command
    from dazzle.http.runtime.framework_schema import ensure_framework_schema

    psycopg_url = _sa_url(plain_url)
    monkeypatch.chdir(project)
    monkeypatch.setenv("DATABASE_URL", psycopg_url)
    monkeypatch.delenv("DAZZLE_ENV", raising=False)

    # Materialize framework tables so any project→framework FK resolves at upgrade,
    # then stamp the framework baseline head so alembic's "DB up to date" holds.
    with psycopg.connect(plain_url) as conn:
        conn.autocommit = False
        ensure_framework_schema(conn)
    stamp_command(revision="head")

    baseline_command(database_url="", apply=False)
    upgrade_command(revision="head", no_rls=True)
    return _introspect_project_tables(plain_url)


# ---------------------------------------------------------------------------
# Name-insensitive normalization + comparison
# ---------------------------------------------------------------------------


def _norm_default(default: str | None) -> str | None:
    """Neutralize wall-clock-nondeterministic defaults so parity isn't flaky.

    A column default of ``'now'`` is frozen by PostgreSQL to a literal timestamp
    *at table-creation time* (the classic ``DEFAULT 'now'`` string-literal gotcha).
    ``create_all`` and the engine baseline create their tables moments apart, so
    the frozen literals differ by microseconds — semantically identical, textually
    not. Collapse any frozen-timestamp literal to a single sentinel; every other
    default (enum strings, booleans, ``gen_random_uuid()``, NULL) is compared verbatim.
    """
    if default is not None and "::timestamp" in default and default.startswith("'"):
        return "<frozen-timestamp-default>"
    return default


def _normalize(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reduce a rich introspect snapshot to a name-insensitive comparable form."""
    out: dict[str, Any] = {}
    for tname, tsnap in snapshot.items():
        columns = {
            cname: {
                "type": c.get("type"),
                "nullable": c.get("nullable"),
                "pk": c.get("pk"),
                "default": _norm_default(c.get("default")),
            }
            for cname, c in tsnap.get("columns", {}).items()
        }
        # FKs: keyed by column → referenced table (name-insensitive already).
        fks = dict(tsnap.get("fks", {}))
        # Indexes by SHAPE (sorted columns, uniqueness, predicate) — drop names.
        index_shapes = {
            (tuple(sorted(idx.get("columns", []))), bool(idx.get("unique")), idx.get("predicate"))
            for idx in tsnap.get("indexes", {}).values()
        }
        out[tname] = {"columns": columns, "fks": fks, "indexes": index_shapes}
    return out


def _diff_report(ref: dict[str, Any], eng: dict[str, Any]) -> str:
    lines: list[str] = []
    ref_t, eng_t = set(ref), set(eng)
    if ref_t != eng_t:
        lines.append(f"  tables only in create_all: {sorted(ref_t - eng_t)}")
        lines.append(f"  tables only in engine:     {sorted(eng_t - ref_t)}")
    for t in sorted(ref_t & eng_t):
        r, e = ref[t], eng[t]
        if r["columns"] != e["columns"]:
            for col in sorted(set(r["columns"]) | set(e["columns"])):
                if r["columns"].get(col) != e["columns"].get(col):
                    lines.append(
                        f"  {t}.{col}: create_all={r['columns'].get(col)} engine={e['columns'].get(col)}"
                    )
        if r["fks"] != e["fks"]:
            lines.append(f"  {t} FKs: create_all={r['fks']} engine={e['fks']}")
        if r["indexes"] != e["indexes"]:
            lines.append(
                f"  {t} indexes: only-create_all={r['indexes'] - e['indexes']} "
                f"only-engine={e['indexes'] - r['indexes']}"
            )
    return "\n".join(lines) or "  (no field-level diff surfaced — check table sets)"


def _run_parity(setup: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run both paths against fresh scratch DBs and assert project-schema parity."""
    _skip_if_no_pg()

    ref_url, ref_name = _make_scratch_db()
    eng_url, eng_name = _make_scratch_db()
    try:
        ref_proj = tmp_path / "ref_proj"
        eng_proj = tmp_path / "eng_proj"
        ref_proj.mkdir()
        eng_proj.mkdir()
        setup(ref_proj)
        setup(eng_proj)

        reference = _normalize(_reference_via_create_all(ref_proj, ref_url, monkeypatch))
        engine = _normalize(_engine_baseline(eng_proj, eng_url, monkeypatch))

        assert reference == engine, (
            "engine baseline schema diverges from create_all (project tables):\n"
            + _diff_report(reference, engine)
        )
        # Guard against a vacuous pass: the corpus must produce at least one table.
        assert reference, "no project tables introspected — parity check was vacuous"
    finally:
        _drop_scratch_db(ref_name)
        _drop_scratch_db(eng_name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,dsl", _INLINE_CORPUS, ids=[c[0] for c in _INLINE_CORPUS])
def test_engine_baseline_matches_create_all_inline(
    label: str, dsl: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Engine baseline ≡ create_all for inline DSLs covering the FK bug classes
    (Org↔Person cycle, Node self-ref, multi-FK, plain). The cyclic/self-ref case is
    the #1460 regression guard: a dropped FK shows up as an `fks` mismatch."""
    _run_parity(lambda p: _write_inline_project(p, dsl), monkeypatch, tmp_path)


@pytest.mark.parametrize("app", _EXAMPLE_APPS)
def test_engine_baseline_matches_create_all_examples(
    app: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Engine baseline ≡ create_all across real example apps — broad coverage that
    grows automatically as the example set expands."""
    _run_parity(lambda p: _copy_example_project(app, p), monkeypatch, tmp_path)


# Round-trip: V1 baseline, then an incremental revision adds an entity with an FK,
# a unique field and an indexed field. The end state must equal create_all of V2 —
# proving the *incremental* path (db revision) reaches parity, not just baseline.
_DSL_RT_V1 = """\
module app

app rt "RT":
  security_profile: standard

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""

_DSL_RT_V2 = """\
module app

app rt "RT":
  security_profile: standard

entity Task "Task":
  id: uuid pk
  title: str(200) required

entity Note "Note":
  id: uuid pk
  task: ref Task required
  slug: str(40) unique
  body: str(500)
"""


def test_engine_revision_roundtrip_reaches_create_all_parity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """baseline(V1) → revision(V2) → upgrade  ≡  create_all(V2 metadata)."""
    _skip_if_no_pg()
    from dazzle.cli.db import revision_command, upgrade_command

    ref_url, ref_name = _make_scratch_db()
    eng_url, eng_name = _make_scratch_db()
    try:
        # Reference: create_all of the V2 DSL.
        ref_proj = tmp_path / "ref"
        ref_proj.mkdir()
        _write_inline_project(ref_proj, _DSL_RT_V2)
        reference = _normalize(_reference_via_create_all(ref_proj, ref_url, monkeypatch))

        # Engine: baseline V1, then add the Note entity and run an incremental revision.
        eng_proj = tmp_path / "eng"
        eng_proj.mkdir()
        _write_inline_project(eng_proj, _DSL_RT_V1)
        _engine_baseline(eng_proj, eng_url, monkeypatch)  # chdir + DATABASE_URL set here
        (eng_proj / "dsl" / "app.dsl").write_text(_DSL_RT_V2, encoding="utf-8")
        revision_command(message="add note", autogenerate=True, legacy_autogenerate=False)
        upgrade_command(revision="head", no_rls=True)
        engine = _normalize(_introspect_project_tables(eng_url))

        assert reference == engine, (
            "engine revision round-trip diverges from create_all(V2):\n"
            + _diff_report(reference, engine)
        )
        assert "Note" in reference and "Note" in engine, "round-trip must add the Note table"
    finally:
        _drop_scratch_db(ref_name)
        _drop_scratch_db(eng_name)
