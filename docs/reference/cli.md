# CLI Reference

Complete reference for the `dazzle` command-line interface.

## Commands Overview

### Project Creation

There is no `init` command. Start a new app with the MCP `bootstrap` tool (from a
`SPEC.md`), or copy `examples/simple_task` from the repository and edit it.

### Project Operations

| Command | Description |
|---------|-------------|
| `dazzle validate` | Parse and validate all DSL modules |
| `dazzle lint` | Extended validation with style checks |
| `dazzle inspect` | Inspect entities, surfaces, and structure |
| `dazzle doctor` | Run environment health checks |

### Runtime

| Command | Description |
|---------|-------------|
| `dazzle serve` | Start the full-stack app (API + UI) |
| `dazzle build` | Build a production deployment bundle |
| `dazzle build-ui` | Generate UI artifacts from AppSpec |
| `dazzle build-api` | Generate API spec from AppSpec |

### Database & Auth

| Command | Description |
|---------|-------------|
| `dazzle db` | Database migration commands (Alembic) |
| `dazzle migrate` | Run database migrations for production |
| `dazzle auth` | Manage authentication users and sessions |

### Testing

| Command | Description |
|---------|-------------|
| `dazzle test` | Multi-tier test runner (API, Playwright, LLM agent) |
| `dazzle e2e` | Viewport assertions (`run-viewport`), persona journeys (`journey`) and the E2E environment (`env`) |
| `dazzle story` | Story-driven test generation |

### Infrastructure

| Command | Description |
|---------|-------------|
| `dazzle deploy` | Plan infrastructure + generate buildpack (Heroku) deploy files |

### Tooling

| Command | Description |
|---------|-------------|
| `dazzle mcp` | MCP (Model Context Protocol) server commands |

---

## Command Groups

Every registered command group (sub-app). Run `dazzle <group> --help` for its
subcommands, or `dazzle search <keyword>` to discover commands
interactively. This table is drift-gated against the CLI registration in
`src/dazzle/cli/__init__.py` (`tests/unit/test_docs_drift.py`) — adding a group
there requires a row here.

| Group | Purpose |
|-------|---------|
| `dazzle agent` | Agent-first development commands |
| `dazzle analytics` | Analytics, consent, and privacy tooling |
| `dazzle auth` | Manage authentication users and sessions |
| `dazzle compliance` | Compliance documentation tools (ISO 27001 / SOC 2) |
| `dazzle db` | Database migration commands (Alembic) |
| `dazzle demo` | Demo data management commands |
| `dazzle deploy` | Plan infrastructure + generate buildpack (Heroku) deploy files |
| `dazzle docs` | Documentation generation, validation, and maintenance |
| `dazzle fitness` | Framework structural-fitness ratchets (complexity, clones) |
| `dazzle inspect` | Introspect framework extension points and the public API surface |
| `dazzle mcp` | MCP (Model Context Protocol) server commands |
| `dazzle perf` | On-demand local OpenTelemetry tracing |
| `dazzle pipeline` | Run the deterministic quality pipeline |
| `dazzle qa` | QA toolkit — visual quality evaluation and screenshot capture |
| `dazzle rbac` | RBAC verification and compliance |
| `dazzle representation` | Data-representation judgement — patterns, decide, classify (#1617) |
| `dazzle scaffold` | Scaffold domain artefacts from agent closed-loop maps (#1605) |
| `dazzle sentinel` | SaaS Sentinel — failure-mode detection for Dazzle applications |
| `dazzle signing` | Provision the native document signing primitive |
| `dazzle spec` | Compare narrative product spec against DSL state — drift detection |
| `dazzle story` | Story-driven test generation |
| `dazzle tenant` | Multi-tenant schema management |
| `dazzle test` | Multi-tier test runner (dsl-run / playwright / agent) |
| `dazzle ux` | UX verification — deterministic interaction testing |

---

## Key Commands

### dazzle validate

Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

```bash
dazzle validate [OPTIONS]
```

```bash
dazzle validate
dazzle validate --verbose
```

#### Warnings for declarations that change nothing

These warnings never fail the build. Each one means the DSL declares something
that has no runtime effect, so the app does not do what the DSL says (ADR-0057,
flense ship U). Parser warnings end with `(<file>:<line>)`.

| Code | Fires when | What to do |
|------|-----------|------------|
| `W_UNKNOWN_BLOCK_KEY` | A `policies`, `tenancy`, `island`, `llm_model`, `llm_config`, `llm_intent`, `view`, `process`, process `step`, `schedule`, or integration `action`/`sync` block has a line it does not recognise: a typo, or a clause removed from the grammar (e.g. `tenancy: provisioning:`, view `time_bucket:`). The whole entry, including any indented block under it, is skipped. | Fix the spelling or delete the line. |
| `W_DECLARED_NOT_READ` | A clause the parser accepts but no framework code reads is declared: `feedback_widget` `categories:`/`severities:`, service `stub:`, `entity_card_config` `scope_param:`, schedule `catch_up:`/`overlap:`, `llm_config` `artifact_store:`, grant relation `principal_label:`/`revoke_verb:`. | Delete the clause, or treat it as documentation only. |
| `W_CLAUSE_VALUE_IGNORED` | `llm_config` `concurrency:` or `rate_limits:` has an inline value (`concurrency: 3`) instead of a block of `<model>: <limit>` lines. | Write one `<model>: <limit>` line per model under the clause. |
| `W_TENANCY_MODE_UNIMPLEMENTED` | `tenancy: mode:` is `schema_per_tenant` or `database_per_tenant`. These modes turn off partition-key injection and RLS, and no runtime provides the isolation they name, so the app has no tenant fencing. | Use `shared_schema` (or `single`). |
| `W_GRANT_EXPIRY_CONTRADICTION` | A grant relation declares `expiry: none` and `max_duration:`. The grant routes reject every `expires_at` under `expiry: none`, so the cap never applies. | Drop `max_duration:` or use `expiry: required`. |
| `W_GRANT_APPROVER_UNUSED` | A grant relation declares `approved_by:` with `approval: none` or `immediate`. Grants are active on creation, so no approver is ever asked. | Drop `approved_by:` or use `approval: required`. |

`tenancy: topics:` accepts only `shared` or `namespace_per_tenant`. Any other
value is a parse error. It used to fall back to `shared` without saying so.

---

### dazzle lint

Run extended lint checks (validation plus additional style warnings).

```bash
dazzle lint [OPTIONS]
```

---

### dazzle serve

Start the full-stack application (FastAPI backend + HTMX frontend).

```bash
dazzle serve [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--manifest` | `-m` | `dazzle.toml` | Path to manifest file |
| `--port` | `-p` | auto | Frontend port (default 3000) |
| `--api-port` | | auto | Backend API port (default 8000) |
| `--host` | | `127.0.0.1` | Host to bind to |
| `--local` | | | Run locally without Docker |
| `--watch` | `-w` | | Re-validate the DSL on every change and print the result (restart to apply) |
| `--ui-only` | | | Serve static UI only (no API) |
| `--backend-only` | | | Serve API only (no frontend) |
| `--rebuild` | | | Force Docker image rebuild |
| `--attach` | `-a` | | Stream Docker logs to terminal |
| `--database-url` | | | PostgreSQL URL (also reads `DATABASE_URL` env) |
| `--test-mode` | | | Enable E2E test endpoints |
| `--dev-mode` | | | Enable dev control plane |

```bash
# Docker mode (default)
dazzle serve

# Re-validate the DSL on every change (restart to apply)
dazzle serve --watch

# API server only
dazzle serve --backend-only

# Custom ports
dazzle serve --port 4000 --api-port 9000

```

**Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `http://localhost:3000` | UI |
| `http://localhost:8000/api/` | REST API |
| `http://localhost:8000/docs` | Interactive API docs (Swagger) |
| `http://localhost:8000/redoc` | Alternative API docs |

---

### dazzle test

Multi-tier testing framework.

```bash
dazzle test COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `generate` | Generate E2E test spec from AppSpec |
| `run` | Run Playwright tests |
| `walk` | Scene walks list/validate/run/pack-dry-run (#1638) |
| `docs claims` | Job claim registry check (#1638 PR3) |
| `dsl-run` | **Tier 1**: Run API-based tests against a server |
| `tier2-generate` | **Tier 2**: Generate Playwright tests from surfaces |
| `agent` | **Tier 3**: Run LLM-agent-powered E2E tests |
| `populate` | Auto-populate stories and test designs from DSL |
| `create-sessions` | Create authenticated sessions for DSL personas |
| `diff-personas` | Compare route responses across personas |

```bash
# Run API-level tests
dazzle test dsl-run --base-url http://localhost:8000

# Generate Tier 2 Playwright tests from surfaces
dazzle test tier2-generate
```

---

### dazzle auth

Manage authentication users and sessions.

```bash
dazzle auth COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `create-user` | Create a new user |
| `list-users` | List users |
| `get-user` | Get user details |
| `update-user` | Update user properties |
| `reset-password` | Reset a user's password |
| `deactivate` | Soft-delete a user |
| `list-sessions` | List active sessions |
| `cleanup-sessions` | Remove expired sessions |
| `config` | Show auth system configuration |
| `rotate-encryption-key` | Re-encrypt all enterprise connection secrets onto a new `DAZZLE_CONNECTION_SECRET` |
| `connection` | Manage per-org enterprise connections (OIDC, SCIM) and verify their domains |

`dazzle auth connection` subcommands: `create` (OIDC), `create-scim`, `list`, `add-domain`,
`show-verification`, `verify-domain`, `doctor [--probe] [--json]`, `rotate-secret [--grace]`,
`revoke-previous-secret`, `secret-history`, `set-require-sso <id> --on|--off [--tenant]`,
`scaffold`, `delete`. Connections are runtime data
(DD-013); the `[auth.enterprise] protocols` manifest key gates which protocol routes mount.

```bash
dazzle auth create-user --email admin@example.com --roles admin
dazzle auth list-users
dazzle auth connection doctor <connection-id> --probe
```

---

### dazzle deploy

Plan an app's infrastructure and generate buildpack deploy files.

```bash
dazzle deploy COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `plan` | Show the infrastructure an app needs (target-agnostic) |
| `heroku` | Generate Heroku/uv-buildpack deploy files |

See [Deployment](deployment.md) for the full guide.

---

### dazzle db

Database migration commands (Alembic).

```bash
dazzle db COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `revision` | Generate a new migration |
| `upgrade` | Apply pending migrations |
| `downgrade` | Rollback migrations |
| `current` | Show current revision |
| `history` | Show migration history |
| `apply-rls` | Apply the `shared_schema` RLS policies (`--check-dumpable`: check only) |
| `dump` | Tenant-aware backup under `shared_schema` RLS (one bound dump per tenant + manifest) |
| `restore-check` | Restore a `dump` into a scratch database and compare every row count |
| `resanitize-rich-text` | Re-run the rich-text sanitiser over stored `widget=rich_text` values |

#### dazzle db upgrade

```bash
dazzle db upgrade [REVISION]            # default: head
```

| Option | Description |
|--------|-------------|
| `--no-rls` | `shared_schema` only: skip applying the RLS policies after the migrations (run `dazzle db apply-rls` separately) |
| `--no-rls-tripwire` | `shared_schema` only: do not run the upgrade with `row_security = off` (#1778) |
| `--database-url URL` | Target database |

For `shared_schema` apps the whole upgrade transaction runs with
`SET LOCAL row_security = off`. A migration binds no tenant, so DML on a fenced
table would otherwise match zero rows without an error. With the tripwire it
fails with `query would be affected by row-level security policy`. Data-migration
seams run tenant DML through `for_each_tenant`
([migrations](migrations.md#seam-dml-under-shared_schema-tenancy-1778)).
Superuser and `BYPASSRLS` connections are never filtered, so the tripwire does
not affect them.

#### dazzle db dump / restore-check

Under `tenancy: mode: shared_schema`, tenant tables have `FORCE ROW LEVEL
SECURITY`. A plain `pg_dump` (and `heroku pg:backups`) run by a role RLS filters
fails, and `pg_dump --enable-row-security` with no tenant bound writes every
tenant table empty (#1788). `dump` writes one custom-format dump per tenant,
each with `dazzle.tenant_id` bound through `PGOPTIONS`, all from one exported
snapshot, then `manifest.json`.

```bash
dazzle db dump --out backups/ [--label L] [--role R] [--pg-bin DIR]
dazzle db restore-check --from backups/<label> --target-url URL [--drop-first] [--pg-bin DIR]
```

| Option | Description |
|--------|-------------|
| `--out DIR` | Parent directory; the dump goes to `DIR/<label>/` (must be absent or empty) |
| `--label L` | Dump label (default `dump-<UTC timestamp>`) |
| `--role R` | `SET ROLE` for the dump session. Required when the connected role is a superuser or has `BYPASSRLS` |
| `--pg-bin DIR` | Directory holding `pg_dump` / `pg_restore` (default: `PATH`) |
| `--database-url URL` | Source database (`dump` only) |
| `--from DIR` | The dump directory holding `manifest.json` (`restore-check`) |
| `--target-url URL` | Scratch database to restore into (`restore-check`) |
| `--drop-first` | Drop every user schema on the target first (`restore-check`) |

`dump` exits 2 without `shared_schema`, on RLS policy drift (or a live RLS
posture that disagrees with the DSL / artifact registry), when the role bypasses
RLS and no `--role` is given, and when `organizations` has no tenants. The URL
reaches `pg_dump` only through `PG*` environment variables.

The manifest records the label, creation time, Dazzle version, Alembic
version, source host and database, server and `pg_dump` versions, partition
key, tenant entity, the tenants and their files, the fenced and non-fenced
tables, per-tenant per-table counts, global counts and file sizes.

`restore-check` restores `pre-data` from the first dump, the fenced tables from
every dump and the non-fenced tables from the first dump only, then
`post-data`, and recounts. It exits 0 when every count matches, 1 on a
mismatch (printed per table and tenant) or a failed step, and 2 when there is
no manifest, the target is the source database, or the target has tables and
`--drop-first` was not given.

`dazzle db apply-rls --check-dumpable` applies nothing and exits 1 when FORCE
RLS is on and the connected role cannot bypass it; `dazzle db verify` prints
the same check as a warning. `dazzle db snapshot` / `db restore` (e2e
baselines) refuse in that state.

#### dazzle db resanitize-rich-text

Rows written before rich-text sanitising reached the write path (flense ship T)
still hold whatever HTML was posted. This walks every field a surface renders
with `widget=rich_text` and runs the same allowlist sanitiser
(`clean_rich_text`) over each stored value. The target database resolves like
every `dazzle db` command: `--database-url` > `DATABASE_URL` > `dazzle.toml`.

```bash
dazzle db resanitize-rich-text --dry-run   # default: per entity.field, rows that would change
dazzle db resanitize-rich-text --apply     # write the sanitised values
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Report only (the default). Counts per entity and field; stored values are never printed |
| `--apply` | Write the sanitised values |
| `--tenant SLUG` | Run against one tenant schema (schema-per-tenant isolation) |
| `--database-url URL` | Target database |
| `--json` | Machine-readable report |

A value longer than the field's cap after sanitising is reported and left
untouched. A visually empty value becomes NULL (or `""` on a `required` field).
Re-running is safe: clean values are unchanged.

---

### dazzle mcp

MCP (Model Context Protocol) server for AI assistants.

```bash
dazzle mcp COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `run` | Run the MCP server |
| `setup` | Register with Claude Code |
| `check` | Check MCP server status |

See [MCP Server](../architecture/mcp-server.md) for the full tool reference.

---

### dazzle story

Story-driven test generation.

```bash
dazzle story COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `propose` | Propose behavioural stories from DSL |
| `list` | List stories by status |
| `generate-tests` | Generate test designs from accepted stories |

---

## Common Workflows

### Development

```bash
# Validate, then serve and re-validate on every DSL change
dazzle validate && dazzle serve --watch
```

### Testing

```bash
# Run API tests against a running server
dazzle serve &
dazzle test dsl-run

# Run the generated E2E flows
dazzle test run
```

### CI/CD

```yaml
steps:
  - name: Validate DSL
    run: dazzle validate

  - name: Lint
    run: dazzle lint

  - name: Run API tests
    run: |
      dazzle serve --test-mode &
      sleep 5
      dazzle test dsl-run --base-url http://localhost:8000
```

### Deployment

```bash
# Discover the app's infrastructure requirements, then generate buildpack files
dazzle deploy plan
dazzle deploy heroku
```
