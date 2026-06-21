# DSL-snapshot IR-diff migration engine — design

**Issue:** #1431 (follow-on to #1427, whose additive-scoping guardrail shipped v0.83.59)
**Date:** 2026-06-21
**Status:** Design approved; ready for implementation plan.

---

## 1. Problem

`dazzle db revision --autogenerate` uses Alembic's autogenerate, which diffs the
*generated SQLAlchemy metadata* against the *live database* (`compare_type=True`). That
is the weakest possible pairing: a Dazzle type-mapping mismatch (a project's
hand-authored `text` PKs vs the DSL's `uuid`) or any schema drift both read as
"changes," producing a destructive whole-schema rewrite (alter PK types, drop live
columns/tables) — the #1427 footgun. #1427 shipped a guardrail (strip destructive ops),
but that is deliberately *dumb*: it can't generate legitimate renames or type changes.

The DSL is a structured, diffable source of truth. The engine diffs **DSL-vs-DSL** (the
committed schema snapshot vs the current AppSpec), so live-DB drift and type-mapping
noise can never produce spurious ops — a migration reflects exactly what changed *in the
spec*, intentionally.

## 2. Principle (the architecture in one line)

**We own the comparison; Alembic owns rendering + execution.** We replace Alembic's
autogenerate *comparison* (metadata-vs-DB) with our own (snapshot-vs-AppSpec) and render
the resulting semantic delta into Alembic op objects — reusing Alembic's op→SQL
rendering, migration-file authoring, version graph, and upgrade/downgrade execution.

### What is deliberately OUT of scope (confirmed in the code)
- **RLS policies** — idempotently reconciled from the AppSpec after every `db upgrade`
  (`db.py:_apply_rls_after_upgrade` → `dazzle.db.rls_apply.apply_rls_policies`, plus the
  standalone `dazzle db apply-rls` + `dazzle.db.rls_drift.detect_rls_drift`). RLS is
  **not versioned in migrations**, so scope-rule changes never enter the diff. Unchanged.
- **Enums** — stored as `TEXT` (`sa_schema.py:94`), so no native `CREATE TYPE` churn.
- **M2M** — modeled as explicit junction *entities* (ordinary tables); no hidden
  junction-table generation to diff.
- **PK-type canonicalization** — the snapshot diff removes the type-divergence *churn*
  (the engine never compares to the live DB), so canonicalization is no longer required.
  The genuine framework self-inconsistency (implicit `id` is `TEXT` in `pg_backend.py`
  but `Uuid` in `sa_schema.py`) is filed as its own issue (§9).

The engine's diff surface is therefore just the **relational schema**: tables (entities
±), columns (fields ± with type/nullable/length/default/unique), FK columns (refs),
indexes, and the implicit framework columns.

## 3. Components

### 3.1 Snapshot projection + storage
- A pure **relational-schema projection** of the AppSpec: per *project* entity →
  `{table, columns: {name → {type, nullable, length, default, unique, pk}}, fks: [...],
  indexes: [...]}`, deterministically ordered (sorted keys), excluding all UI/non-schema
  fields. This is a stable, diffable shape — NOT a raw `EntitySpec.model_dump` (which
  carries UI hints, validators, etc.).
- Emitted as a `SCHEMA_SNAPSHOT = {...}` constant embedded in each generated revision
  `.py` (the snapshot is atomic with the migration that produced it and travels through
  git with it).
- **"Previous schema"** = the resolved **project-lineage head** revision's
  `SCHEMA_SNAPSHOT`, loaded by importing/parsing that revision module. Framework
  entities are baseline-owned (the `version_locations` framework lineage) and are
  excluded from the projection. First project revision → previous is `{}` → full create.
- **Dual-lineage note:** the project versions dir (`_get_project_versions_dir`) is the
  lineage that carries `SCHEMA_SNAPSHOT`; the framework lineage does not. A multi-head
  state (ADR dual-lineage) resolves to the project head for the snapshot.

### 3.2 Differ (pure)
- `diff(prev_snapshot: Snapshot, current: Snapshot) → SchemaDelta`.
- `SchemaDelta` = an ordered list of typed ops:
  `AddTable`, `DropTable`, `RenameTable`, `AddColumn`, `DropColumn`, `RenameColumn`,
  `AlterColumn{type|nullable|length|default}`, `AddForeignKey`, `DropForeignKey`,
  `AddIndex`, `DropIndex`, `AddUnique`, `DropUnique`.
- No DB, no Alembic — exhaustively unit-testable (mirrors the pure-mapper style of
  `apex_discovery.resolve_apex_redirect`).
- **Rename resolution** consumes the `was:` hints (§3.4): a field/entity carrying
  `renamed_from = old` whose `old` is present in `prev` and whose new name is absent →
  emit `Rename*` instead of `Drop`+`Add`. Ordering: renames and adds before drops;
  drops last (so a rename is never misread as drop-then-add).

### 3.3 Renderer
- `render(delta: SchemaDelta) → alembic.operations.ops.UpgradeOps`, with the downgrade as
  the exact inverse (`UpgradeOps.reverse()` where clean, else an explicit inverse for
  ops whose reverse needs the prior column definition — carried in the delta).
- Reuses the Alembic op classes, so `db revision` file-authoring and `db upgrade`
  execution are unchanged.
- Reuses the existing `dazzle.http.runtime.safe_casts.get_using_clause` for type alters
  (the `postgresql_using` injection already in `env.py`).
- Unsafe ops are rendered as the expand/contract scaffold (§3.5), not as a bare
  destructive op.

### 3.4 `was:` rename grammar
- Syntax: `field new_name <type> ... was: old_name` and `entity NewName "..." was: OldName`.
- Lexer shape in `src/dazzle/core/dsl_parser_impl/_lexical.py` (ADR-0024: no `re` in the
  parser; new lexical shapes go there). Parser mixin reads the `was:` clause.
- IR: `FieldSpec.renamed_from: str | None` and `EntitySpec.renamed_from: str | None`
  (optional, default `None`).
- **Transient + fail-loud lifecycle:**
  - `old` in `prev` snapshot, new name absent → perform the rename.
  - `old` NOT in `prev` but the new name IS present in `prev` → already-applied; treat as
    a no-op (the author may leave the hint briefly after the rename migration; idempotent).
  - Neither resolvable (dangling `was:` — typo, or `old` never existed) → **hard error**
    at `db revision` time, naming the entity/field and the unresolved `old` name.
- Grammar doc updated (`docs/reference/grammar.md`) and the drift test
  (`tests/unit/test_docs_drift.py`) accounts for the new clause.

### 3.5 Data-migration seam
- Every generated migration carries a clearly-marked, ordered block:
  `# === DATA MIGRATION (hand-author) ===` … `# === END DATA MIGRATION ===`, placed
  between structural phases.
- For **unsafe changes** — adding a `NOT NULL` column without a server default, or a type
  change needing a backfill — the renderer emits the **expand → migrate → contract**
  scaffold:
  1. add the column nullable (or add the new typed column),
  2. the marked data-migration stub (commented `op.execute(...)` example),
  3. finalize (`alter_column ... nullable=False`, or drop the old column).
- Generated migrations are **immutable once committed** — the author fills the stub once;
  the engine never regenerates an existing migration.

### 3.6 CLI wiring + verification
- `dazzle db revision` uses the snapshot-diff engine as the **generator**. Alembic
  autogenerate remains available behind a flag (e.g. `--legacy-autogenerate`), still under
  the #1427 additive guardrail, as an escape hatch.
- After generating, optionally run Alembic's metadata-vs-DB compare as a
  **verification-only check**: warn if the live DB will not reach the expected post-state
  (drift detector), but never use it to generate ops. This is the hybrid safety net.
- The #1427 additive-scoping guardrail stays wired for the legacy-autogenerate path; the
  new engine emits intentful ops directly and does not need it.

## 4. Data flow

```
DSL files ─► parse ─► AppSpec ─► relational projection ─► current Snapshot
                                                              │
project-lineage head revision.SCHEMA_SNAPSHOT ─► prev Snapshot │
                                                              ▼
                              differ(prev, current) ─► SchemaDelta
                                                              │
                                                  renderer ─► UpgradeOps/DowngradeOps
                                                              │
                          embed SCHEMA_SNAPSHOT(current) + write revision .py (Alembic)
                                                              │
                                   dazzle db upgrade (Alembic execution) ─► apply-rls (unchanged)
```

## 5. File structure

**New:**
- `src/dazzle/db/schema_snapshot.py` — the relational projection (`project_schema(appspec) → Snapshot`) + the embedded-snapshot read/write helpers (load from a revision module, render the `SCHEMA_SNAPSHOT` literal).
- `src/dazzle/db/schema_diff.py` — `SchemaDelta` types + the pure `diff(prev, current)`.
- `src/dazzle/db/schema_render.py` — `render(delta) → UpgradeOps` (+ inverse) incl. the expand/contract scaffold + data-seam emission.
- `tests/unit/test_schema_snapshot.py`, `tests/unit/test_schema_diff.py`, `tests/unit/test_schema_render.py`, `tests/integration/test_migration_engine_pg.py`.

**Modified:**
- `src/dazzle/cli/db.py` — `revision_command` routes through the engine; `--legacy-autogenerate` flag; post-generation verification check.
- `src/dazzle/core/dsl_parser_impl/_lexical.py` + the field/entity parser mixins — `was:` clause.
- `src/dazzle/http/specs/entity.py` (or the IR entity types) — `renamed_from` on field/entity specs.
- `docs/reference/grammar.md`, `tests/unit/test_docs_drift.py` — the `was:` clause.
- `src/dazzle/http/alembic/env.py` — the engine sets `process_revision_directives` to inject the rendered ops + embed the snapshot (or the revision template carries it); the #1427 guardrail stays for the legacy path.

## 6. Edge cases
- **First project revision** — no prior snapshot → full create of all project tables.
- **Empty diff** — no DSL schema change → no revision emitted (existing empty-suppression).
- **Framework vs project entities** — only project entities are projected/diffed; framework tables are baseline + their own lineage.
- **Implicit framework columns** (id, tenant_id, timestamps) — projected consistently (or consistently excluded) so they never appear as spurious adds/drops. Decision: **exclude** framework-injected implicit columns from the project projection (they're framework-owned and created by the framework baseline / `_init_db`); the engine diffs only author-declared columns. (Confirm during impl against how `sa_schema`/`pg_backend` inject them.)
- **Dual-lineage multi-head** — resolve the project-lineage head for the snapshot; error clearly if the project head is ambiguous (mirror the existing `_guard_single_head` behavior).
- **Hand-edited / legacy migrations without `SCHEMA_SNAPSHOT`** — if the project head has no embedded snapshot (pre-engine migration), fall back to treating prev as unknown: either (a) require a one-time `dazzle db snapshot-baseline` to stamp the current AppSpec as the baseline snapshot, or (b) prev = current (emit nothing, stamp snapshot). Choose (a) — explicit baseline stamping — so the first engine revision after adoption is correct. Documented in the migration runbook.

## 7. Testing
- **Differ** (pure): exhaustive cases — add/drop/rename table; add/drop/rename column;
  alter type/nullable/length/default; FK/index/unique add/drop; rename via `was:`;
  dangling `was:` → error; already-applied `was:` → no-op; empty diff.
- **Renderer**: each `SchemaDelta` op → expected Alembic op; unsafe add/type → expand/
  contract scaffold with the data seam; downgrade is the exact inverse.
- **Snapshot projection**: deterministic/sorted; excludes UI fields + implicit columns;
  round-trips through the embedded literal.
- **End-to-end (PG)**: a fixture walking a *sequence* of DSL edits (add entity → add
  field → rename field → type change → drop field), asserting each `db revision` emits the
  intentful migration, **no spurious ops**, and applies + rolls back cleanly on real
  Postgres. This is the detector that the engine is non-destructive and intentful.

## 8. Phasing (for the plan)
1. **Snapshot projection + embed/load** — `schema_snapshot.py`; baseline-stamp command; embed in the revision template.
2. **Differ + SchemaDelta** — pure `schema_diff.py` + exhaustive unit tests.
3. **Renderer → Alembic ops** — `schema_render.py` (additive + drop + alter; downgrade inverse); wire `db revision` to the engine; e2e on add/drop/alter.
4. **`was:` grammar + rename resolution** — lexer/parser/IR + differ rename path + grammar doc/drift.
5. **Data-seam + expand/contract** — unsafe-change scaffold + marked seam.
6. **CLI polish + verification + full e2e** — `--legacy-autogenerate`, post-gen verification check, the sequence-walk PG test, runbook doc.

Phases 1–3 already deliver correct additive+drop+type migrations before renames/data-seam land.

## 9. Out of scope (filed separately)
- **PK-type canonicalization** + the implicit-id `TEXT` (`pg_backend.py`) vs `Uuid`
  (`sa_schema.py`) reconcile — a schema-philosophy decision with framework-wide blast
  radius (baseline + every example). Its own issue/brainstorm.

## 10. Model-driven failure-mode note (CLAUDE.md review rule)
- **Failure mode risked:** generated-code divergence (the migration not matching the DSL
  the engineer reads). Mitigated because the migration is rendered *from* the DSL diff —
  the snapshot makes "what the spec said at revision N" explicit and auditable.
- **Detector:** the end-to-end sequence-walk PG test (must be live) + the post-generation
  verification check that warns on DB/expected-state mismatch.
- **Traceability:** every migration op traces to a `SchemaDelta` entry, which traces to a
  DSL field/entity change between two embedded snapshots.
- **Semantics preserved:** RLS/auth/workflow untouched; this is purely the relational-DDL
  generation path.
