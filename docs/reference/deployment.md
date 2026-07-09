# Deployment

Dazzle apps deploy as a single, well-optimised **core process**. You run that
process on a buildpack platform (Heroku or similar) or any Python host, provision
the backing services the app needs yourself, and pass their connection details in
via environment variables. Dazzle does not generate cloud infrastructure — it
tells you *what* the app requires and generates the buildpack files to run it.

```
DSL Files → AppSpec IR → infrastructure requirements (deploy plan)
                       → buildpack deploy files (deploy heroku)
```

## Discovering an app's infrastructure — `dazzle deploy plan`

`dazzle deploy plan` is **target-agnostic**: it infers from your DSL what backing
services the app needs (database, cache, queue, workers, object storage, ledger
cluster) and which environment variables the host must supply. It does **not**
generate code or target any specific cloud.

```bash
dazzle deploy plan [--project DIR] [--format text|json]
```

| Option | Description |
|--------|-------------|
| `--project` | Project directory to analyse (defaults to the current directory) |
| `--format` | `text` (human-readable, default) or `json` (machine-readable) |

For a simple app the plan lists a **database — Postgres** component, the
environment variables the host must provide (`DATABASE_URL`, …), and notes
reminding you to provision the services yourself and deploy the app as a core
process via a buildpack. Richer apps add components for cache, queues, workers,
object storage, and ledger clusters as the DSL warrants.

Use the plan as the checklist of services to provision and env vars to set before
you deploy.

## Generating buildpack deploy files — `dazzle deploy heroku`

`dazzle deploy heroku` generates the files needed to deploy on Heroku (or any
uv-buildpack-compatible platform). This is the **supported deploy path**.

```bash
dazzle deploy heroku [--pip]
```

| Mode | Files generated |
|------|-----------------|
| default (uv buildpack) | `Procfile`, `pyproject.toml`, `uv.lock`, `.python-version` |
| `--pip` (legacy) | `requirements.txt`, `runtime.txt` (plus `Procfile`) |

See the [Heroku deployment guide](../guides/heroku.md) for the full walkthrough
(provisioning add-ons, setting config vars, running migrations, and pushing).

### The process entrypoint — `dazzle serve --production`

However you host the app, the production entrypoint is:

```bash
dazzle serve --production
```

This binds `0.0.0.0`, requires `DATABASE_URL` to be set, and emits structured
JSON logging suitable for a platform log drain. The generated `Procfile` invokes
this for you.

## Provisioning backing services

Provisioning is the operator's concern — use managed services or your own infra.
The app needs whatever `dazzle deploy plan` reports, typically:

| Service | When needed | Env var(s) |
|---------|-------------|-----------|
| PostgreSQL | Always, for any app with entities | `DATABASE_URL` |
| Redis / cache | When the app declares caching | as reported by `deploy plan` |
| Queue / workers | When the app declares async jobs or processes | as reported by `deploy plan` |
| Object storage | When the app stores files/assets | as reported by `deploy plan` |
| Ledger cluster | When the app declares `ledger` constructs | as reported by `deploy plan` |

Set every env var `deploy plan` lists; an app that boots without its required
connection details fails fast (`dazzle serve --production` requires
`DATABASE_URL`, for example).

## Ledgers (TigerBeetle)

The `ledger` construct and TigerBeetle as a backing store remain **first-class**
domain concepts (ADR-0015). An app that declares `ledger` constructs needs a
running **TigerBeetle cluster**:

```dsl
ledger CustomerWallet:
  account_code: 1001
  account_type: asset
  currency: GBP
```

Provision the cluster yourself and point the app at it. For production, run an
**odd node count** (1, 3, or 5) so the Raft consensus can achieve quorum — 3 nodes
tolerates 1 failure, 5 nodes tolerates 2. Dazzle no longer generates the cluster
infrastructure; `dazzle deploy plan` simply reports that the app requires a
TigerBeetle ledger cluster and which env vars carry its addresses.

## Containers / Kubernetes

The framework does not provide container images or Kubernetes manifests — roll
your own against the documented core process (`dazzle serve --production`) and the
requirements that `dazzle deploy plan` reports.

## Host-app lifecycle hooks

When your own code needs startup/shutdown work on the Dazzle app (connection
pools, auth caches, background clients), use the supported hook API:

```python
import dazzle

dazzle.register_lifespan_hook(app, startup=init_pool, shutdown=close_pool)
```

Hooks may be sync or async, run inside the framework's lifespan (after the DB pool
opens, so they can use the database), and shutdown hooks run in reverse order.

**Do not use `@app.on_event`.** Dazzle constructs the app with a custom
`lifespan=`, which makes Starlette skip the default lifespan — the only thing that
ever read the `on_event` lists. (Starlette 1.x removed the draining machinery
entirely; FastAPI keeps `on_event` only as a deprecated write-only shim.) As of
v0.82.24 (#1366) Dazzle drains those legacy handlers itself with original
semantics — a failed startup handler aborts boot — and logs a deprecation warning
per handler, so existing code works loudly rather than failing silently. Migrate
to `register_lifespan_hook`.

## Row-tenancy RLS roles (`tenancy: mode: shared_schema`)

When an app uses shared-schema row tenancy, the tenant boundary is enforced by
PostgreSQL Row-Level Security. **Enforcement only applies when the app connects as
a non-superuser, non-owner role** — superusers always bypass RLS, and the table
owner bypasses unless `FORCE ROW LEVEL SECURITY` (which Dazzle sets). So:

- **Provision three roles** (DDL generated by
  `dazzle.http.runtime.rls_schema.build_rls_role_ddl()`):
  - `dazzle_owner` — owns the schema, runs migrations (DDL is unaffected by RLS).
  - `dazzle_app` — the **runtime role** the app connects as. `LOGIN`, **no
    `BYPASSRLS`**. Subject to every policy.
  - `dazzle_bypass` — `BYPASSRLS`, for excision / cross-tenant ops only (never the
    app's request path).
- **Point the app's `DATABASE_URL` at `dazzle_app`** in production. If it connects
  as a superuser/owner, RLS is silently bypassed (data still isolated by the
  app-layer scope filters, but the DB-level guarantee is lost).
- The runtime sets `dazzle.tenant_id` per transaction from the authenticated
  user's tenant; an unset context **fails closed** (no rows; writes rejected).
  Tenant-scoped DB access therefore runs inside a transaction.
- **Local dev** typically connects as a superuser → RLS present but bypassed;
  app-layer scope filters enforce there. This is expected; production gets the
  DB-enforced fence via `dazzle_app`.
- **Applying the policies in production (Phase D):** `dazzle db upgrade` now
  **applies the RLS policies automatically after running migrations** (in
  `shared_schema` mode), using the same owner-capable role that ran the DDL — so a
  standard deploy (`dazzle db upgrade`) enforces RLS. You can also apply them
  explicitly with **`dazzle db apply-rls`** (run with an owner DATABASE_URL). Both
  are idempotent. **The apply must run as a role that OWNS the tables
  (`dazzle_owner` / your migration role) — not the runtime `dazzle_app`** (which
  lacks the privilege to create policies). Pass `--no-rls` to `dazzle db upgrade`
  to skip (e.g. if you apply RLS in a separate step); a failed apply after a
  successful migration exits non-zero with a "schema migrated but RLS NOT enforced
  — re-run `dazzle db apply-rls`" message.
- **Verifying RLS in CI/ops:** `dazzle db verify` now gates **RLS policy drift** (a
  tenant-scoped table with RLS disabled, or a missing/extra policy) and exits
  non-zero on drift. `dazzle inspect rls` shows the generated policy set per table
  (add `--runtime` to cross-reference live `pg_policies`).

## Secrets

Keep secrets (database passwords, API keys) out of the DSL and out of source
control — set them as environment variables / platform config vars on the host,
alongside the connection strings `dazzle deploy plan` reports.
