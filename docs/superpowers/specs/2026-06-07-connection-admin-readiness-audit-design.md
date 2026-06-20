# Org-admin connection surface: readiness panel + rotation audit — Design

**Issue:** #1342 (enterprise auth) Phase 3 backlog — "in-app org-admin connection surface".
**Date:** 2026-06-07
**Status:** Approved (design), pending spec review.

## Problem

The org-admin connection surface (`GET /auth/connections` + `add-domain` / `verify-domain`)
already ships: RBAC-gated (`org_admin_roles` + `may_manage_members`), org-scoped (cross-org →
404), CSRF-protected, capability-gated, typed-Fragment rendered, **secret-free** (domains +
status only). What an org admin still can't see in-app:

1. **Why a connection isn't live yet** — the activation readiness that today only `dazzle auth
   connection doctor` (devops CLI) reports.
2. **Secret-rotation history** — the `connection_secret_events` audit shipped in v0.81.78 is
   CLI-only (`secret-history`).

Both are read-only and **secret-free** (presence/booleans/timestamps, never a secret value),
so they fit the surface's existing boundary. This increment surfaces both into the page.

## Scope

- **In:** a per-connection readiness panel (reusing `connection_doctor.diagnose_connection`),
  a per-connection rotation audit list (last 5 `connection_secret_events`), and a grace-window
  indicator. All on the existing `GET /auth/connections` page — **no new route, no capability
  change, no RBAC change**.
- **Out (unchanged by design):** connection create/edit/delete, secret rotation triggers, and
  grace **revoke** stay in the operator CLI (secret I/O or destructive — outside the secret-free
  read+domains boundary). The panel is read-only status; it does not add action buttons.

## Architecture

The existing `connections_page` handler builds a per-connection dict and passes a list to
`build_connections_view`. This change adds three secret-free fields to each dict and renders
them in `_connection_block`. The handler already iterates **only** `get_connections_for_tenant(
org_id)`, so every new read is org-fenced for free.

### 1. Readiness panel — reuse `connection_doctor`

- Extract the CLI's `_env_flags()` into a shared **`environment_flags() -> tuple[bool, bool,
  bool]`** in `src/dazzle/http/runtime/auth/connection_doctor.py` (runtime). The CLI
  `_env_flags()` becomes a thin call to it (single source of truth; the route can't import the
  CLI, so the shared helper must live in the runtime module).
- The handler computes `flags = environment_flags()` **once** before the loop, then per
  connection calls `diagnose_connection(conn, secret_key_ok=flags[0], sso_extra_ok=flags[1],
  dns_extra_ok=flags[2])` (the exact function the CLI `doctor` uses — no drift).
- It projects the `Diagnosis` into the view dict as secret-free primitives:
  `{"ready": diag.ready, "checks": [{"name": c.name, "ok": c.status == "ok", "detail": c.detail}
  for c in diag.checks if c.level == "required"], "next_steps": list(diag.next_steps)}`.
  `Check.detail`/`next_steps` are presence statements + remedies — **never a secret value**
  (doctor's existing contract).
- Defensive: wrap the per-connection `diagnose_connection` in `try/except
  ConnectionSecretError` → readiness `{"ready": False, "checks": [], "next_steps": ["The
  operator must set DAZZLE_CONNECTION_SECRET to assess readiness."]}` so a missing/rotated key
  degrades gracefully instead of 500ing the page.

### 2. Rotation audit list — consume `connection_secret_events`

- Per connection: `events = store.get_connection_secret_events(conn.id)[:5]` — fetched **only**
  for org-owned connections (the loop is already `get_connections_for_tenant(org_id)`), so
  org-scoping fences it; no cross-org read is possible.
- Project to secret-free dicts: `{"at": e.at.isoformat()/str, "event": e.event, "actor":
  e.actor or "-", "grace_until": e.detail.get("grace_until")}`. Event names + timestamps only.

### 3. Grace-window indicator

- New store read **`get_connection_grace_status(connection_id) -> tuple[bool, str | None]`**:
  reads `previous_secret_expires_at` (a timestamp, not a secret); returns
  `(active = parse(exp) > now(UTC), exp)` or `(False, None)` when absent. Used to render
  "Grace window active until X" on the connection block. Read-only — revoking stays CLI.

### View (`connection_admin_views.py`)

`_connection_block` gains, after the domain controls:
- A **Readiness** sub-section: a `Badge("Activation-ready ✓" / "Not activation-ready",
  variant default/warning)`, then one `Text` per required check (`✓`/`✗` + name + detail), then
  a muted `Text` "What's left:" list of `next_steps` when not ready.
- A **Grace** `Badge`/`Text` "Grace window active until {expires_at}" when `grace.active`.
- A **Secret-rotation history** sub-section: a muted `Text` per event
  (`{at}  {event}  ({actor})` + `→ grace until {grace_until}` when present), or "No rotation
  events yet." when empty.

The handler passes the new fields through; the view consumes `conn["readiness"]`,
`conn["grace"]`, `conn["events"]`. No new Fragment primitives needed (reuses `Badge`/`Text`).

## Data flow

```
connections_page (RBAC gate → org_id)
  flags = environment_flags()                      # once
  for conn in store.get_connections_for_tenant(org_id):   # org-fenced
      ... existing domain dict ...
      readiness = project(diagnose_connection(conn, *flags))   # secret-free
      events    = project(store.get_connection_secret_events(conn.id)[:5])
      grace     = store.get_connection_grace_status(conn.id)
  build_connections_view(... connections=[dict + readiness/events/grace ...])
  FragmentRenderer().render(page)  → HTMLResponse
```

## Files

| File | Change |
|------|--------|
| `src/dazzle/http/runtime/auth/connection_doctor.py` | add `environment_flags()` (moved from CLI) |
| `src/dazzle/cli/auth_connection.py` | `_env_flags()` → calls shared `environment_flags()` |
| `src/dazzle/http/runtime/auth/store.py` | add `get_connection_grace_status()` |
| `src/dazzle/http/runtime/auth/connection_admin_routes.py` | gather readiness/events/grace per connection |
| `src/dazzle/http/runtime/auth/connection_admin_views.py` | render readiness panel + audit list + grace badge |
| `tests/integration/test_connection_admin_routes.py` | new tests (below) |
| `docs/reference/enterprise-sso.md`, `CHANGELOG.md` | docs + changelog; `/bump patch` → v0.81.79 |

## Testing

Extend the existing fake `_Store` with `get_connection_secret_events(cid)` and
`get_connection_grace_status(cid)`. New tests in `test_connection_admin_routes.py`:

- **`test_page_shows_readiness`** — admin sees a readiness badge + at least one required check
  for their connection.
- **`test_page_shows_rotation_history`** — a connection with seeded events renders the event
  names + timestamps (e.g. "rotated", the date).
- **`test_page_shows_grace_window_when_active`** — `get_connection_grace_status` → `(True,
  <future>)` renders "Grace window active until …".
- **`test_readiness_and_audit_never_leak_secret`** — connection with `client_secret =
  "SUPER-SECRET"` + a seeded event whose detail has `grace_until` → assert the secret value and
  any bearer string are absent from the rendered HTML (extends the existing secret-free pin).
- **`test_page_degrades_when_key_missing`** — `environment_flags` reports `secret_key_ok=False`
  (or `diagnose_connection` raises `ConnectionSecretError`) → page still 200s with a
  "set DAZZLE_CONNECTION_SECRET" readiness note, not a 500.
- **`test_audit_is_org_scoped`** — confirm the handler only reads events for connections in the
  caller's org (a second-org connection's events are never fetched/rendered). Mirrors the
  existing `test_page_only_shows_active_orgs_connections`.

`environment_flags()` gets a tiny unit test (key present/absent → flag) in the CLI/doctor test
file. The store method is covered in `tests/integration/test_connections_pg.py`
(`get_connection_grace_status` returns active/expiry after a `--grace` rotation and `(False,
None)` after revoke/none).

## Docs

`docs/reference/enterprise-sso.md`: note the org-admin page now shows per-connection activation
readiness (mirrors `doctor`) and a read-only secret-rotation history (still secret-free).
CHANGELOG `Added` + an Agent Guidance bullet (readiness panel reuses `diagnose_connection`;
audit view is read-only/secret-free; rotation/revoke stay CLI).

## Execution

UI over auth data — lower risk than the rotation core, but still an independent review focused
on: (a) the **secret-free invariant** (no secret/bearer in the rendered HTML via any new path —
readiness `detail`, event `detail`, grace), and (b) **org-scoping of the audit read** (no
cross-org event leak). Hybrid: implement inline, review, ship. Run the non-e2e suite + the
`-m postgres` slice (store method + auth surface).

## Failure-mode notes (per CLAUDE.md review rule)

- **Mode risked:** information disclosure (a UI path that accidentally renders a secret) and
  semantic drift (a UI readiness that disagrees with the CLI `doctor`).
- **Detector:** the secret-free render test + reusing the *same* `diagnose_connection` the CLI
  uses (drift impossible by construction).
- **Live:** tests run in CI (`test_connection_admin_routes.py` is collected in the non-e2e
  suite; the store method in the `-m postgres` job).
- **Traceable:** readiness traces to `connection_doctor`; audit to `connection_secret_events`.
- **Semantics preserved:** secrets stay in the store, never rendered; org-scoping unchanged.
