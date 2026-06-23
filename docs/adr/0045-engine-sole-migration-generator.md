# ADR-0045 — The snapshot-diff engine is the sole migration generator

**Status:** Accepted
**Builds on:** ADR-0017 (Alembic for all schema changes), ADR-0003 (clean breaks, no shims), #1431 (DSL-snapshot diff engine + `SCHEMA_SNAPSHOT`), #1427 (additive-only autogenerate scoping — *removed by this ADR*), #1460 (cyclic-FK hoist — *removed by this ADR*), #1390 (autostamp)
**Supersedes-in-part:** #1431's decision to keep the legacy autogenerate path for `db baseline` / `db migrate` / tenant / bare-alembic runs.

## Decision

The **#1431 DSL-snapshot diff engine is the one and only generator** of migration
operations across `dazzle db revision`, `dazzle db baseline`, and `dazzle db
migrate`. The legacy Alembic **metadata-vs-live-DB autogenerate** path — and
everything built to make it safe (the #1427 additive-only scoping and the #1460
cyclic-FK inline hoist) — is **deleted**, not flagged off.

> Every generated migration is the engine diffing **DSL-snapshot vs DSL-snapshot**
> (the head migration's embedded `SCHEMA_SNAPSHOT` vs the live DSL projection),
> never DSL-vs-live-database.

`db baseline` is the engine diffing against an empty prior snapshot, with
framework-owned tables excluded (they are created by the framework baseline
migration, ADR-0044) and the *full* post-state embedded as `SCHEMA_SNAPSHOT`. `db
migrate` is `db revision` + `db upgrade` in one step. `db revision` loses its
`--legacy-autogenerate` flag; `DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE` is gone.

## Why

The legacy path's *only* distinct capability was diffing against the live DB. It
added **no expressiveness** — both paths project the same `load_target_metadata()`
— and that metadata-vs-DB diff is exactly the destructive-churn source #1427 was
built to suppress (it "fixes" drift by dropping what it doesn't understand).
Keeping it meant maintaining a whole second generator *plus* the #1460 hoist (which
existed solely because Alembic autogenerate renders `use_alter` FKs inline, where
the `CreateTable` compiler silently drops them). The engine emits FKs — and, as of
this change, indexes and unique constraints — as **separate post-create ops**, so
cyclic/self-referential FKs and all constraints on new tables are correct by
construction; no hoist needed.

The two genuine needs the legacy path appeared to serve are met better elsewhere:

- **Schema the engine can't express** (triggers, extensions, partial indexes):
  hand-author a revision with `dazzle db revision --no-autogenerate` and write the
  `op.execute(...)` yourself — strictly more powerful than any autogenerator.
- **Live-DB drift detection**: a *verification* concern (`dazzle db verify` /
  `db status`), reconciled deliberately (`stamp` / `snapshot-baseline`), not
  silently auto-diffed.

## Correctness gate

Because op-tree unit tests are blind to "structurally-valid op-tree, wrong schema"
bugs (the class that hid #1460 *and* a latent drop of all FKs/indexes/uniques on
new tables), engine correctness is pinned by a **`create_all` parity oracle**
(`tests/integration/test_engine_baseline_parity_pg.py`, marker `migration_engine`):

> `db baseline` + `upgrade`, introspected on real Postgres  ≡  SQLAlchemy
> `create_all` of the same DSL — over project tables, name-insensitively — plus a
> round-trip property (`baseline → db revision → upgrade ≡ create_all(evolved DSL)`).

SQLAlchemy `create_all` is the trusted reference implementation of "DSL → schema".
Run the engine regression path with `pytest -m migration_engine`.

## Consequences

- **Behaviour change:** `dazzle db migrate` no longer reconciles live-DB drift via
  autogenerate; it generates the DSL-snapshot delta and applies it. `#1390`
  autostamp (align an empty `alembic_version` against a materialized schema before
  upgrade) is retained — it is an upgrade-time concern, independent of the generator.
- **Adoption:** a project whose head migration predates the engine (no
  `SCHEMA_SNAPSHOT`) must run `dazzle db snapshot-baseline` once before the next
  `db revision`/`db migrate` (unchanged; `snapshot-baseline` is kept for exactly
  this). A *fresh* `db baseline` no longer needs it — the engine baseline embeds
  the snapshot.
- **Bare `alembic revision --autogenerate`** (no dazzle Config) is unsupported: the
  directive hook suppresses the revision with a warning pointing at `dazzle db
  revision`.
- **Removed:** `src/dazzle/http/alembic/directive_scoping.py`,
  `_process_legacy_autogenerate` / `_legacy_scope_to_additive` in `env.py`, the
  `--legacy-autogenerate` flag, and `DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE`.
