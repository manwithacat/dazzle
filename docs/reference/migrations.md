# Schema Migrations

Dazzle uses [Alembic](https://alembic.sqlalchemy.org/) for all schema changes. This document covers the migration workflow for Dazzle app developers: how to generate, edit, and apply migrations as requirements evolve.

The worked examples here come from `examples/invoice_ops`, which was evolved through seven successive requirement changes (Changes 0–6) to exercise each migration pattern. The migration files are committed under `examples/invoice_ops/.dazzle/migrations/versions/`.

> **Policy reference**: [ADR-0017](../adr/0017-schema-migrations-via-alembic.md) — all schema changes, including framework entities, must go through Alembic. No raw DDL at startup.

---

## The model

**DSL is the source of truth.** When you add an entity or change a field in your `.dsl` files, Alembic compares the DSL-derived SQLAlchemy metadata against the live database and generates a migration script. You review and edit the script, then apply it.

`dazzle db` wraps the Alembic CLI. `dazzle serve` runs `alembic upgrade head` automatically at startup — pending migrations are applied before the app accepts requests.

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

`dazzle db upgrade` alone (Step 1) applies `0001_framework_baseline` — the framework's own schema. `dazzle db baseline` (Step 2) then introspects your DSL and writes a migration that creates all your DSL-declared tables, revising from `0001_framework_baseline`. Step 3 applies it. After this two-step setup, subsequent changes follow the normal `revision → review → upgrade` loop.

### Normal change loop

```bash
# 1. Edit your DSL (add field, rename, split entity, etc.)
# 2. Generate a migration
dazzle db revision -m "describe the change"

# 3. Review and hand-edit the generated file (see patterns below)
# 4. Apply
dazzle db upgrade

# 5. Commit the migration file (see "Committing migrations" below)
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

## Autogenerate noise to expect

Every `dazzle db revision` (autogenerate) emits two categories of spurious operations that must be stripped by hand before applying the migration.

### 1. `op.drop_table('_dazzle_params')`

`_dazzle_params` is a framework-internal table owned by `0001_framework_baseline`. Because `build_metadata()` only includes DSL-declared entities, Alembic thinks the table is absent from the target schema and emits a drop. It is not — do not drop it.

The baseline migration (`5c144ea092ef_baseline_create_all_tables.py`) shows the comment that should accompany the strip:

```python
# NOTE: _dazzle_params is a framework table owned by 0001_framework_baseline.
# Autogenerate incorrectly flags it as "removed" because build_metadata only
# includes DSL-declared entities. Do NOT drop it here.
```

### 2. Unnamed unique-constraint re-emissions on `id` columns

Alembic cannot reconcile unnamed unique constraints (`UniqueConstraint(None, ...)`) that were created by `create_all()` on `id` columns. It re-emits `op.create_unique_constraint(None, ...)` on every table in every autogenerated migration. Strip these — they are no-ops that will fail at runtime if not removed.

**Rule:** after `dazzle db revision`, always scroll to the bottom of the generated file and remove any `op.drop_table('_dazzle_params')` and any `op.create_unique_constraint(None, ...)` lines before reviewing the substantive change.

---

## Pattern: additive field

**DSL change:** add a new optional field to an existing entity.

**Autogenerate result:** correct — emits `op.add_column`. Strip the noise, no other edits needed.

**Worked example:** `2026_05_21_08934671d5d5_add_po_number_to_invoice.py` (Change 1)

```python
def upgrade() -> None:
    # Hand-edited: stripped spurious _dazzle_params drop and unnamed
    # unique-constraint ops emitted by autogenerate. Column type kept as
    # sa.Text() — Dazzle maps str/str(N) to TEXT (back/runtime/sa_schema.py);
    # the (40) length is an application-layer concern, not a DB column type.
    op.add_column("Invoice", sa.Column("po_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("Invoice", "po_number")
```

**Note on types:** `str`, `str(N)`, and `enum[...]` in DSL all map to `sa.Text()` at the database layer (`src/dazzle/back/runtime/sa_schema.py`). The `(N)` length limit and the enum value list are application-layer constraints enforced by Dazzle, not PostgreSQL column types. Migrations always show `sa.Text()` for string columns — that is correct and expected.

---

## Pattern: field rename

**DSL change:** rename a field on an existing entity.

**Autogenerate result:** WRONG — autogenerate cannot detect renames. It emits `op.drop_column` followed by `op.add_column`, which destroys the existing data in that column.

**Worked example:** `2026_05_21_e3c4b12a8018_rename_supplier_bank_reference_to_bank_.py` (Change 2)

What autogenerate produces (data-destroying — do not apply):

```python
# DO NOT USE — this destroys data
def upgrade() -> None:
    op.drop_column("Supplier", "bank_reference")
    op.add_column("Supplier", sa.Column("bank_account_ref", sa.Text(), nullable=False))
```

The hand-edited migration that preserves data:

```python
def upgrade() -> None:
    op.alter_column("Supplier", "bank_reference", new_column_name="bank_account_ref")


def downgrade() -> None:
    op.alter_column("Supplier", "bank_account_ref", new_column_name="bank_reference")
```

**Rule:** whenever you rename a DSL field, discard the autogenerated drop/add pair and replace it with a single `op.alter_column(..., new_column_name=...)` call.

---

## Pattern: enum evolution

**DSL change:** add a new value to an existing `enum[...]` field.

**Autogenerate result:** nothing substantive — after stripping the standard noise, the migration body is empty.

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

**Autogenerate result:** partially correct — emits `op.create_table` and `op.drop_column`, but with no backfill step. Applying it as-is loses the data that was in the dropped column.

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

**Autogenerate result:** empty (after stripping noise).

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

Before applying any destructive migration (rename, drop, split):

1. **Back up or snapshot first** — especially in production.
2. **Review the autogenerate output** — do not apply raw autogenerate on rename or split; hand-edit first.
3. **Strip noise** — remove `op.drop_table('_dazzle_params')` and any unnamed unique-constraint ops.
4. **Test the downgrade path** — run `dazzle db downgrade` and `dazzle db upgrade` on a copy of the database before touching production.
5. **Commit the migration file** — before deploying, confirm the migration is committed and pushed.
