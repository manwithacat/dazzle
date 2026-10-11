# Dynamic RBAC Verifier — Design (#1171)

**Date:** 2026-05-20
**Issue:** #1171 — "dynamic RBAC verifier is a stub but docs advertise it as delivered"
**Status:** Approved — ready for implementation planning

## Problem

`src/dazzle/rbac/verifier.py` is the "Layer 2" of the RBAC verification
framework. The types (`VerifiedCell`, `VerificationReport`, `CellResult`),
the comparison function (`compare_cell`), and JSON `save`/`load` are real
and tested. But the orchestrating `verify()` async function is a **stub**:
it returns a placeholder report with zero cells. The `dazzle rbac verify`
CLI command prints "not yet implemented". Meanwhile the README, `llms.txt`,
and `docs/reference/rbac-verification.md` advertise dynamic verification —
"the running app is probed as every role to confirm runtime matches the
matrix" — as a delivered capability.

This design replaces the stub with a real implementation and wires the CLI.

## Goal

`verify(project_root)` boots the app, exercises every generated route as
every role, diffs observed behaviour against the static RBAC matrix, and
returns a populated `VerificationReport`. Divergence between the static
matrix and runtime behaviour surfaces as `CellResult.VIOLATION`.

## Decisions (from brainstorming)

1. **Boot model — managed in-process ASGI.** `verify()` constructs the
   `DazzleServer` ASGI app in-process and drives it with
   `httpx.AsyncClient(transport=httpx.ASGITransport(app=...))`. No real
   socket, no port. The full middleware + route stack (auth, Cedar permit
   gate, scope predicates) is exercised — that is all that matters for
   RBAC correctness; a real socket adds nothing. Fast, hermetic, no
   server-lifecycle flake.
2. **Probe scope — full matrix including permitted writes.** Every
   `(role, entity, operation)` cell is probed, including permitted
   create/update/delete. To keep write mutations from polluting a real
   database, `verify()` owns a **disposable database** (provision → probe
   → drop).
3. **Role authentication — seed one synthetic user per role.** `verify()`
   inserts exactly one user per matrix role into the disposable database
   and authenticates each via the normal `/auth/login` flow. Fully
   hermetic — no dependency on demo data or test-mode endpoints.

## Architecture

`verify()` orchestrates small, independently-testable helpers. The pure
types and `compare_cell` stay where they are in `verifier.py`; the runtime
helpers are added to the same module.

```
verify(project_root)
  │
  ├─ load_project_appspec(root) ─────────────► AppSpec
  ├─ generate_access_matrix(appspec) ────────► AccessMatrix   (expected)
  │
  ├─ _DisposableDatabase()  ── async ctx mgr
  │     CREATE DATABASE dazzle_verify_<uuid>
  │     create schema (dev-mode metadata.create_all)
  │     ... yield db_url ...
  │     DROP DATABASE                          (finally)
  │
  ├─ _seed_role_users(db_url, matrix.roles) ─► {role: (email, password)}
  ├─ _seed_baseline_rows(db_url, entities) ──► {entity: baseline_id}
  │
  ├─ build DazzleServer(app) against db_url
  ├─ httpx.AsyncClient(ASGITransport(app))
  ├─ _login per role ───────────────────────► {role: session cookies}
  │
  ├─ for each matrix cell (role, entity, operation):
  │     set_audit_sink(InMemoryAuditSink())
  │     status, count = _probe_cell(client, session, entity, op, baseline_id)
  │     records = drained from the sink
  │     result = compare_cell(expected, status, count, total=...)
  │     → VerifiedCell
  │
  └─ VerificationReport(cells, totals…) → save(.dazzle/rbac-verify-report.json)
```

## Components

### `_DisposableDatabase` (async context manager)
- Derives the PostgreSQL server URL from the configured `DATABASE_URL`
  (strip the database name), connects to the maintenance DB, and runs
  `CREATE DATABASE dazzle_verify_<uuid>`.
- Creates the schema using the framework's existing dev-mode path
  (`build_metadata(entities)` + `metadata.create_all`), the same code
  `DazzleServer._setup_database` uses when `_should_create_schema_on_startup`.
- `DROP DATABASE` in a `finally` block — the scratch DB never leaks even
  if verification raises.
- **Dependency:** a reachable PostgreSQL server (ADR-0008 — the runtime is
  PG-only; `verify()` already needs one). If `DATABASE_URL` is unset,
  `verify()` fails fast with a clear message.

### `_seed_role_users(db_url, roles)`
- For each role in the matrix, insert one user: email
  `verify-<role>@dazzle.test`, password `test` (hashed via the framework's
  normal auth path), with that single role assigned.
- Returns `{role: (email, password)}` for the login step.

### `_seed_baseline_rows(db_url, entities)`
- For each entity, insert one baseline row (as a superuser/admin context)
  so `read`/`update`/`delete` cells have a concrete target id.
- Returns `{entity: baseline_id}`.

### `_probe_cell(client, session, entity, operation, baseline_id)`
- Maps an operation to an HTTP request, issued with the role's session
  cookies:
  - `list` → `GET /api/<entity_plural>`
  - `read` → `GET /api/<entity_plural>/{baseline_id}`
  - `create` → `POST /api/<entity_plural>` (minimal valid body)
  - `update` → `PUT|PATCH /api/<entity_plural>/{baseline_id}`
  - `delete` → `DELETE /api/<entity_plural>/{baseline_id}`
- Returns `(observed_status, observed_count)` — `observed_count` is the
  item count parsed from a `list` response, `None` otherwise.

### Audit capture
- Each probe is wrapped with `set_audit_sink(InMemoryAuditSink())`; the
  sink's `AccessDecisionRecord`s are drained into the cell's
  `audit_records`. This is the documented purpose of the `dazzle.rbac.audit`
  verification seam (clarified in #1172).

### CLI — `dazzle rbac verify`
- Replace the stub in `cli/rbac.py`: `asyncio.run(verify(root))`, print a
  summary table (total / passed / violated / warnings), save the report to
  `.dazzle/rbac-verify-report.json`, and `raise typer.Exit(1)` when
  `violated > 0`. `dazzle rbac report` already reads that JSON path.

## Comparison semantics

Unchanged — `compare_cell()` already maps `(expected PolicyDecision,
observed_status, observed_count)` to `PASS` / `VIOLATION` / `WARNING` and
is unit-tested. The verifier only feeds it observed values.

## Error handling

- **Disposable DB:** always dropped (`finally`), even on exception.
- **App boot failure:** `verify()` returns a `VerificationReport` with
  zero cells and an error detail; the CLI exits non-zero.
- **Per-cell probe exception:** the cell becomes `CellResult.WARNING` with
  the exception in `detail`; verification continues to the next cell — one
  bad route never aborts the whole run.
- **No `DATABASE_URL`:** fail fast with a clear, actionable message.

## Testing

- **Unit:** each helper in isolation — `_probe_cell` against a fake httpx
  client; `_DisposableDatabase` lifecycle with a mocked connection;
  `_seed_role_users` / `_seed_baseline_rows` shape assertions. `compare_cell`
  is already covered.
- **Integration (`postgres`-marked):** run the full `verify()` against
  `fixtures/rbac_validation` and assert `violated == 0` — the fixture is
  the canonical RBAC probe and its matrix should hold at runtime.

## Scope boundary — v1 vs v2

**v1 (this design):** verifies *operation-level* allow / deny / filter
against the matrix. `read`/`update`/`delete` are probed against one
baseline row per entity. `list` filtering is checked via the item count.

**v2 (deliberately deferred, noted not built):** per-row cross-tenant
IDOR probing — seeding rows owned by *different* tenants and confirming a
role cannot reach another tenant's specific row by id. v1 confirms the
operation is gated; v2 confirms row-level isolation per record. Deferring
keeps v1 "narrow but proper" per the issue.

## Docs follow-through

Once `verify()` is real, update `README.md`, `docs/llms.txt`, and
`docs/reference/rbac-verification.md` so "Dynamic Verification" is
described accurately rather than overclaimed — this also resolves the
RBAC-overclaim half of #1176.

## Out of scope

- Making `dazzle rbac verify` a blocking CI gate (a follow-up once the
  verifier has a track record).
- Per-row IDOR probing (v2, above).
- Verifying custom/extension routes — the matrix covers generated routes.
