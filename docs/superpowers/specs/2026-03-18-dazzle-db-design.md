# Dazzle DB: DSL-Driven Database Operations

**Date**: 2026-03-18
**Status**: Design
**Issue**: #529

## Problem

SaaS founders on Dazzle need database operations — backup, restore, reset, verify, cleanup — but each project reinvents the tooling. CyFuture built `db_ops.py`, AegisMark built `restore_golden_master.py`. Both are project-specific scripts driven by YAML config that duplicates information the DSL already declares.

Dazzle already knows the entire data model: every entity, every field, every relationship. Database operations should be derived from the DSL, not configured separately.

## Design

### Two Layers

**Layer A — DSL-derived (zero config):** Operations that work out of the box using the AppSpec's entity definitions, relationship graph, and field types. No project-specific configuration needed.

**Layer B — Provider-pluggable (dazzle.toml config):** Backup/restore backends that depend on the deployment target. Configured via `[database]` in `dazzle.toml`.

### Commands

| Command | Layer | Type | MCP | Description |
|---------|-------|------|-----|-------------|
| `dazzle db status` | A | Read | Yes | Row counts per entity, database size, backup inventory |
| `dazzle db verify` | A | Read | Yes | FK integrity check, baseline validation, orphan detection |
| `dazzle db reset` | A | Write | No | Truncate entity tables in dependency order, preserve auth |
| `dazzle db cleanup` | A | Write | No | Find and remove FK orphans using DSL relationship graph |
| `dazzle db backup` | B | Write | No | Dump to local/S3/Heroku PG |
| `dazzle db restore` | B | Write | No | Restore from local/S3/Heroku PG backup |

Read operations are available as both CLI commands and MCP tools. Write operations are CLI-only (follows the MCP/CLI boundary principle).

---

## Layer A: DSL-Derived Operations

### `dazzle db status`

Iterates `appspec.entities`, counts rows per table, reports totals.

```
$ dazzle db status
Entity           Rows    Size
─────────────────────────────
User               12    48KB
School              3    12KB
StaffMember       199   180KB
Student          3406   2.1MB
...
─────────────────────────────
Total: 48 entities, 12,847 rows, 8.4MB

Backups: 3 local, 1 heroku
Last backup: 2026-03-18 14:30 (local)
```

### `dazzle db verify`

Walks every `ref` field in every entity and checks FK integrity. Reports:

1. **Missing references** — records where a `ref` field points to a non-existent parent
2. **Orphan records** — records whose parent has been deleted but the child persists
3. **Baseline validation** — expected minimum record counts (if configured in `dazzle.toml`)
4. **Auth integrity** — user records exist for all declared personas

```
$ dazzle db verify
FK Integrity:
  ✓ Student.school → School: 3406/3406 valid
  ✗ Exclusion.student → Student: 2 orphans found
    - Exclusion #a1b2c3 → Student #deleted
    - Exclusion #d4e5f6 → Student #deleted

Auth Users:
  ✓ 8/8 persona users present

Baselines:
  ✓ School: 3 (minimum: 1)
  ✗ StaffMember: 0 (minimum: 1)

Result: 2 issues found
```

The relationship graph is computed from `appspec.entities` — every `ref X` field defines an FK constraint. No manual config.

### `dazzle db reset`

Truncates entity tables in topological order (leaf entities first, then parents) to respect FK constraints. Preserves:

- Auth tables (users, sessions, roles)
- Config/settings tables
- Any tables listed in `[database.preserve]`

```
$ dazzle db reset
This will truncate 45 entity tables (12,847 total records).
Auth tables (3 tables) will be preserved.
Type 'reset' to confirm: reset

Truncating in dependency order...
  Exclusion (60 rows) ✓
  ParentConsent (10218 rows) ✓
  ...
  School (3 rows) ✓

Reset complete: 45 tables truncated, 12,847 records removed.
```

The truncation order is computed from the entity dependency graph (topological sort of `ref` relationships). This is the same graph used by the schema generator — no additional config needed.

### `dazzle db cleanup`

Finds and removes FK orphans — records where a `ref` field references a non-existent parent. This is the targeted version of `reset`: it removes only broken records, not everything.

```
$ dazzle db cleanup --dry-run
Found 7 orphan records:
  2 × Exclusion (student → Student: missing)
  3 × Assessment (teacher → StaffMember: missing)
  2 × ParentConsent (student → Student: missing)

Run without --dry-run to delete.

$ dazzle db cleanup
Deleting 7 orphan records...
  2 × Exclusion ✓
  3 × Assessment ✓
  2 × ParentConsent ✓

Cleanup complete: 7 orphans removed.
```

The orphan sweep is iterative: after deleting orphans, re-check for cascading orphans (a record that was only referenced by the deleted orphans). Repeat until no more orphans are found (max 10 iterations to prevent infinite loops).

---

## Layer B: Provider-Pluggable Backup/Restore

### Configuration

```toml
[database]
backup_provider = "local"         # "local" | "s3" | "heroku"
backup_path = ".dazzle/backups"   # local backup directory
retention = 5                     # keep N most recent backups

[database.heroku]
app = "my-app-prod"

[database.s3]
bucket = "my-backups"
prefix = "dazzle/"
region = "eu-west-1"
```

### Provider Protocol

```python
class BackupProvider(Protocol):
    def backup(self, db_url: str, label: str) -> BackupInfo: ...
    def restore(self, db_url: str, backup_id: str) -> None: ...
    def list_backups(self) -> list[BackupInfo]: ...
    def prune(self, keep: int) -> int: ...

@dataclass
class BackupInfo:
    id: str
    label: str
    timestamp: str
    size_bytes: int
    provider: str
    path: str  # local path, S3 key, or Heroku backup ID
```

### Providers

**`LocalProvider`** — ships with Dazzle, no extra dependencies.
- Backup: `pg_dump --format=custom` → `.dazzle/backups/<label>-<timestamp>.dump`
- Restore: `pg_restore --clean --if-exists`
- Prune: delete oldest files beyond retention count

**`S3Provider`** — requires `boto3` (optional dependency).
- Backup: `pg_dump` → gzip → S3 put
- Restore: S3 get → gunzip → `pg_restore`
- Uses `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars or IAM roles

**`HerokuProvider`** — requires `heroku` CLI.
- Backup: `heroku pg:backups:capture`
- Restore: `heroku pg:backups:restore`
- List: `heroku pg:backups`

### `dazzle db backup`

```
$ dazzle db backup
Creating backup: pre-deploy-2026-03-18
Provider: local
Path: .dazzle/backups/pre-deploy-2026-03-18-143000.dump
Size: 8.4MB
Duration: 2.3s

$ dazzle db backup --label golden-master --provider heroku
Creating backup: golden-master
Provider: heroku (my-app-prod)
Heroku backup ID: b042
Duration: 12.1s
```

### `dazzle db restore`

```
$ dazzle db restore
Available backups:
  1. pre-deploy-2026-03-18 (local, 8.4MB, 2h ago)
  2. weekly-2026-03-17 (local, 8.2MB, 1d ago)
  3. golden-master (heroku, b042, 3d ago)

Select backup [1]: 1

This will replace all data in the database.
Type 'restore' to confirm: restore

Restoring from .dazzle/backups/pre-deploy-2026-03-18-143000.dump...
Duration: 4.1s
Restore complete.
```

---

## Safety

All write operations require interactive confirmation:
- `dazzle db reset` — "Type 'reset' to confirm"
- `dazzle db cleanup` — "Type 'cleanup' to confirm" (unless `--dry-run`)
- `dazzle db restore` — "Type 'restore' to confirm"
- `dazzle db backup` — no confirmation needed (non-destructive)

`--yes` flag skips confirmation for CI/scripting use.

`--dry-run` on cleanup shows what would be deleted without deleting.

---

## MCP Operations

Added to a new `db` MCP tool:

```
db status    — row counts per entity, database size, backup inventory
db verify    — FK integrity report with findings list
```

These are read-only operations that let Claude Code inspect database state without running CLI commands.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/db/__init__.py` | Package init |
| `src/dazzle/db/core.py` | Entity-aware operations: status, verify, reset, cleanup |
| `src/dazzle/db/backup.py` | Backup/restore orchestration, provider dispatch |
| `src/dazzle/db/providers/__init__.py` | BackupProvider protocol |
| `src/dazzle/db/providers/local.py` | LocalProvider (pg_dump/pg_restore) |
| `src/dazzle/db/providers/s3.py` | S3Provider (boto3) |
| `src/dazzle/db/providers/heroku.py` | HerokuProvider (heroku CLI) |
| `src/dazzle/cli/db.py` | CLI command group |
| `src/dazzle/mcp/server/handlers/db.py` | MCP handler |

---

## Dependencies on Existing Infrastructure

- **AppSpec**: `appspec.entities` for entity list, field types, relationships
- **DatabaseManager**: `dazzle_back.runtime.repository.DatabaseManager` for database connections
- **Entity dependency graph**: Compute from `ref` fields in `appspec.entities` (topological sort)
- **dazzle.toml**: `[database]` section for provider config (new section)

## Non-Goals

- Schema migrations (handled by `dazzle serve` auto-migration)
- Data seeding (handled by `dazzle demo`)
- Test data management (handled by test runner `__test__/reset`)
- Multi-database support (single database per project for now)

## Implementation Order

1. `core.py` — status + verify (read-only, safest to start)
2. CLI `db status` + `db verify` commands
3. MCP `db status` + `db verify` operations
4. `core.py` — reset + cleanup (write operations)
5. CLI `db reset` + `db cleanup` commands
6. `backup.py` + `LocalProvider`
7. CLI `db backup` + `db restore`
8. `S3Provider` + `HerokuProvider` (optional, separate tasks)
