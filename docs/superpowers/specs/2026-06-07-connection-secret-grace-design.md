# SCIM Bearer Grace Window + Rotation Audit — Design

**Issue:** #1342 (enterprise auth) Phase 3 backlog — "connection secret rotation".
**Date:** 2026-06-07
**Status:** Approved (design), pending spec review.

## Problem

Connection secret rotation already ships (v0.81.56 `rotate-secret` CLI; v0.81.57
`rotate-encryption-key`). Both are **hard swaps**: rotating a SCIM bearer invalidates
the old bearer instantly, so the IdP's provisioning breaks until an operator races to
update the IdP config — a self-inflicted outage window, and pressure to do it fast.
The standard secure pattern (cf. AWS access-key rotation) is **overlap**: old + new both
valid for a bounded window, so the IdP migrates at its own pace, then the old credential
is revoked. Rotation is also **unaudited** — membership changes write append-only events,
but a secret rotation only bumps `updated_at`.

This increment adds (1) a **grace/overlap window for SCIM bearer rotation** and (2)
**append-only rotation audit events**.

## Scope

- **In:** SCIM-bearer grace window (mint new while old stays valid until expiry or explicit
  revoke); rotation audit events for rotate / revoke-previous / encryption-key-rewrap; CLI
  surface (`--grace`, `revoke-previous-secret`, `secret-history`); Alembic `0012` + `_init_db`
  mirror; encryption-key rewrap extended to cover the grace blob.
- **Out (by design):**
  - **OIDC grace.** Dazzle is the OAuth *client*; it presents `client_secret` to the IdP
    token endpoint, so the IdP arbitrates which secret is valid — Dazzle holding two doesn't
    help. `--grace` on an OIDC rotation is **refused**. OIDC rotation stays a hard swap.
  - **SAML.** No rotatable secret (public cert) — still refused entirely.
  - **HTTP/admin surface.** Rotation stays CLI/devops-only (the org-admin UI is deliberately
    secret-free). Audit is readable via CLI only.
  - **TTL auto-cleanup job.** Expiry is enforced at *verification* time (an expired previous
    bearer is ignored); no background reaper. Operators may `revoke-previous-secret` to clear
    eagerly; a future rotation overwrites it.

## Storage

**Two nullable columns on `connections`:**

| Column | Type | Meaning |
|--------|------|---------|
| `previous_encrypted_secret` | `TEXT` | AES-GCM blob of the *prior* secrets dict (same format as `encrypted_secret`: `encrypt_secret(json.dumps(secrets))`). `NULL` when no grace secret. |
| `previous_secret_expires_at` | `TEXT` | ISO-8601 UTC. The previous secret is honored **only while `now() < expires_at`**. `NULL` when no grace secret. |

**New append-only audit table `connection_secret_events`** (mirrors `membership_events`,
no hard FK to `connections` — matches the auth-store raw-SQL convention, and lets the audit
trail survive a connection delete):

```sql
CREATE TABLE IF NOT EXISTS connection_secret_events (
    id            TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL,
    tenant_id     TEXT NOT NULL,
    event         TEXT NOT NULL,          -- rotated | revoked_previous | encryption_key_rewrapped
    actor         TEXT,                   -- "cli" (no authenticated user on the CLI path)
    detail        TEXT NOT NULL DEFAULT '{}',  -- non-secret JSON context; NEVER a secret
    at            TEXT NOT NULL
)
-- ix_connection_secret_events_conn ON (connection_id)
```

`detail` examples: `{"type":"scim","grace":true,"grace_until":"2026-06-08T…Z"}` (rotated),
`{}` (revoked_previous), `{"from_key":"old"}` (rewrap). **No secret value ever lands in
`detail`** — only booleans, the connection type, and the grace-expiry timestamp.

## Schema change (dual-write, per ADR-0017 + existing mirror convention)

1. **Alembic `0012_connection_grace_secret.py`** (canonical), `down_revision = "0011"`:
   - `add_column` the two `connections` columns — **idempotent** via `inspect(bind)` column
     check (framework migrations must use `inspect`, not PG-only `to_regclass`).
   - `create_table('connection_secret_events', …)` guarded by `inspect(bind).has_table`.
   - `downgrade`: drop the table + the two columns.
2. **`_init_db` mirror** (store.py / `connections.py`):
   - Add the two columns to `CONNECTIONS_DDL` (fresh tables).
   - `ALTER TABLE connections ADD COLUMN IF NOT EXISTS previous_encrypted_secret TEXT` and
     `… previous_secret_expires_at TEXT` (existing auth-store DBs) — same pattern as the
     `sessions.csrf_secret` / `active_membership_id` columns.
   - `CREATE TABLE IF NOT EXISTS connection_secret_events …` + its index.

## New module `src/dazzle/back/runtime/auth/secret_rotation.py`

Pure, store-free helpers + constants:

```python
SECRET_EVENT_ROTATED = "rotated"
SECRET_EVENT_REVOKED_PREVIOUS = "revoked_previous"
SECRET_EVENT_KEY_REWRAPPED = "encryption_key_rewrapped"

_GRACE_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}

def parse_grace_duration(text: str) -> timedelta:
    """'24h' / '7d' / '30m' / '2w' -> timedelta. Raises ValueError on a bad/zero/negative
    duration. Single integer + single unit suffix (m/h/d/w); no compound forms."""
```

`parse_grace_duration` is deliberately local (not the DSL lexer's `parse_duration`) so the
auth store doesn't depend on the core parser. It accepts exactly `<positive-int><m|h|d|w>`.

## Store methods (store.py)

```python
def rotate_connection_secret(
    self, connection_id: str, new_secrets: dict[str, Any], *,
    grace: timedelta | None = None, actor: str | None = None,
    tenant_id: str | None = None,
) -> bool:
    """Rotate a connection's secret, optionally keeping the OLD one valid for `grace`.

    One transaction: reads current `encrypted_secret`; if `grace` is set, copies it to
    `previous_encrypted_secret` and sets `previous_secret_expires_at = now + grace`; else
    clears both previous_* (hard swap). Writes the new `encrypted_secret`, bumps
    `updated_at` (OIDC client-cache key), and appends a `rotated` audit event with
    non-secret detail. Returns True if a row changed. Tenant-fenced when `tenant_id` given.
    """

def revoke_previous_connection_secret(
    self, connection_id: str, *, actor: str | None = None, tenant_id: str | None = None,
) -> bool:
    """Clear `previous_encrypted_secret` + `previous_secret_expires_at` immediately and
    append a `revoked_previous` event. Returns True if a previous secret was cleared."""

def get_connection_secret_events(
    self, connection_id: str,
) -> list["ConnectionSecretEvent"]:
    """The append-only rotation history for one connection, newest first."""
```

`ConnectionSecretEvent` is a frozen dataclass in `connections.py` (`id, connection_id,
tenant_id, event, actor, detail: dict, at: datetime`).

### Verification with grace — `get_scim_connection_by_bearer`

Extend the existing constant-time scan: for each active SCIM connection, compare `token`
against the current `scim_bearer` **and** — when `previous_encrypted_secret` is present and
`previous_secret_expires_at` is in the future — against the decrypted previous bearer, both
via `hmac.compare_digest`. An expired or absent previous secret is ignored. The read path
stays read-only (no lazy cleanup of expired rows). The high-entropy-bearer argument that
already justifies the per-candidate timing signal still holds.

### Encryption-key rewrap covers the grace blob — `rewrap_all_connection_secrets`

`previous_encrypted_secret` is also AES-GCM ciphertext, so the key-rotation rewrap MUST
re-encrypt it too — otherwise a grace secret becomes undecryptable after a master-key
rotation (the old bearer would silently stop working before its window). Rewrap both blobs
per row; write an `encryption_key_rewrapped` audit event per connection actually rewrapped
(not for `already_current` rows). `failed` collection semantics unchanged.

## CLI (auth_connection.py)

- `rotate-secret <id>` gains `--grace <duration>` (default `""` = hard swap, current behavior):
  - `--grace` + non-SCIM connection → **error, exit 1** ("grace applies only to a SCIM bearer").
  - SCIM + `--grace 24h` → `parse_grace_duration` → `rotate_connection_secret(id,
    {"scim_bearer": new}, grace=td, actor="cli")`; print the new bearer once + "the previous
    bearer stays valid until `<expires_at>`".
  - No `--grace` → `rotate_connection_secret(…, grace=None)` (hard swap **+ audit event +
    previous cleared**). OIDC unchanged (hard swap, `--client-secret` still required).
- New `revoke-previous-secret <id>` → `revoke_previous_connection_secret(id, actor="cli")`;
  reports whether a grace secret was cleared.
- New `secret-history <id>` → table of `get_connection_secret_events` (at, event, actor, detail).

## Testing

- **Unit** `test_secret_rotation.py`: `parse_grace_duration` valid units + reject
  garbage/zero/negative/compound.
- **Unit CLI** `test_auth_connection_cli.py`: `--grace` on SCIM reports old-valid-until;
  `--grace` on OIDC refused (exit 1); `revoke-previous-secret`; `secret-history` lists events.
- **Postgres integration** `test_connections_pg.py`:
  - rotate-with-grace → both old and new bearer authenticate via `get_scim_connection_by_bearer`.
  - expiry → set `previous_secret_expires_at` in the past → old bearer rejected, new still works.
  - `revoke_previous_connection_secret` → old bearer rejected immediately.
  - audit rows written for `rotated` (grace=true/false) and `revoked_previous`.
  - encryption-key rewrap re-encrypts the previous blob: rotate-with-grace, then rotate the
    master key + rewrap, then BOTH bearers still authenticate; a `encryption_key_rewrapped`
    event is recorded.
  - hard-swap rotate (no grace) clears any prior previous_* and writes a `rotated` event.
- **Migration** `test_migration_0012_applies_on_a_pre_0012_db` (mirrors the 0007/SCIM test):
  drop to pre-0012, apply, assert the columns + table exist and a pre-existing connection
  survives.

## Docs

`docs/reference/enterprise-sso.md` rotation section: document `--grace`,
`revoke-previous-secret`, `secret-history`, the SCIM-only scope, and that an expired previous
bearer is rejected at verification. CHANGELOG `Added` (grace + audit + commands) / `Changed`
(rewrap now covers the grace blob; rotate now writes an audit event) + an Agent Guidance bullet
(rotation is audited; grace is SCIM-only). `/bump patch` → v0.81.78.

## Execution

Security-sensitive auth → **Hybrid**: implement inline, then an independent adversarial
review (as with SCIM /Groups) before ship. Verify the full `-m postgres` job + the non-e2e
suite (touches a migration + the auth store, so the postgres slice is mandatory per the
pre-ship test-scope rule).

## Failure-mode notes (per CLAUDE.md review rule)

- **Which mode this risks:** semantic-drift / hidden-state — a grace window is invisible
  state that keeps an "old" credential alive. Mitigation: it's explicit (operator opts in
  with `--grace`), bounded (`expires_at`), auditable (`connection_secret_events`), and
  revocable (`revoke-previous-secret`).
- **Detector:** the postgres integration tests assert both the overlap *and* the expiry/
  revoke kill-paths; the audit trail makes the state inspectable.
- **Live:** the tests run in the CI `-m postgres` job.
- **Traceable:** every state change writes an append-only event with non-secret detail.
- **Semantics preserved:** auth stays in the auth store; no secret leaves it in plaintext;
  verification stays constant-time and fail-closed.
