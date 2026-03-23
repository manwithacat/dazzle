# Alembic Migration System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled `MigrationPlanner` with Alembic-based migrations, adding safe type casting, empty revision suppression, and user-friendly CLI commands.

**Architecture:** Alembic is already scaffolded (`src/dazzle_back/alembic/env.py`, `alembic.ini`, CLI commands). The work is: (1) add safe-cast registry, (2) enhance `env.py` with `compare_type=True`, `process_revision_directives` (suppress empties + inject USING clauses), (3) add `dazzle db migrate`/`rollback` commands, (4) replace `auto_migrate()` with Alembic in server startup + production guard, (5) retire ~400 lines of hand-rolled code.

**Tech Stack:** Python 3.12, Alembic >= 1.13, SQLAlchemy >= 2.0, Typer CLI

**Spec:** `docs/superpowers/specs/2026-03-23-alembic-migrations-design.md`

**Deviations from spec (deliberate):**
- Spec says create `src/dazzle_back/runtime/alembic_env.py` — we modify the existing `src/dazzle_back/alembic/env.py` instead (already scaffolded)
- Spec says `SAFE_CASTS` in `migrations.py` — we create a separate `safe_casts.py` (cleaner separation)
- Spec says no `alembic.ini` — we keep it (already exists, simpler than programmatic config)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/safe_casts.py` | Create | SAFE_CASTS registry, lookup, validation |
| `src/dazzle_back/alembic/env.py` | Modify | Add `compare_type=True`, `process_revision_directives` hook |
| `src/dazzle/cli/db.py` | Modify | Add `migrate`, `rollback` wrapper commands |
| `src/dazzle_back/runtime/server.py` | Modify | Replace `auto_migrate()` with Alembic upgrade |
| `src/dazzle/cli/runtime_impl/serve.py` | Modify | Add production guard for pending migrations |
| `src/dazzle_back/runtime/migrations.py` | Modify | Retire MigrationPlanner/Executor/History |
| `src/dazzle_back/__init__.py` | Modify | Remove `auto_migrate`/`plan_migrations` exports |
| `tests/unit/test_safe_casts.py` | Create | Test safe cast registry |
| `tests/unit/test_circular_fk_migration.py` | Delete | Tests for retired MigrationPlanner |
| `pyproject.toml` | Modify | Add `alembic>=1.13` to dependencies |
| `CHANGELOG.md` | Modify | Document changes |

---

### Task 1: Add alembic dependency and safe cast registry

**Files:**
- Create: `src/dazzle_back/runtime/safe_casts.py`
- Create: `tests/unit/test_safe_casts.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add alembic to pyproject.toml dependencies**

In `pyproject.toml`, find the `dependencies` list and add `"alembic>=1.13"` if not already present. Check first:

```bash
grep "alembic" pyproject.toml
```

If missing, add it to the dependencies list.

- [ ] **Step 2: Write failing tests for safe cast registry**

Create `tests/unit/test_safe_casts.py`:

```python
"""Tests for the safe cast registry."""

from __future__ import annotations

import pytest

from dazzle_back.runtime.safe_casts import SAFE_CASTS, get_using_clause, is_safe_cast


class TestSafeCastRegistry:
    def test_text_to_uuid_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "UUID")

    def test_text_to_timestamptz_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "TIMESTAMPTZ")

    def test_text_to_date_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "DATE")

    def test_text_to_jsonb_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "JSONB")

    def test_text_to_boolean_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "BOOLEAN")

    def test_text_to_integer_is_safe(self) -> None:
        assert is_safe_cast("TEXT", "INTEGER")

    def test_double_to_numeric_is_safe(self) -> None:
        assert is_safe_cast("DOUBLE PRECISION", "NUMERIC")

    def test_uuid_to_text_is_not_safe(self) -> None:
        assert not is_safe_cast("UUID", "TEXT")

    def test_integer_to_boolean_is_not_safe(self) -> None:
        assert not is_safe_cast("INTEGER", "BOOLEAN")

    def test_case_insensitive(self) -> None:
        assert is_safe_cast("text", "uuid")


class TestGetUsingClause:
    def test_text_to_uuid_clause(self) -> None:
        clause = get_using_clause("TEXT", "UUID", "my_col")
        assert clause == '"my_col"::uuid'

    def test_text_to_timestamptz_clause(self) -> None:
        clause = get_using_clause("TEXT", "TIMESTAMPTZ", "created_at")
        assert clause == '"created_at"::timestamptz'

    def test_double_to_numeric_has_no_clause(self) -> None:
        clause = get_using_clause("DOUBLE PRECISION", "NUMERIC", "amount")
        assert clause is None

    def test_unknown_cast_returns_none(self) -> None:
        clause = get_using_clause("UUID", "TEXT", "id")
        assert clause is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_safe_casts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement safe_casts.py**

Create `src/dazzle_back/runtime/safe_casts.py`:

```python
"""Safe cast registry for Alembic type change migrations.

Maps (from_pg_type, to_pg_type) to USING clause templates. Casts in this
registry are known to be lossless and can be applied automatically during
auto-migration. Unknown casts are skipped with a warning.
"""

from __future__ import annotations

from dazzle_back.runtime.query_builder import quote_identifier

# (from_type, to_type) → USING template or "" for no-op widening.
# Types are uppercase Postgres type names as returned by information_schema.
SAFE_CASTS: dict[tuple[str, str], str] = {
    ("TEXT", "UUID"): "{col}::uuid",
    ("TEXT", "DATE"): "{col}::date",
    ("TEXT", "TIMESTAMPTZ"): "{col}::timestamptz",
    ("TEXT", "JSONB"): "{col}::jsonb",
    ("TEXT", "BOOLEAN"): "{col}::boolean",
    ("TEXT", "INTEGER"): "{col}::integer",
    ("DOUBLE PRECISION", "NUMERIC"): "",
    ("CHARACTER VARYING", "TEXT"): "",
}


def is_safe_cast(from_type: str, to_type: str) -> bool:
    """Return True if converting from_type to to_type is known-safe."""
    return (from_type.upper(), to_type.upper()) in SAFE_CASTS


def get_using_clause(from_type: str, to_type: str, column_name: str) -> str | None:
    """Return the USING clause for a safe cast, or None if not safe/needed.

    Returns None for unknown casts and for no-op widenings where USING
    is not needed. Returns a string like '"col"::uuid' for casts that
    require explicit USING.
    """
    template = SAFE_CASTS.get((from_type.upper(), to_type.upper()))
    if template is None:
        return None
    if not template:
        return None  # no-op widening
    return template.format(col=quote_identifier(column_name))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_safe_casts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/safe_casts.py tests/unit/test_safe_casts.py pyproject.toml
git commit -m "feat: add safe cast registry for Alembic type migrations (#625)"
```

---

### Task 2: Enhance Alembic env.py

**Files:**
- Modify: `src/dazzle_back/alembic/env.py`

This task adds three things to the existing Alembic environment:
1. `compare_type=True` to detect type changes
2. `process_revision_directives` hook to suppress empty migrations AND inject `postgresql_using` for safe casts
3. Schema support for tenant migrations

- [ ] **Step 1: Add imports and the process_revision_directives hook**

At the top of `env.py`, after the existing imports, add:

```python
from alembic.operations import ops as alembic_ops
```

Before `run_migrations_offline()`, add the hook function:

```python
def _process_revision_directives(context, revision, directives):
    """Post-process autogenerated migration directives.

    1. Suppress empty revisions (no-op when DSL hasn't changed).
    2. Inject postgresql_using clauses for safe type casts.
    """
    if not directives:
        return

    script = directives[0]
    if script.upgrade_ops is None:
        return

    # Suppress empty migrations
    if script.upgrade_ops.is_empty():
        directives[:] = []
        return

    # Inject USING clauses for safe type casts
    try:
        from dazzle_back.runtime.safe_casts import is_safe_cast, get_using_clause
    except ImportError:
        return

    for op in script.upgrade_ops.ops:
        if not isinstance(op, alembic_ops.ModifyTableOps):
            continue
        for sub_op in op.ops:
            if not isinstance(sub_op, alembic_ops.AlterColumnOp):
                continue
            if sub_op.modify_type is None or sub_op.existing_type is None:
                continue
            # Get Postgres type names from SA types
            from_name = sub_op.existing_type.__class__.__name__.upper()
            to_name = sub_op.modify_type.__class__.__name__.upper()
            using = get_using_clause(from_name, to_name, sub_op.column_name)
            if using:
                sub_op.kw["postgresql_using"] = using
```

- [ ] **Step 2: Add compare_type and hook to both configure() calls**

In `run_migrations_offline()`, update `context.configure()`:

```python
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        process_revision_directives=_process_revision_directives,
    )
```

In `run_migrations_online()`, update `context.configure()`:

```python
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            process_revision_directives=_process_revision_directives,
        )
```

- [ ] **Step 3: Run lint and verify**

Run: `ruff check src/dazzle_back/alembic/env.py --fix`
Run: `python -c "from dazzle_back.alembic import env; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/alembic/env.py
git commit -m "feat: add compare_type and safe-cast injection to Alembic env (#625)"
```

---

### Task 3: Add dazzle db migrate and rollback commands

**Files:**
- Modify: `src/dazzle/cli/db.py`

The existing `db.py` has raw Alembic commands (`revision`, `upgrade`, `downgrade`). Add user-friendly wrappers that combine autogenerate + upgrade.

- [ ] **Step 1: Add migrate command**

After the existing `history_command` (around line 149), add:

```python
@db_app.command(name="migrate")
def migrate_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    check: bool = typer.Option(
        False,
        "--check",
        help="Dry-run: show what would change without applying",
    ),
    sql: bool = typer.Option(
        False,
        "--sql",
        help="Print SQL without applying",
    ),
) -> None:
    """Generate and apply pending migrations.

    Diffs the DSL-derived schema against the live database and applies
    safe changes automatically. Use --check for a dry-run preview.

    Examples:
        dazzle db migrate              # Generate + apply
        dazzle db migrate --check      # Preview changes
        dazzle db migrate --tenant X   # Apply to tenant schema
    """
    from alembic import command
    from alembic.util.exc import CommandError

    cfg = _get_alembic_cfg()
    url = _resolve_url(database_url)
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    if check:
        console.print("[bold]Migration check (dry-run):[/bold]\n")
        try:
            command.check(cfg)
            console.print("[green]No pending changes.[/green]")
        except CommandError as e:
            console.print(f"[yellow]Pending changes detected:[/yellow] {e}")
        return

    if sql:
        command.upgrade(cfg, "head", sql=True)
        return

    try:
        # Generate revision from current DSL diff.
        # process_revision_directives in env.py suppresses empty revisions,
        # so revision() returns None when there are no changes.
        rev = command.revision(cfg, message="auto", autogenerate=True)
        if rev is None:
            console.print("[green]No schema changes detected.[/green]")
            return

        # Apply the new revision (and any other pending)
        command.upgrade(cfg, "head")
        console.print("[green]Migration applied successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="rollback")
def rollback_command_wrapper(
    revision: str = typer.Argument(
        "-1",
        help="Target revision or steps back (default: -1)",
    ),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
) -> None:
    """Revert the last migration (or to a specific revision).

    Examples:
        dazzle db rollback             # Undo last migration
        dazzle db rollback -2          # Undo last 2 migrations
        dazzle db rollback abc123      # Downgrade to specific revision
    """
    from alembic import command

    cfg = _get_alembic_cfg()
    url = _resolve_url(database_url)
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    try:
        command.downgrade(cfg, revision)
        console.print(f"[green]Rolled back to: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Rollback failed: {e}[/red]")
        raise typer.Exit(1)
```

Note: tenant support (`--tenant`) for migrate requires `env.py` to accept a schema parameter. This is wired through `_get_alembic_cfg()` — add `cfg.attributes["tenant_schema"] = schema` and read it in `env.py`'s `run_migrations_online()` to do `SET search_path`. Implement this in the same step:

In `_get_alembic_cfg()`, the returned config is a plain Alembic Config. The `migrate_command` should set an attribute:

```python
    schema = _resolve_tenant_schema(tenant) if tenant else ""
    if schema:
        cfg.attributes["tenant_schema"] = schema
```

And in `env.py`'s `run_migrations_online()`, before `context.run_migrations()`:

```python
        tenant_schema = config.attributes.get("tenant_schema")
        if tenant_schema:
            from sqlalchemy import text
            connection.execute(text(f"SET search_path TO {tenant_schema}, public"))
```

- [ ] **Step 2: Verify commands register**

Run: `python -c "from dazzle.cli.db import db_app; print([c.name for c in db_app.registered_commands])"`
Expected: list includes `migrate` and `rollback`

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/db.py
git commit -m "feat: add dazzle db migrate and rollback wrapper commands (#625)"
```

---

### Task 4: Replace auto_migrate with Alembic in server and add production guard

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`
- Modify: `src/dazzle/cli/runtime_impl/serve.py`

- [ ] **Step 1: Replace auto_migrate in server.py _setup_database**

In `src/dazzle_back/runtime/server.py`, the `_setup_database` method calls `auto_migrate()` at line ~493. Replace with:

```python
        # Auto-migrate via Alembic
        try:
            from alembic import command
            from alembic.config import Config as AlembicConfig
            from pathlib import Path as _Path

            alembic_dir = _Path(__file__).resolve().parent.parent / "alembic"
            cfg = AlembicConfig(str(alembic_dir / "alembic.ini"))
            cfg.set_main_option("script_location", str(alembic_dir))
            cfg.set_main_option("sqlalchemy.url", self._database_url)

            # Generate + apply in one step (empty revisions suppressed by env.py)
            command.revision(cfg, message="auto", autogenerate=True)
            command.upgrade(cfg, "head")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Alembic auto-migrate: %s", exc)
```

Update the import at the top of `server.py` — change:
```python
from dazzle_back.runtime.migrations import MigrationPlan, auto_migrate
```
to:
```python
from dazzle_back.runtime.migrations import MigrationPlan
```

Also replace `_migrate_tenant_schemas()` (line ~435) — it calls `auto_migrate()` which is being deleted. Replace the `auto_migrate()` call with Alembic:

```python
            try:
                from alembic import command
                from alembic.config import Config as AlembicConfig
                from pathlib import Path as _Path

                alembic_dir = _Path(__file__).resolve().parent.parent / "alembic"
                cfg = AlembicConfig(str(alembic_dir / "alembic.ini"))
                cfg.set_main_option("script_location", str(alembic_dir))
                cfg.set_main_option("sqlalchemy.url", self._database_url)
                cfg.attributes["tenant_schema"] = schema_name

                command.upgrade(cfg, "head")
                logger.info("Migrated tenant schema %s", schema_name)
            except Exception as exc:
                logger.warning("Failed to migrate tenant schema %s: %s", schema_name, exc)
```

- [ ] **Step 2: Add production guard in serve.py**

In `src/dazzle/cli/runtime_impl/serve.py`, inside the `if production:` block (added in the production deployment spec), after the DSL file check and before the infrastructure validation, add:

```python
        # Production mode: refuse to start with pending migrations
        try:
            from alembic import command
            from alembic.config import Config as AlembicConfig
            from alembic.util.exc import CommandError
            from pathlib import Path as _Path

            alembic_dir = _Path(__file__).resolve().parents[3] / "dazzle_back" / "alembic"
            cfg = AlembicConfig(str(alembic_dir / "alembic.ini"))
            cfg.set_main_option("script_location", str(alembic_dir))
            cfg.set_main_option("sqlalchemy.url", database_url)

            try:
                command.check(cfg)
            except CommandError:
                typer.echo(
                    "Cannot start in production mode: pending migrations detected. "
                    "Run 'dazzle db migrate' first.",
                    err=True,
                )
                raise typer.Exit(code=1)
        except ImportError:
            pass  # Alembic not installed, skip check
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q --tb=short 2>&1 | tail -10`
Expected: All pass (server startup code only exercised in integration tests)

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/runtime/server.py src/dazzle/cli/runtime_impl/serve.py
git commit -m "feat: replace auto_migrate with Alembic, add production guard (#625)"
```

---

### Task 5: Retire hand-rolled migration code

**Files:**
- Modify: `src/dazzle_back/runtime/migrations.py`
- Modify: `src/dazzle_back/__init__.py`
- Modify: `src/dazzle_back/runtime/__init__.py`
- Delete: `tests/unit/test_circular_fk_migration.py`
- Delete: `src/dazzle_back/tests/test_migrations.py`

- [ ] **Step 1: Delete MigrationPlanner, MigrationExecutor, MigrationHistory, auto_migrate**

In `src/dazzle_back/runtime/migrations.py`:

**Keep:**
- Module docstring (update to reflect new role)
- `MigrationAction` enum (lines 36-46)
- `MigrationStep` dataclass (lines 49-57)
- `MigrationPlan` dataclass (lines 60-76)
- `ColumnInfo` dataclass (lines 84-92)
- `get_table_schema()` function (lines 95-117)
- `get_table_indexes()` function (lines 120-127)
- `MigrationError` exception (lines 586-589)
- `ensure_dazzle_params_table()` function (used by server startup)

**Delete everything else:**
- `MigrationPlanner` class
- `MigrationExecutor` class
- `MigrationHistory` class
- `auto_migrate()` function
- `plan_migrations()` function
- `_MIGRATION_LOCK_ID` constant

Update the module docstring:

```python
"""
Migration support types and schema introspection for Dazzle.

Migrations are managed by Alembic (see src/dazzle_back/alembic/).
This module retains schema introspection utilities and type definitions
used by the MCP db tools and CLI reporting.
"""
```

- [ ] **Step 2: Update dazzle_back/__init__.py**

Remove `auto_migrate` and `plan_migrations` from the lazy imports:
- Remove lines referencing `_get_auto_migrate`, `_get_plan_migrations`
- Remove entries from the `__getattr__` dispatch dict
- Remove from `__all__` if present

Also update `src/dazzle_back/runtime/__init__.py`:
- Remove `MigrationPlanner`, `auto_migrate`, `plan_migrations` from imports (lines 45-48)
- Remove from `__all__` (lines 120-125)

- [ ] **Step 3: Delete migration tests that reference retired code**

```bash
rm tests/unit/test_circular_fk_migration.py
rm src/dazzle_back/tests/test_migrations.py
```

Both test files import `MigrationPlanner` which is being deleted. The circular FK handling is now Alembic's responsibility via `sa_schema.py`'s `_find_circular_refs()`.

- [ ] **Step 4: Check for other broken imports**

```bash
grep -rn "MigrationPlanner\|MigrationExecutor\|MigrationHistory\|auto_migrate\|plan_migrations" src/ tests/ --include="*.py" | grep -v __pycache__ | grep -v migrations.py | grep -v __init__.py
```

Fix any remaining references. Expected callers:
- `server.py` — already updated in Task 4
- `cli/runtime_impl/build.py` — may reference `plan_migrations` for dry-run; update to use Alembic `command.check()`

- [ ] **Step 5: Run tests**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q --tb=short 2>&1 | tail -10`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/migrations.py src/dazzle_back/__init__.py tests/unit/test_circular_fk_migration.py
git commit -m "refactor: retire MigrationPlanner/Executor/History (~400 lines) in favor of Alembic (#625)"
```

---

### Task 6: CHANGELOG and final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CHANGELOG entry**

Add under `## [Unreleased]`:

```markdown
### Changed
- Database migrations now use Alembic instead of hand-rolled `MigrationPlanner`
- `dazzle db migrate` generates and applies migrations in one step
- `dazzle db rollback` reverts migrations with optional revision target
- Type changes detected automatically via `compare_type=True`
- `dazzle serve --production` refuses to start with pending migrations

### Added
- Safe cast registry: text→uuid, text→date, text→timestamptz, text→jsonb applied automatically with USING clauses
- `dazzle db migrate --check` dry-run to preview schema changes
- `dazzle db migrate --tenant <slug>` for per-tenant schema migration

### Removed
- `MigrationPlanner`, `MigrationExecutor`, `MigrationHistory` classes (~400 lines)
- `auto_migrate()` / `plan_migrations()` functions — replaced by Alembic
```

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle_back/runtime/safe_casts.py src/dazzle_back/runtime/migrations.py src/dazzle/cli/db.py src/dazzle_back/alembic/env.py src/dazzle_back/runtime/server.py --fix`

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle_back/runtime/safe_casts.py src/dazzle_back/runtime/migrations.py src/dazzle/cli/db.py --ignore-missing-imports`

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q 2>&1 | tail -10`
Expected: All pass (count drops slightly due to deleted migration planner tests)

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG for Alembic migration system (#625)"
```
