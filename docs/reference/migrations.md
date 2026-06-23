# Schema Migrations

Dazzle uses [Alembic](https://alembic.sqlalchemy.org/) for all schema changes. This document covers the migration workflow for Dazzle app developers: how to generate, edit, and apply migrations as requirements evolve.

The worked examples here come from `examples/invoice_ops`, which was evolved through seven successive requirement changes (Changes 0–6) to exercise each migration pattern. The migration files are committed under `examples/invoice_ops/.dazzle/migrations/versions/`.

> **Policy reference**: [ADR-0017](../adr/0017-schema-migrations-via-alembic.md) — all schema changes, including framework entities, must go through Alembic. No raw DDL at startup.

---

## The model

**DSL is the source of truth.** When you add an entity or change a field in your `.dsl` files, Dazzle computes a migration script by comparing the new DSL schema against the last snapshot embedded in the head migration. You review and edit the script, then apply it.

`dazzle db` wraps the Alembic CLI. `dazzle serve` runs `alembic upgrade head` automatically at startup — pending migrations are applied before the app accepts requests.

### The #1431 DSL-snapshot migration engine

The **DSL-snapshot engine** is the **sole** migration generator (ADR-0045) — every migration `dazzle db revision`, `dazzle db baseline`, and `dazzle db migrate` produce comes from it. It replaced, and as of ADR-0045 fully **removed**, the legacy metadata-vs-live-DB autogenerate path (#1427) that was prone to destructive churn (spurious drops, unnamed-constraint noise).

**How it works:**

1. The engine reads the `SCHEMA_SNAPSHOT` constant embedded in the project's head migration — a plain Python dict encoding the previous DSL's table/column/FK/index shape.
2. It projects the current DSL through the same SQLAlchemy metadata builder used by Alembic, producing a new snapshot dict.
3. `diff(prev, curr)` computes a minimal ordered list of `SchemaOp` values (add table, drop column, rename column, etc.). With `was:` rename hints present (see below), renames are detected rather than emitted as drop+add.
4. `render(ops)` converts those ops to Alembic `UpgradeOps` / `DowngradeOps` op-trees.
5. The generated migration file carries the new snapshot as `SCHEMA_SNAPSHOT = <literal>` so the _next_ revision can diff against it.

Because the engine diffs snapshot-to-snapshot rather than schema-to-DB, it never produces the destructive whole-schema rewrite that schema-to-DB diffing emits when the DB has already applied the previous migration.

**All generation goes through the engine:**

- `dazzle db revision` — generate one migration from the DSL delta.
- `dazzle db baseline` — fresh-DB creation: the engine diffs against an empty prior snapshot (framework-owned tables excluded — they come from the framework baseline migration) and embeds the full `SCHEMA_SNAPSHOT`, so **a fresh baseline needs no follow-up `snapshot-baseline`**. FKs (including circular / self-referential) are emitted as separate `op.create_foreign_key(...)` ops.
- `dazzle db migrate` — `db revision` + `db upgrade` in one step (DSL-vs-snapshot, *not* metadata-vs-live-DB).
- Tenant schema migrations apply the engine-generated revision files, scoped to the tenant schema.

**Schema the engine can't express** (triggers, extensions, partial indexes): hand-author with `dazzle db revision --no-autogenerate` and write the `op.execute(...)` yourself. **Live-DB drift** is a verification concern — use `dazzle db verify` / `dazzle db status`, and reconcile with `stamp` / `snapshot-baseline`, not an auto-diff.

### Project-database resolution

`dazzle db` resolves the target database in this priority order:

1. `--database-url` flag (highest priority)
2. `DAZZLE_ENV` profile (if configured in `dazzle.toml`)
3. `DATABASE_URL` environment variable
4. `[database].url` in `dazzle.toml`
5. Default: `postgresql://localhost:5432/dazzle`

`dazzle db` also loads a `.env` file from the project root. The recommended pattern for local development is a gitignored `.env` at your project root:

```bash
# examples/invoice_ops/.env  (gitignored)
DATABASE_URL=postgresql://localhost/dazzle_invoice_ops
```

### First-time setup (two-step)

On a fresh database you must bootstrap in this order:

```bash
# Step 1 — apply the Dazzle framework baseline (creates _dazzle_params, etc.)
dazzle db upgrade

# Step 2 — generate the project baseline migration from your current DSL
dazzle db baseline

# Step 3 — apply the project baseline
dazzle db upgrade
```

`dazzle db upgrade` alone (Step 1) applies `0001_framework_baseline` — the framework's own schema. `dazzle db baseline` (Step 2) then projects your DSL and writes a migration (via the engine) that creates all your DSL-declared tables, revising from the framework baseline, **with an embedded `SCHEMA_SNAPSHOT`** so the next `db revision` diffs against it (no `snapshot-baseline` needed). Step 3 applies it. After this setup, subsequent changes follow the normal `revision → review → upgrade` loop.

### Normal change loop (engine path)

```bash
# 1. Edit your DSL (add field, rename, split entity, etc.)
# 2. Generate a migration (engine default)
dazzle db revision -m "describe the change"

# 3. Review the generated file — see patterns below
# 4. Apply
dazzle db upgrade

# 5. Commit both the DSL change and the migration file
```

No manual noise-stripping required with the engine path — the `_dazzle_params` drop and unnamed-constraint churn that plagued the legacy autogenerate path are not emitted.

---

## The `was:` rename clause

When you rename a DSL field or entity, annotate the new name with `was: OldName`. The engine reads this hint and generates a SQL `RENAME` operation rather than a destructive drop+add pair — the existing column data is preserved.

### Field rename

```dsl
entity Invoice "Invoice":
  id: uuid pk
  reference_number: str(50) required was: invoice_number
  # ^ was: tells the engine: rename the DB column "invoice_number" → "reference_number"
```

The `was:` clause goes at the end of the field line, after all modifiers.

Generated migration (upgrade):

```python
def upgrade() -> None:
    with op.batch_alter_table("Invoice") as batch_op:
        batch_op.alter_column("invoice_number", new_column_name="reference_number")
```

### Entity rename

For an entity-level rename, add `was: OldName` as a body keyword inside the entity block:

```dsl
entity PurchaseOrder "Purchase Order":
  was: Invoice
  id: uuid pk
  amount: money required
```

The engine generates `op.rename_table("Invoice", "PurchaseOrder")` in the upgrade.

### Lifecycle of `was:`

`was:` is **transient**: it is consumed during the revision that performs the rename. After `dazzle db revision` and `dazzle db upgrade` have run, remove the `was:` annotation from the DSL. Leaving it in permanently is harmless on a clean history (the engine detects the already-applied case — the old name is absent from the prev snapshot and the new name is already present), but it makes the DSL harder to read and will produce a `RenameResolutionError` on a fresh clone if the old name appears in a snapshot from before the rename was applied.

**Dangling `was:` is a hard error at diff time** (`RenameResolutionError`): if the hint names an old column/table that is neither in the previous snapshot (meaning it was never applied) nor already absent with the new name present (already-applied), the engine raises immediately with a clear message identifying the field and the unresolvable old name.

`was` is a reserved keyword in the DSL lexer — you cannot use it as a field or entity name.

---

## Unsafe changes and the data-migration seam

Some schema changes cannot be applied directly to a populated table. The engine detects two cases and scaffolds an explicit seam for you to fill in.

### Case 1: NOT NULL column with no default

Adding a `required` field with no default to an entity that already has rows would fail at the DB level — PostgreSQL has no value to put in the existing rows.

The engine generates an **expand → seam → contract** scaffold:

```python
def upgrade() -> None:
    # Expand: add the column NULLABLE first (non-blocking)
    with op.batch_alter_table("LineItem") as batch_op:
        batch_op.add_column(sa.Column("cost_centre", sa.Text(), nullable=True))

    # === DATA MIGRATION (hand-author) ===
    # Backfill / transform existing rows here BEFORE the column is
    # finalized NOT NULL or the type cast runs. Replace the example.
    # op.execute("UPDATE my_table SET my_col = ... WHERE my_col IS NULL")
    # === END DATA MIGRATION ===

    # Contract: finalize NOT NULL
    with op.batch_alter_table("LineItem") as batch_op:
        batch_op.alter_column("cost_centre", existing_type=sa.Text(), nullable=False)
```

Fill in the `op.execute(...)` stub between the seam markers with a real backfill statement before applying the migration. Do not remove the seam markers until the backfill is complete and tested.

### Case 2: type change requiring an explicit cast

When you change a column's DSL type (e.g. from `str` to `int`) and the engine does not have a known-safe automatic cast for that pair, it emits a seam before the `ALTER COLUMN TYPE` so you can prepare the data:

```python
def upgrade() -> None:
    # === DATA MIGRATION (hand-author) ===
    # Backfill / transform existing rows here BEFORE the column is
    # finalized NOT NULL or the type cast runs. Replace the example.
    # op.execute("UPDATE my_table SET my_col = ... WHERE my_col IS NULL")
    # === END DATA MIGRATION ===

    with op.batch_alter_table("Product") as batch_op:
        batch_op.alter_column("quantity",
            existing_type=sa.Text(), modify_type=sa.Integer())
```

### Known-safe automatic casts

For the type pairs in the table below, the engine emits a raw `ALTER COLUMN ... TYPE ... USING <cast>` statement automatically — no seam, no manual work:

| From DSL type | To DSL type | USING expression |
|---|---|---|
| `str` | `uuid` | `"col"::uuid` |
| `str` | `date` | `"col"::date` |
| `str` | `datetime` | `"col"::timestamptz` |
| `str` | `json` | `"col"::jsonb` |
| `str` | `bool` | `"col"::boolean` |
| `str` | `int` | `"col"::integer` |
| `float` → `decimal` | (widening) | no `USING` needed |
| `varchar` → `str` | (widening) | no `USING` needed |

Any pair not in this table gets a seam.

> **The engine emits type changes as raw `ExecuteSQLOp` statements**, so the `USING` cast is serialized into the revision file verbatim. Any pair not in the safe-cast table above gets an expand→seam→contract scaffold to hand-fill.

---

## Hand-authored migrations (engine-inexpressible schema)

The engine projects the DSL through SQLAlchemy metadata, so it can only express what that metadata captures. For schema beyond it — triggers, `CREATE EXTENSION`, partial/expression indexes, raw DDL — hand-author the revision:

```bash
dazzle db revision -m "add fuzzy-search trigger" --no-autogenerate
# then edit the generated file: op.execute("CREATE TRIGGER ...")
```

This is strictly more powerful than any autogenerator. (There is no metadata-vs-live-DB fallback flag — that path was removed in ADR-0045; both paths shared the same metadata projection, so it added no expressiveness.)

---

## Adoption: `dazzle db snapshot-baseline`

If your project's head migration predates the engine (no `SCHEMA_SNAPSHOT` constant), run this **once** before the next `dazzle db revision`:

```bash
# Write an empty revision that stamps the current DSL as the baseline snapshot
dazzle db snapshot-baseline

# Apply it (no-op upgrade — the revision has an empty upgrade body)
dazzle db upgrade

# Subsequent revisions now diff correctly against the snapshot
dazzle db revision -m "add field"
```

The command is **idempotent**: if the head migration already carries `SCHEMA_SNAPSHOT`, it prints a message and exits without writing a file.

What `snapshot-baseline` does:

1. Projects the current DSL schema into a snapshot dict.
2. Writes a revision file with `def upgrade(): pass` / `def downgrade(): pass`.
3. Post-writes `SCHEMA_SNAPSHOT = <literal>` into the file (the same injection path used by `db revision`).

After `dazzle db upgrade` applies this no-op revision, the next `dazzle db revision` diffs the live DSL against the stamped snapshot and emits only the intentful delta.

---

## Worked runbooks

### Standard change: add a field

```bash
# 1. Add the field to your DSL
#    e.g. add  priority: int=0  to entity Task

# 2. Generate the migration
dazzle db revision -m "add priority to Task"

# 3. Review the generated file in .dazzle/migrations/versions/
#    The engine emits an AddColumn op — no noise to strip.
#    For a nullable/default field this is complete; apply it.

# 4. Apply
dazzle db upgrade

# 5. Commit both the DSL change and the migration file
```

### Rename: field or entity

```bash
# 1. Annotate the DSL with was:
#    Change:  title: str(200) required
#    To:      name: str(200) required was: title

# 2. Generate the migration
dazzle db revision -m "rename title to name on Task"

# 3. Review — expect a RenameColumn op (ALTER COLUMN ... RENAME TO ...).
#    No data loss. Downgrade is the reverse rename.

# 4. Apply
dazzle db upgrade

# 5. Commit. Then remove the `was: title` annotation from the DSL and commit again.
```

### Unsafe change: NOT NULL column with backfill

```bash
# 1. Add the required field to DSL:
#    region: str(50) required

# 2. Generate the migration
dazzle db revision -m "add required region to Task"

# 3. Review the generated file. It will contain:
#    - op.add_column (NULLABLE)
#    - # === DATA MIGRATION (hand-author) === ... # === END DATA MIGRATION ===
#    - op.alter_column(nullable=False)

# 4. Fill in the data-migration block:
#    op.execute("UPDATE \"Task\" SET region = 'default' WHERE region IS NULL")

# 5. Apply
dazzle db upgrade

# 6. Commit
```

### Adopting the engine on an existing project

```bash
# Run once to stamp the current DSL as the snapshot baseline
dazzle db snapshot-baseline

# Apply the no-op stamp revision
dazzle db upgrade

# Commit the snapshot-baseline revision file
git add .dazzle/migrations/versions/
git commit -m "stamp snapshot-baseline for #1431 engine"

# From now on, db revision uses the engine
dazzle db revision -m "next change"
```

---

## Committing your migrations

Migration files are the schema-evolution record for your project. They must be version-controlled alongside your DSL.

The `.dazzle/` directory is gitignored repo-wide (it contains generated state, caches, and lock files). A project un-ignores its `migrations/versions/` subtree with a negation block. The `examples/invoice_ops` project demonstrates the pattern — see the repo `.gitignore`:

```gitignore
# invoice_ops commits its migration history — a project's migrations
# are the schema-evolution record and must be version-controlled.
!examples/invoice_ops/.dazzle/
examples/invoice_ops/.dazzle/*
!examples/invoice_ops/.dazzle/migrations/
examples/invoice_ops/.dazzle/migrations/*
!examples/invoice_ops/.dazzle/migrations/versions/
!examples/invoice_ops/.dazzle/migrations/versions/**
examples/invoice_ops/.dazzle/migrations/versions/**/__pycache__/
examples/invoice_ops/.dazzle/migrations/versions/**/*.pyc
```

For your own project, add an equivalent block to the repo `.gitignore` (or to a project-level `.gitignore` if your project is in a standalone repo):

```gitignore
# Commit migration history but not generated state
!<your_project>/.dazzle/
<your_project>/.dazzle/*
!<your_project>/.dazzle/migrations/
<your_project>/.dazzle/migrations/*
!<your_project>/.dazzle/migrations/versions/
!<your_project>/.dazzle/migrations/versions/**
<your_project>/.dazzle/migrations/versions/**/__pycache__/
<your_project>/.dazzle/migrations/versions/**/*.pyc
```

---

## Pattern: additive field

**DSL change:** add a new optional field to an existing entity.

**Engine result:** correct — emits a single `op.add_column`, no noise to strip.

**Worked example:** `2026_05_21_08934671d5d5_add_po_number_to_invoice.py` (Change 1)

```python
def upgrade() -> None:
    # Hand-edited: stripped spurious _dazzle_params drop and unnamed
    # unique-constraint ops emitted by autogenerate. Column type kept as
    # sa.Text() — Dazzle maps str/str(N) to TEXT (http/runtime/sa_schema.py);
    # the (40) length is an application-layer concern, not a DB column type.
    op.add_column("Invoice", sa.Column("po_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("Invoice", "po_number")
```

**Note on types:** `str`, `str(N)`, and `enum[...]` in DSL all map to `sa.Text()` at the database layer (`src/dazzle/http/runtime/sa_schema.py`). The `(N)` length limit and the enum value list are application-layer constraints enforced by Dazzle, not PostgreSQL column types. Migrations always show `sa.Text()` for string columns — that is correct and expected.

---

## Pattern: field rename

**DSL change:** rename a field on an existing entity.

**Engine result:** add a `was:` clause — the engine detects the rename and emits a safe `op.alter_column(..., new_column_name=...)` automatically (preserving data), instead of a data-destroying drop+add. See the `was:` section above.

**Worked example:** `2026_05_21_e3c4b12a8018_rename_supplier_bank_reference_to_bank_.py` (Change 2)

```python
def upgrade() -> None:
    op.alter_column("Supplier", "bank_reference", new_column_name="bank_account_ref")


def downgrade() -> None:
    op.alter_column("Supplier", "bank_account_ref", new_column_name="bank_reference")
```

---

## Pattern: enum evolution

**DSL change:** add a new value to an existing `enum[...]` field.

**Result:** nothing substantive — `enum[...]` maps to `TEXT` with app-layer value enforcement, so the migration body is empty.

**Worked example:** `2026_05_21_7cf317f60a5f_add_partially_paid_to_invoice_status.py` (Change 3)

```python
def upgrade() -> None:
    # Enum evolution — no-op: Invoice.status is unconstrained TEXT in PostgreSQL.
    # Dazzle maps DSL enum fields to sa.Text() with no CHECK constraint, so adding
    # 'partially_paid' to the enum values list requires no DDL change.
    pass


def downgrade() -> None:
    # Enum evolution — no-op: see upgrade() comment.
    pass
```

**Trade-off:** because Dazzle enums are stored as unconstrained `TEXT`, adding (or removing) an enum value requires no DB migration. The downside is that PostgreSQL will accept any string in that column — enum validity is enforced only at the Dazzle application layer, not at the DB layer.

---

## Pattern: entity split and data backfill

**DSL change:** extract fields from an existing entity into a new entity (entity split), where existing rows must have their data migrated to the new table before the old columns are dropped.

**Engine result:** generates the expand scaffold with a seam marker. You fill in the backfill SQL.

**Worked example:** `2026_05_21_7b4f5f16a753_split_supplierbankaccount_out_of_.py` (Change 4)

The hand-edited migration uses a strict three-step ordering: create the new table, backfill from the old column, then drop the old column. Reversing steps 2 and 3 loses data.

```python
def upgrade() -> None:
    op.create_table(
        "SupplierBankAccount",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier", sa.Uuid(), nullable=False),
        sa.Column("bank_account_ref", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("iban", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["supplier"], ["Supplier.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["Tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
    )
    # Backfill: one bank-account row per existing supplier, BEFORE dropping the column.
    op.execute(
        """
        INSERT INTO "SupplierBankAccount"
            (id, tenant_id, supplier, bank_account_ref, account_name, created_at, updated_at)
        SELECT gen_random_uuid(), tenant_id, id, bank_account_ref, name, now(), now()
        FROM "Supplier"
        WHERE bank_account_ref IS NOT NULL
        """
    )
    op.drop_column("Supplier", "bank_account_ref")


def downgrade() -> None:
    op.add_column("Supplier", sa.Column("bank_account_ref", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE "Supplier" s
        SET bank_account_ref = sba.bank_account_ref
        FROM "SupplierBankAccount" sba
        WHERE sba.supplier = s.id
        """
    )
    op.alter_column("Supplier", "bank_account_ref", nullable=False)
    op.drop_table("SupplierBankAccount")
```

**Rule:** the ordering in `upgrade()` is non-negotiable — create first, backfill second, drop third. Use `op.execute` with a raw SQL `INSERT ... SELECT` for the backfill. `gen_random_uuid()` is available on PostgreSQL 13+.

---

## Pattern: event-schema change

**DSL change:** modify an `event_model` block — change retention, add or rename an event field, add an event type.

**Result:** empty — event-schema changes carry no app-DB table change.

**Worked example:** `2026_05_21_321d3b7c99d8_invoice_events_retention_.py` (Change 5)

```python
def upgrade() -> None:
    # event_model is runtime-only — no DDL produced
    pass


def downgrade() -> None:
    # event_model is runtime-only — no DDL produced
    pass
```

The `event_model` construct is runtime-only. Events are not backed by PostgreSQL tables — no DDL change is needed when the event schema changes.

**Gap: no event-schema versioning in `event_model`.** Unlike the `hless` construct (which has `version` and `compatibility` fields — `ADDITIVE`/`BREAKING` — in its IR), the simpler `event_model` DSL has no event-versioning mechanism: no version tag, no schema registry, no upcaster. Adding a required field to an event is a silent breaking change for existing consumers reading stored events that pre-date the new field. If your application stores and replays events from `event_model` topics and needs schema evolution with backward compatibility, use `hless` instead, which was designed for that requirement.

---

## Pattern: changes that need no migration

Some DSL changes have no schema impact at all. The generated migration is an intentional empty `pass`.

**Worked example:** `2026_05_21_f43cc3604cf7_add_finance_admin_persona.py` (Change 6 — RBAC change)

```python
def upgrade() -> None:
    # RBAC-only change — no schema impact
    pass


def downgrade() -> None:
    # RBAC-only change — no schema impact
    pass
```

Changes in this category:

| DSL change | Why no migration |
|---|---|
| `permit:` / `forbid:` rules | Compile to query filters, not schema |
| `scope:` / `as:` clauses | Compile to SQL predicates, not columns |
| Adding or removing a persona | Personas are DSL-level roles, not tables |
| Changing a story or rhythm | Test/specification metadata, no DB backing |
| Changing `event_model` retention or event fields | Runtime-only (see above) |
| Adding a `schedule` or `webhook` | Resolved at startup from DSL, no new tables |

Even when the migration is an empty pass, generating and committing it is still the right practice — it keeps the revision chain intact and documents that you considered the schema impact and found none.

---

## Out of scope and known limitations

The following are explicitly not handled by the #1431 engine:

**RLS (Row Level Security):** RLS policies are reconciled separately. `dazzle db upgrade` applies RLS automatically after a successful migration in `shared_schema` tenancy mode, or you can run `dazzle db apply-rls` independently. RLS is not part of the `SCHEMA_SNAPSHOT` diff.

**Composite UNIQUE constraints:** the engine's unique-constraint tracking is per-column (single-column uniques). Multi-column `UNIQUE(a, b)` constraints are flattened to per-column entries in the snapshot. A true composite unique constraint declared in the DSL would be tracked as two single-column uniques, not as the joint constraint. File a revision by hand if you need multi-column uniqueness.

**PK type canonicalization:** primary-key type changes (e.g. `int` → `uuid`) are tracked as `AlterColumn` ops but the FK cascade to referencing tables is not auto-resolved. Tracked in #1432.

**Index column order:** the snapshot stores index keys as sorted comma-joined column names, so `(tenant_id, status)` and `(status, tenant_id)` produce the same key. Index column-order changes are not detected.

**`was:` lifecycle validation at lint time:** the engine detects a dangling `was:` at diff time (when `db revision` runs) via `RenameResolutionError`. There is no `dazzle lint` gate that checks for stale `was:` clauses in the DSL before that point.

---

## Rollback and safety

### Downgrade

```bash
# Step back one revision (default behaviour)
dazzle db downgrade

# Step back to a specific revision
dazzle db downgrade <revision_id>

# Step back N steps
dazzle db downgrade -2
```

Note: the target revision is a positional argument. `dazzle db downgrade` with no arguments steps back one revision. Passing a negative integer like `-1` as a flag (e.g. `dazzle db downgrade --target -1`) does not work — use the positional form.

### Verify ref integrity

After applying a migration that creates or drops FK relationships — or as a periodic audit of a long-lived database — verify the database state against the DSL:

```bash
dazzle db verify            # human-readable report; non-zero exit on findings
dazzle db verify --json     # machine-readable, for CI/cron gating
```

Refs compile to **soft (un-constrained) columns** by design, and `required` + invariants are enforced at the app layer only — so out-of-convention writes (manual SQL, sweeps, old bugs) can violate what the DSL declares without the database objecting. `verify` is the DSL-derived audit (#1364):

- **Orphans** — ref columns pointing at a missing parent row.
- **Required-ref NULLs** — `ref X required` columns containing NULL.
- **Unanchored rows** — entities declaring an at-least-one-anchor invariant (`invariant: case_ref != null or matter_ref != null`) where every anchor is NULL. Only that statically translatable invariant shape is checked; other invariants remain app-write-time contracts.

To remove the bad rows:

```bash
dazzle db cleanup --dry-run               # preview the orphan sweep
dazzle db cleanup                          # iterative, children-aware orphan deletion
dazzle db cleanup --unanchored --dry-run   # also preview unanchored-row deletions (#1364)
```

The `--unanchored` sweep is opt-in: unlike orphans (rows pointing at nothing), unanchored rows may be mid-flow data a user still intends to anchor. Deleting unanchored rows can orphan *their* children — the sweep runs inside the same iterative loop, so the next pass reaps them.

### Snapshot and restore

Before applying a risky migration (entity split, column drop, large backfill), take a snapshot of the current database:

```bash
dazzle db snapshot              # capture current state
# ... apply migration ...
dazzle db restore               # roll back to snapshot if something goes wrong
```

Use snapshots as a development safety net. In production, rely on your database provider's point-in-time recovery (PITR) — Heroku Postgres, RDS, and similar services support this natively.

### Safe migration checklist

Before applying any migration that drops or renames columns or tables:

1. **Back up or snapshot first** — especially in production.
2. **Use the engine path with `was:`** for renames (avoids drop+add entirely).
3. **Fill in the data-migration seam** for any NOT NULL add — never apply it with an empty stub.
4. **Test the downgrade path** — run `dazzle db downgrade` and `dazzle db upgrade` on a copy of the database before touching production.
5. **Commit the migration file** — before deploying, confirm the migration is committed and pushed.
