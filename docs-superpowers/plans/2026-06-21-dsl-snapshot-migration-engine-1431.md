# DSL-Snapshot IR-Diff Migration Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate Alembic migrations by diffing a per-revision DSL schema snapshot against the current AppSpec (DSL-vs-DSL), so `dazzle db revision` emits exactly the intended structural changes — never spurious destructive rewrites from metadata-vs-DB noise.

**Architecture:** We own the *comparison* (snapshot → current projection → typed `SchemaDelta`); Alembic owns *rendering + execution* (we render the delta into `alembic.operations.ops` objects and let Alembic author the file + run upgrade/downgrade). Each generated revision embeds a `SCHEMA_SNAPSHOT` constant = the relational schema as-of that revision; the next revision diffs against the project-lineage head's snapshot.

**Tech Stack:** Python 3.12+, Alembic 1.18.4 (`alembic.operations.ops`), SQLAlchemy, psycopg3 (PostgreSQL-only), Pydantic IR (`EntitySpec`/`FieldSpec`), the Dazzle DSL parser.

## Global Constraints

- **PostgreSQL-only** runtime (ADR-0008). No SQLite.
- **All schema changes via Alembic** (ADR-0017) — this engine *generates* Alembic revisions; it does not bypass them.
- **No `re` in the parser** (ADR-0024) — new lexical shapes go in `src/dazzle/core/dsl_parser_impl/_lexical.py`.
- **No `from __future__ import annotations`** in FastAPI route files (ADR-0014) — N/A to most engine files (they're not routes), but applies if a route file is touched.
- **Type hints required** on public functions (`mypy src/dazzle`).
- **Out of scope (do NOT touch):** RLS policy generation/apply (`dazzle.db.rls_*` — separate idempotent reconcile), enum handling (TEXT), PK-type canonicalization (issue #1432).
- **Snapshot is the relational slice only:** tables (entities), columns (name/type/nullable/default/pk/unique), FK columns (refs), indexes. Exclude UI/validator/computed/state-machine fields and framework-injected implicit columns (id handling per Task 1.1) from the *diffable* projection.
- **Pure where possible:** projection, differ, and renderer take plain inputs and return plain outputs (no DB, no FastAPI) so they are exhaustively unit-testable. The differ mirrors `apex_discovery.resolve_apex_redirect`'s pure-mapper style.
- **Pre-ship gates:** `pytest tests/ -m "not e2e"`, `DATABASE_URL=… pytest -m postgres` (this touches migrations/alembic env), `ruff check src/ tests/ --fix && ruff format`, `mypy src/dazzle`. Run with `TEST_DATABASE_URL=postgresql://james@localhost:5432/dazzle_test` for PG tests.
- **Ship discipline:** `/bump patch` + CHANGELOG per shipped phase; clean worktree.

---

## File Structure

**New:**
- `src/dazzle/db/schema_snapshot.py` — `Snapshot` shape + `project_schema(appspec) -> Snapshot`, `render_snapshot_literal(snapshot) -> str`, `load_head_snapshot(cfg) -> Snapshot`.
- `src/dazzle/db/schema_diff.py` — `SchemaDelta` op dataclasses + `RenameHints` + pure `diff(prev, curr, hints) -> list[SchemaOp]`.
- `src/dazzle/db/schema_render.py` — `render(ops) -> alembic ops.UpgradeOps` (+ inverse) incl. expand/contract scaffold + data-seam emission.
- `src/dazzle/db/migration_engine.py` — orchestrator `generate_revision(appspec, cfg) -> RevisionPlan` tying projection→diff→render + the embedded-snapshot wiring; `snapshot_baseline(appspec, cfg)`.
- Tests: `tests/unit/test_schema_snapshot.py`, `test_schema_diff.py`, `test_schema_render.py`, `tests/integration/test_migration_engine_pg.py`.

**Modified:**
- `src/dazzle/cli/db.py` — `revision_command` routes through the engine; `--legacy-autogenerate` flag; `snapshot-baseline` subcommand; post-gen verification.
- `src/dazzle/core/dsl_parser_impl/_lexical.py` + the entity/field parser mixin — `was:` clause.
- `src/dazzle/core/ir/fields.py` + `src/dazzle/core/ir/domain.py` — `FieldSpec.renamed_from` / `EntitySpec.renamed_from` (core.ir types the parser populates).
- `docs/reference/grammar.md`, `tests/unit/test_docs_drift.py` — `was:` clause.
- `src/dazzle/http/alembic/env.py` — engine injects rendered ops + embeds the snapshot via `process_revision_directives` (legacy guardrail stays for the `--legacy-autogenerate` path).

---

## Data shapes (used across tasks — JSON-serializable plain dicts)

```python
# Snapshot = dict[str, TableSnap]                       # keyed by table name (sorted)
# TableSnap = {
#   "columns": dict[str, ColSnap],                      # keyed by column name (sorted)
#   "indexes": list[str],                               # indexed column names (sorted)
#   "uniques": list[str],                               # unique column names (sorted)
#   "fks": dict[str, str],                              # column name -> referenced table
# }
# ColSnap = {"type": str, "nullable": bool, "default": str | None, "pk": bool}
#   type is a canonical token: "text" | "integer" | "bigint" | "boolean" | "numeric(p,s)"
#   | "float" | "date" | "timestamptz" | "uuid" | "json"
```

Plain dicts make the embedded `SCHEMA_SNAPSHOT = {...}` literal trivial to render and re-read, and make the differ a pure dict comparison.

---

## Phase 1 — Snapshot projection + storage

### Task 1.1: `project_schema` — AppSpec → relational Snapshot

**Files:**
- Create: `src/dazzle/db/schema_snapshot.py`
- Test: `tests/unit/test_schema_snapshot.py`

**Interfaces:**
- **Critical design correction (verified against the code):** do NOT re-derive entity→table / field→column mapping rules. Tables are named `entity.name` *verbatim* (`sa.Table(entity.name, ...)`, sa_schema.py:632 — e.g. `"Invoice"`, NOT `"invoices"`), FK columns are `field.name` *verbatim* (not `<name>_id`), and shared_schema injects `tenant_id` + composite FKs + indexes. The single source of truth is `dazzle.http.alembic.metadata_loader.load_target_metadata() -> sqlalchemy.MetaData` (importable, side-effect-free; the SAME builder Alembic's autogenerate target uses; it loads the project appspec from CWD and calls `sa_schema.build_metadata` with the right `partition_key`/`tenant_scoped`/`surfaces`). The projection **introspects that MetaData** → the snapshot is definitionally aligned with the real schema.
- Consumes: `sqlalchemy.MetaData` (`.sorted_tables`; per `sa.Table`: `.name`, `.columns` → `sa.Column(.name, .type, .nullable, .server_default, .primary_key)`, `.foreign_keys` → `fk.column.table.name`, `.indexes`, unique constraints); `metadata_loader.load_target_metadata`.
- Produces:
  - `project_schema(metadata: sqlalchemy.MetaData) -> Snapshot` — **pure introspection** (unit-testable with a hand-built MetaData; no DB, no CWD dependency).
  - `project_current() -> Snapshot` — thin wrapper: `project_schema(load_target_metadata())`.
  - `_sa_type_to_token(sa_type: Any) -> str` — map a SQLAlchemy type instance → the canonical token (`Text→"text"`, `Integer→"integer"`, `BigInteger→"bigint"`, `Boolean→"boolean"`, `Numeric→f"numeric({p},{s})"`, `Float→"float"`, `Date→"date"`, `DateTime→"timestamptz"`, `Uuid→"uuid"`, `JSON→"json"`; fallback `str(sa_type).lower()`).

- [ ] **Step 1: Write the failing test** (pure introspection — build a small MetaData by hand)

```python
import sqlalchemy as sa
from dazzle.db.schema_snapshot import project_schema


def _meta():
    md = sa.MetaData()
    sa.Table("Customer", md, sa.Column("id", sa.Uuid(), primary_key=True),
             sa.Column("name", sa.Text(), nullable=False))
    sa.Table("Invoice", md, sa.Column("id", sa.Uuid(), primary_key=True),
             sa.Column("total", sa.Integer(), nullable=True),
             sa.Column("customer", sa.Uuid(), sa.ForeignKey("Customer.id")))
    return md


def test_project_schema_introspects_metadata():
    snap = project_schema(_meta())
    # Table names are the entity names VERBATIM (not pluralised/lowercased).
    assert set(snap) == {"Customer", "Invoice"}
    inv = snap["Invoice"]
    assert inv["columns"]["total"]["type"] == "integer"
    assert inv["columns"]["total"]["nullable"] is True
    assert inv["columns"]["id"]["pk"] is True
    # FK column is the field name VERBATIM; target is the referenced table name.
    assert inv["fks"]["customer"] == "Customer"


def test_project_schema_is_deterministic():
    assert project_schema(_meta()) == project_schema(_meta())  # sorted, stable
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/unit/test_schema_snapshot.py -v` → ImportError.

- [ ] **Step 3: Implement `project_schema`** — pure introspection of `metadata.sorted_tables`:
  - table key = `table.name`;
  - per `sa.Column`: `ColSnap` = `{"type": _sa_type_to_token(col.type), "nullable": bool(col.nullable), "default": _render_server_default(col.server_default), "pk": bool(col.primary_key)}` (`_render_server_default` → the SQL text string or `None`);
  - `fks`: `{col.name: fk.column.table.name for col in table.columns for fk in col.foreign_keys}`;
  - `uniques`: column names with `col.unique` plus single-column `UniqueConstraint` columns;
  - `indexes`: sorted column names covered by `table.indexes` (single-column indexes; composite indexes recorded as the tuple-joined key — keep simple: list each index's column-name list joined by `,`);
  - sort every dict key + list for determinism.
  Then `project_current()` = `project_schema(load_target_metadata())`, and `_sa_type_to_token` per the mapping above. Document in the module docstring that the snapshot is whatever `load_target_metadata` produces (incl. shared_schema `tenant_id`/composite-FK/index injection) — so it is always consistent with the canonical schema, no exclusion list needed.

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit** `feat(db): project_schema by introspecting canonical MetaData (#1431 phase 1)`

### Task 1.2: Snapshot literal render + round-trip

**Files:**
- Modify: `src/dazzle/db/schema_snapshot.py`
- Test: `tests/unit/test_schema_snapshot.py`

**Interfaces:**
- Produces: `render_snapshot_literal(snapshot: Snapshot) -> str` — returns a deterministic Python source literal (sorted keys, stable formatting) suitable for embedding as `SCHEMA_SNAPSHOT = <literal>` in a revision file. `parse_snapshot_literal(src: str) -> Snapshot` is NOT needed (we import the module); but a `snapshot_from_module(module) -> Snapshot` reading `getattr(module, "SCHEMA_SNAPSHOT", {})` is.

- [ ] **Step 1: Failing test**

```python
from dazzle.db.schema_snapshot import project_schema, render_snapshot_literal


def test_snapshot_literal_roundtrips(simple_appspec):
    snap = project_schema(simple_appspec)
    literal = render_snapshot_literal(snap)
    # The literal is valid Python that evaluates back to the same dict.
    assert eval(literal) == snap  # noqa: S307 — test-only, trusted input
    # Deterministic: same input → identical source.
    assert render_snapshot_literal(snap) == literal
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `render_snapshot_literal` using `pprint.pformat(snapshot, sort_dicts=True, width=88)` (deterministic) + `snapshot_from_module`.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(db): deterministic snapshot literal + module read (#1431 phase 1)`

### Task 1.3: `load_head_snapshot` — read the project-lineage head's snapshot

**Files:**
- Modify: `src/dazzle/db/schema_snapshot.py`
- Test: `tests/integration/test_migration_engine_pg.py` (or a unit test with a temp versions dir — preferred, no DB needed)

**Interfaces:**
- Consumes: the project versions dir (`dazzle.cli.db._get_project_versions_dir()`), Alembic's `ScriptDirectory` to resolve the current head revision.
- Produces: `load_head_snapshot(script_dir: Any) -> Snapshot` — resolve the project-lineage head revision, import its module, return `snapshot_from_module(...)`; return `{}` when there is no head or the head has no `SCHEMA_SNAPSHOT` (pre-engine migration → empty; the baseline-stamp command handles adoption, Task 6.2).

- [ ] **Step 1: Failing test** — create a temp versions dir with a fake revision module exposing `SCHEMA_SNAPSHOT = {...}`; assert `load_head_snapshot` returns it; a dir with a revision lacking the constant → `{}`.
- [ ] **Step 2–4:** implement using `alembic.script.ScriptDirectory` to get the head + `importlib` to load the module (mirror any existing revision-loading in `db.py`); RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): load embedded snapshot from project head revision (#1431 phase 1)`

### Task 1.4: Ship Phase 1 — gates + `/bump patch` + CHANGELOG `### Added` (snapshot projection + storage, no behaviour change yet — nothing wired into `db revision`).

---

## Phase 2 — Differ

### Task 2.1: `SchemaDelta` op types

**Files:**
- Create: `src/dazzle/db/schema_diff.py`
- Test: `tests/unit/test_schema_diff.py`

**Interfaces:**
- Produces: frozen dataclasses — `AddTable(table, columns, fks, indexes, uniques)`, `DropTable(table, snap)`, `RenameTable(old, new)`, `AddColumn(table, name, col)`, `DropColumn(table, name, col)`, `RenameColumn(table, old, new)`, `AlterColumn(table, name, old, new)`, `AddForeignKey(table, column, ref_table)`, `DropForeignKey(table, column, ref_table)`, `AddIndex(table, column)`, `DropIndex(table, column)`, `AddUnique(table, column)`, `DropUnique(table, column)`. `SchemaOp = <union>`. `DropTable`/`DropColumn` carry the prior snap for downgrade.

- [ ] **Step 1: Failing test** — construct each op, assert frozen + field access.
- [ ] **Step 2–4:** define the dataclasses (`@dataclass(frozen=True)`); RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): SchemaDelta op types (#1431 phase 2)`

### Task 2.2: `diff` — pure snapshot comparison (no renames yet)

**Files:**
- Modify: `src/dazzle/db/schema_diff.py`
- Test: `tests/unit/test_schema_diff.py`

**Interfaces:**
- Produces: `diff(prev: Snapshot, curr: Snapshot, hints: RenameHints | None = None) -> list[SchemaOp]`. Phase-2 ignores `hints` (Task 4.x adds rename resolution). Ordering: `RenameTable`/`RenameColumn` (later) → `AddTable` → `AddColumn`/`AddForeignKey`/`AddIndex`/`AddUnique` → `AlterColumn` → `DropColumn`/`DropForeignKey`/`DropIndex`/`DropUnique` → `DropTable`. A table only in `curr` → `AddTable`; only in `prev` → `DropTable`; in both → per-column diff (added/dropped/altered) + index/unique/fk set diffs. `AlterColumn` when a same-named column's `ColSnap` differs.

- [ ] **Step 1: Failing test**

```python
from dazzle.db.schema_diff import diff, AddTable, AddColumn, DropColumn, AlterColumn, DropTable

_COL = {"type": "text", "nullable": True, "default": None, "pk": False}


def _tbl(**cols):
    return {"columns": cols, "indexes": [], "uniques": [], "fks": {}}


def test_new_table_is_add_table():
    ops = diff({}, {"t": _tbl(id={"type": "uuid", "nullable": False, "default": None, "pk": True})})
    assert any(isinstance(o, AddTable) and o.table == "t" for o in ops)


def test_added_column():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": _tbl(a=_COL, b=_COL)}
    ops = diff(prev, curr)
    assert [o for o in ops if isinstance(o, AddColumn)][0].name == "b"


def test_dropped_column():
    ops = diff({"t": _tbl(a=_COL, b=_COL)}, {"t": _tbl(a=_COL)})
    assert [o for o in ops if isinstance(o, DropColumn)][0].name == "b"


def test_altered_column_type():
    prev = {"t": _tbl(a={**_COL, "type": "text"})}
    curr = {"t": _tbl(a={**_COL, "type": "integer"})}
    ops = diff(prev, curr)
    alt = [o for o in ops if isinstance(o, AlterColumn)][0]
    assert alt.old["type"] == "text" and alt.new["type"] == "integer"


def test_dropped_table():
    ops = diff({"t": _tbl(a=_COL)}, {})
    assert any(isinstance(o, DropTable) and o.table == "t" for o in ops)


def test_no_change_empty_delta():
    assert diff({"t": _tbl(a=_COL)}, {"t": _tbl(a=_COL)}) == []
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the pure dict comparison with the ordering above.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(db): pure snapshot differ (add/drop/alter) (#1431 phase 2)`

### Task 2.3: Ship Phase 2 — gates + `/bump patch` + CHANGELOG.

---

## Phase 3 — Renderer + `db revision` wiring (engine becomes live for add/drop/alter)

### Task 3.1: `render` — SchemaDelta → Alembic UpgradeOps

**Files:**
- Create: `src/dazzle/db/schema_render.py`
- Test: `tests/unit/test_schema_render.py`

**Interfaces:**
- Consumes: the `SchemaOp` types; `alembic.operations.ops` (CreateTableOp, AddColumnOp, DropColumnOp, AlterColumnOp, ModifyTableOps, CreateIndexOp, DropIndexOp, CreateForeignKeyOp, DropConstraintOp, UpgradeOps); a `ColSnap`→`sa.Column` builder (reuse the canonical-token→SA-type inverse of `_canonical_type`).
- Produces: `render(ops: list[SchemaOp]) -> alembic_ops.UpgradeOps`. Downgrade is produced by the caller via `.reverse()` for the additive subset; ops whose reverse needs prior state (`DropColumn`/`DropTable` carry `snap`/`col`; `AlterColumn` carries `old`) get explicit inverse handling — return a `(UpgradeOps, DowngradeOps)` tuple so the downgrade is always exact. Final signature: `render(ops) -> tuple[UpgradeOps, DowngradeOps]`.

- [ ] **Step 1: Failing test**

```python
from alembic.operations import ops as aops
from dazzle.db.schema_diff import AddTable, AddColumn
from dazzle.db.schema_render import render

_COL = {"type": "text", "nullable": True, "default": None, "pk": False}


def test_add_table_renders_create_table():
    up, down = render([AddTable("t", {"id": {"type": "uuid", "nullable": False, "default": None, "pk": True}}, {}, [], [])])
    assert any(isinstance(o, aops.CreateTableOp) and o.table_name == "t" for o in up.ops)
    # downgrade drops it
    assert any(isinstance(o, aops.DropTableOp) and o.table_name == "t" for o in down.ops)


def test_add_column_renders_add_and_inverse_drop():
    up, down = render([AddColumn("t", "b", _COL)])
    add = [o for o in up.ops if isinstance(o, aops.ModifyTableOps)][0]
    assert any(isinstance(s, aops.AddColumnOp) for s in add.ops)
    drop = [o for o in down.ops if isinstance(o, aops.ModifyTableOps)][0]
    assert any(isinstance(s, aops.DropColumnOp) for s in drop.ops)
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the per-op renderer + the `ColSnap → sa.Column` builder + explicit inverse construction. Reuse `dazzle.http.runtime.safe_casts.get_using_clause` for `AlterColumn` type changes (set `postgresql_using`).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(db): render SchemaDelta to Alembic ops + exact inverse (#1431 phase 3)`

### Task 3.2: `migration_engine.generate_revision` orchestrator

**Files:**
- Create: `src/dazzle/db/migration_engine.py`
- Test: `tests/unit/test_migration_engine.py`

**Interfaces:**
- Consumes: `project_schema`, `load_head_snapshot`, `render_snapshot_literal` (Phase 1); `diff` (Phase 2); `render` (Task 3.1).
- Produces: `generate_revision(appspec, script_dir) -> RevisionPlan` where `RevisionPlan = {upgrade_ops, downgrade_ops, snapshot_literal, is_empty}`. It: projects current → loads head snapshot → diffs → renders → returns the plan + the current snapshot literal for embedding. `is_empty` True when the delta is empty (caller suppresses the revision).

- [ ] **Step 1: Failing test** — a fake `script_dir` returning a head snapshot + a current appspec with one new entity → `generate_revision` returns a non-empty plan whose `upgrade_ops` contains the CreateTableOp and whose `snapshot_literal` round-trips to the current projection.
- [ ] **Step 2–4:** implement; RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): migration engine orchestrator (#1431 phase 3)`

### Task 3.3: Wire `dazzle db revision` to the engine + embed the snapshot

**Files:**
- Modify: `src/dazzle/cli/db.py` (`revision_command`), `src/dazzle/http/alembic/env.py` (`_process_revision_directives`)
- Test: `tests/integration/test_migration_engine_pg.py`

**Interfaces:** `revision_command` loads the appspec (`load_project_appspec`), calls `generate_revision`, and drives Alembic to write a revision whose `upgrade()`/`downgrade()` are the rendered ops AND which carries `SCHEMA_SNAPSHOT = <literal>`. The cleanest seam: in `env.py` `_process_revision_directives`, when the engine is active, REPLACE `script.upgrade_ops`/`downgrade_ops` with the engine's rendered ops and stash the snapshot literal so the revision template emits it (use a custom `file_template`/`process_revision_directives` write, or post-write the constant into the generated file — pick the approach that fits Alembic 1.18 and the existing template; document it). Keep the legacy autogenerate path (with the #1427 additive guardrail) behind `--legacy-autogenerate`.

- [ ] **Step 1: Failing test (PG)** — in a scratch DB: stamp a baseline snapshot, add an entity to the appspec, run the engine revision, assert the generated file contains `SCHEMA_SNAPSHOT`, contains a `create_table`, contains NO `drop`/`alter` for unrelated tables, and `db upgrade` applies it cleanly.
- [ ] **Step 2–4:** implement the wiring; RED→GREEN. (This is the integration-heavy task — verify the runtime path, not just the unit: actually run `dazzle db revision` against the scratch DB.)
- [ ] **Step 5: Commit** `feat(db): db revision uses the snapshot-diff engine (#1431 phase 3)`

### Task 3.4: Ship Phase 3 — full gates incl. `-m postgres`; `/bump patch`; CHANGELOG `### Added` + `### Agent Guidance` (db revision is now DSL-diff-driven; `--legacy-autogenerate` is the escape hatch).

---

## Phase 4 — `was:` rename grammar + rename resolution

### Task 4.1: IR — `renamed_from` on field/entity specs

**Files:**
- **Correction (verified):** `renamed_from` goes on the **core.ir** types the PARSER populates and that `extract_rename_hints(appspec)` reads off `appspec.domain.entities` — NOT the converted `http/specs/entity.py` runtime types. Modify `src/dazzle/core/ir/fields.py` (`FieldSpec`, line ~164) and `src/dazzle/core/ir/domain.py` (`EntitySpec`, line ~433).
- Test: `tests/unit/test_parser.py` or a core.ir spec test (construct the core.ir `FieldSpec`/`EntitySpec`).

**Interfaces:** `dazzle.core.ir.fields.FieldSpec.renamed_from: str | None = None`, `dazzle.core.ir.domain.EntitySpec.renamed_from: str | None = None`.

- [ ] **Step 1: Failing test** — construct `dazzle.core.ir.fields.FieldSpec(..., renamed_from="old")` and `dazzle.core.ir.domain.EntitySpec(..., renamed_from="Old")`; assert the attr.
- [ ] **Step 2–4:** add the fields (default None); RED→GREEN; confirm no IR-surface drift test breaks (update `docs/api-surface/ir-types` baseline via `dazzle inspect api ir-types --write` if needed + a CHANGELOG note).
- [ ] **Step 5: Commit** `feat(ir): renamed_from on field/entity specs (#1431 phase 4)`

### Task 4.2: `was:` lexer + parser

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/_lexical.py` + the entity/field parser mixin (find via `grep -rn "def _parse_field\|def _parse_entity" src/dazzle/core/dsl_parser_impl/`)
- Test: `tests/unit/test_parser.py`

**Interfaces:** Parse `field new_name <type> ... was: old_name` → `FieldSpec.renamed_from="old_name"`; `entity NewName "..." was: OldName` → `EntitySpec.renamed_from="OldName"`. Lexical shape (the `was:` token + identifier) in `_lexical.py` per ADR-0024 (no `re` in the parser).

- [ ] **Step 1: Failing test** — parse DSL snippets with `was:` on a field and an entity; assert `renamed_from` is populated; a `was:` with no identifier → parse error.
- [ ] **Step 2–4:** implement lexer shape + parser handling; RED→GREEN. Update `docs/reference/grammar.md` + `tests/unit/test_docs_drift.py`.
- [ ] **Step 5: Commit** `feat(dsl): was: rename hint grammar (#1431 phase 4)`

### Task 4.3: Rename resolution in the differ

**Files:**
- Modify: `src/dazzle/db/schema_diff.py`, `src/dazzle/db/migration_engine.py` (extract `RenameHints` from the appspec's `renamed_from`)
- Test: `tests/unit/test_schema_diff.py`

**Interfaces:** `RenameHints = {"tables": dict[str, str], "columns": dict[tuple[str, str], str]}` (new→old). `extract_rename_hints(appspec) -> RenameHints`. `diff(prev, curr, hints)` now: before computing add/drop, resolve renames — a table/column whose `hints` `old` is in `prev` and whose `new` is in `curr` (and `new` not in `prev`) → emit `RenameTable`/`RenameColumn` and treat the pair as matched (no add/drop). Lifecycle: `old` not in `prev` but `new` in `prev` → already-applied, no-op; neither resolvable → raise `RenameResolutionError(entity/field, old)`.

- [ ] **Step 1: Failing test**

```python
import pytest
from dazzle.db.schema_diff import diff, RenameColumn, RenameResolutionError

_COL = {"type": "text", "nullable": True, "default": None, "pk": False}
def _tbl(**c): return {"columns": c, "indexes": [], "uniques": [], "fks": {}}


def test_was_hint_renders_rename_not_drop_add():
    prev = {"t": _tbl(old_name=_COL)}
    curr = {"t": _tbl(new_name=_COL)}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    ops = diff(prev, curr, hints)
    assert any(isinstance(o, RenameColumn) and o.old == "old_name" and o.new == "new_name" for o in ops)


def test_already_applied_rename_is_noop():
    prev = {"t": _tbl(new_name=_COL)}  # already renamed
    curr = {"t": _tbl(new_name=_COL)}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    assert diff(prev, curr, hints) == []


def test_dangling_rename_raises():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": _tbl(b=_COL)}
    hints = {"tables": {}, "columns": {("t", "b"): "nonexistent"}}
    with pytest.raises(RenameResolutionError):
        diff(prev, curr, hints)
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** rename resolution + `extract_rename_hints` + render `RenameTable`/`RenameColumn` (Task 3.1 renderer gains `op.rename_table`/`alter_column(new_column_name=...)`).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `feat(db): was: rename resolution in differ + renderer (#1431 phase 4)`

### Task 4.4: Ship Phase 4 — gates + `/bump patch` + CHANGELOG.

---

## Phase 5 — Data-migration seam + expand/contract

### Task 5.1: Marked data seam + unsafe-change scaffold

**Files:**
- Modify: `src/dazzle/db/schema_render.py`
- Test: `tests/unit/test_schema_render.py`

**Interfaces:** The renderer marks unsafe ops and emits the expand/contract scaffold:
- `AddColumn` with `nullable=False` and no `default` → render as: add nullable → **data seam** → `alter_column(nullable=False)`.
- `AlterColumn` with a type change → add new typed column / cast scaffold with the data seam (or keep the `postgresql_using` cast when safe per `safe_casts`; only scaffold when the cast isn't in the safe set).
- The data seam is a marked block emitted into the generated `upgrade()` body: `# === DATA MIGRATION (hand-author) ===` … `# === END DATA MIGRATION ===` with a commented `op.execute("...")` example. Implement as a small marker op (a `ops.ExecuteSQLOp`-adjacent placeholder, or a post-render text injection into the generated file body — pick what Alembic 1.18 supports cleanly and document).

- [ ] **Step 1: Failing test** — `render([AddColumn("t","x",{type:"text",nullable:False,default:None,pk:False})])` produces: an add-nullable op, a data-seam marker, and a finalize `alter_column nullable=False`. A safe `AlterColumn` (text→text length change) does NOT scaffold.
- [ ] **Step 2–4:** implement; RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): expand/contract data-migration seam (#1431 phase 5)`

### Task 5.2: Ship Phase 5 — gates + `/bump patch` + CHANGELOG.

---

## Phase 6 — CLI polish, verification, baseline adoption, e2e

### Task 6.1: `--legacy-autogenerate` flag + post-gen verification check

**Files:**
- Modify: `src/dazzle/cli/db.py`
- Test: `tests/unit/test_cli_db_ops.py`

**Interfaces:** `--legacy-autogenerate` routes to the old autogenerate path (with the #1427 guardrail). After an engine revision, optionally run `dazzle.db.rls_drift`-style metadata-vs-DB compare (Alembic `compare`) as a **warn-only** check: log if the live DB won't reach the expected post-state. Never generates ops.

- [ ] **Step 1: Failing test** — `--legacy-autogenerate` invokes the legacy path; default invokes the engine; the verification check logs (caplog) a warning when the DB diverges, never raises.
- [ ] **Step 2–4:** implement; RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): legacy-autogenerate escape hatch + verification check (#1431 phase 6)`

### Task 6.2: `dazzle db snapshot-baseline` adoption command

**Files:**
- Modify: `src/dazzle/cli/db.py`, `src/dazzle/db/migration_engine.py`
- Test: `tests/integration/test_migration_engine_pg.py`

**Interfaces:** `snapshot-baseline` stamps the current AppSpec projection as the head revision's baseline snapshot (for a project adopting the engine whose head migration predates `SCHEMA_SNAPSHOT`): generate an empty (no-op upgrade) revision carrying only `SCHEMA_SNAPSHOT = <current projection>`, so the next real `db revision` diffs from a correct baseline. `snapshot_baseline(appspec, script_dir)` in the engine.

- [ ] **Step 1: Failing test (PG)** — head revision has no snapshot → `load_head_snapshot` is `{}`; run `snapshot-baseline`; now the head carries the current projection; a subsequent no-op `db revision` emits nothing (empty delta).
- [ ] **Step 2–4:** implement; RED→GREEN.
- [ ] **Step 5: Commit** `feat(db): snapshot-baseline adoption command (#1431 phase 6)`

### Task 6.3: End-to-end sequence-walk (the non-destructive/intentful detector)

**Files:**
- Test: `tests/integration/test_migration_engine_pg.py`

**Interfaces:** A PG test that walks a *sequence* of AppSpec edits on a scratch DB, running `generate_revision` + `db upgrade` at each step, asserting each emits ONLY the intended ops and applies + rolls back cleanly:
1. baseline (2 entities) → 2. add entity → 3. add field → 4. rename field (`was:`) → 5. type change → 6. drop field.
At each step assert: no spurious ops on unrelated tables; the specific intended op present; `upgrade` then `downgrade` round-trips.

- [ ] **Step 1: Write the sequence test.**
- [ ] **Step 2: Run** (green = the engine is intentful + non-destructive end-to-end). Any failure localizes a real engine defect.
- [ ] **Step 3: Commit** `test(db): end-to-end migration-engine sequence walk (#1431 phase 6)`

### Task 6.4: Runbook doc + ship Phase 6

**Files:**
- Modify/Create: `docs/reference/migrations.md`
- Steps: document the engine (DSL-diff, embedded snapshot, `was:` renames, the data seam, `snapshot-baseline` adoption, `--legacy-autogenerate`). Full gates incl. `-m postgres` + the e2e. `/bump patch` + CHANGELOG. Comment on #1431 + close.

---

## Self-Review

**Spec coverage:**
- §3.1 snapshot projection+storage → Tasks 1.1/1.2/1.3. ✓
- §3.2 differ → 2.1/2.2 (+ rename in 4.3). ✓
- §3.3 renderer → 3.1 (+ rename render 4.3, data-seam 5.1). ✓
- §3.4 `was:` grammar → 4.1/4.2/4.3. ✓
- §3.5 data seam → 5.1. ✓
- §3.6 CLI wiring + verification → 3.3/6.1. ✓
- §6 edge cases: first revision (empty prev) → 2.2/3.2; framework-vs-project + implicit columns → 1.1; legacy-without-snapshot adoption → 6.2; dual-head → 1.3 (resolve project head). ✓
- §7 testing → pure unit tests per component + 6.3 sequence walk. ✓
- §8 phasing → Phases 1–6 match. ✓
- §9 out-of-scope (PK-canon) → not in plan (filed #1432). ✓

**Placeholder scan:** The integration-heavy tasks (3.3 env.py wiring, 5.1 seam emission, 6.1 verification) describe the seam + name the exact functions/Alembic APIs and say "pick the approach that fits Alembic 1.18 and document it" — these are genuine implementation choices that require the files open (the Alembic 1.18 revision-write/template seam can't be byte-specified without experimenting against the installed version); they are grounded directions, not vague placeholders. Pure-component tasks (1.x, 2.x, 3.1, 4.3) carry complete code.

**Type consistency:** `Snapshot`/`TableSnap`/`ColSnap` plain-dict shapes consistent across 1.1→2.2→3.1. `diff(prev, curr, hints)` signature consistent 2.2/4.3. `render(ops) -> (UpgradeOps, DowngradeOps)` consistent 3.1/3.2/5.1. `renamed_from` (IR) + `RenameHints` (new→old) consistent 4.1/4.2/4.3. `generate_revision(appspec, script_dir) -> RevisionPlan` consistent 3.2/3.3/6.2.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-21-dsl-snapshot-migration-engine-1431.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task + per-task review + final whole-branch review; adversarial review on the integration tasks (3.3, 5.1) and the e2e detector (6.3).
2. **Inline Execution** — execute in-session with checkpoints (CLAUDE.md hybrid default for Opus: inline for cross-task type coherence + independent review at the integration checkpoints).
