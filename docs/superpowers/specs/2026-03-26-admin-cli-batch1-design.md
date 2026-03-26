# Admin CLI Commands — Batch 1 Design

**Issue:** #695
**Date:** 2026-03-26
**Status:** Draft
**Scope:** flush-sessions, impersonate, rotate-passwords, dbshell

## Summary

Four high-priority admin CLI commands that solve daily-driver operations: session management, impersonation for debugging, bulk password rotation, and zero-config database access. All build on existing AuthStore infrastructure with minimal new code.

Batch 2 (routes listing, maintenance mode) is deferred — different architectural concerns.

## Key Decisions

1. **Magic link as a reusable primitive** — `impersonate --url` generates a one-time login token. Same mechanism supports future passwordless email login, API-driven session creation, and Playwright test automation.
2. **dbshell is top-level** — `dazzle dbshell`, not `dazzle db shell`. It's a daily-driver command like `dazzle serve`.
3. **DATABASE_URL resolution unchanged** — uses existing chain (dazzle.toml → env var → default). Environment profiles (#718) will enrich this later.
4. **All commands support --json** — consistent with existing auth CLI pattern.

## Commands

### 1. `dazzle auth flush-sessions`

```bash
dazzle auth flush-sessions --yes           # All sessions (requires confirm)
dazzle auth flush-sessions --expired       # Only expired (no confirm needed)
dazzle auth flush-sessions --user EMAIL    # One user's sessions
```

**Implementation:** Add command to `src/dazzle/cli/auth.py`.

| Flag | AuthStore Method | Confirm? |
|------|-----------------|----------|
| (no flags / --yes) | `delete_all_sessions()` (new) | Yes |
| `--expired` | `cleanup_expired_sessions()` (exists) | No |
| `--user EMAIL` | `delete_user_sessions(user_id)` (exists) | No |

New AuthStore method:
```python
def delete_all_sessions(self) -> int:
    """Delete all sessions. Returns count deleted."""
    # DELETE FROM sessions RETURNING (count via rowcount)
```

Output: `{"deleted": N}` or `Deleted N sessions.`

### 2. `dazzle auth impersonate`

```bash
dazzle auth impersonate teacher@school.uk           # Print session cookie
dazzle auth impersonate teacher@school.uk --url     # Print one-time login URL
dazzle auth impersonate teacher@school.uk --ttl 5m  # Short-lived session
```

**CLI command** in `src/dazzle/cli/auth.py`:
1. Resolve user via `_resolve_user()` (existing)
2. Cookie mode (default): `create_session(user, expires_in=ttl)`, print cookie value
3. URL mode (`--url`): Create magic link, print URL
4. Log audit event: `"CLI impersonation of {email} by {hostname}"`

**Magic link primitive** (`src/dazzle_back/runtime/auth/magic_link.py`):

New module with:
- `create_magic_link(store, user_id, ttl, created_by) -> str` — generates token, stores in `magic_links` table, returns token
- `validate_magic_link(store, token) -> user_id | None` — checks exists, not expired, not used; marks `used_at`

New table `magic_links`:
```sql
CREATE TABLE IF NOT EXISTS magic_links (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by TEXT
)
```

Created in AuthStore's `_ensure_tables()` method (same pattern as users/sessions tables).

Token: `secrets.token_urlsafe(32)` — 43-char URL-safe string. Default TTL: 5 minutes.

**Runtime route** (`/_auth/magic/<token>`):
- Registered in auth subsystem startup
- Validates token via `validate_magic_link()`
- Creates session via `create_session()`
- Sets `dazzle_session` cookie
- Redirects to `/`
- Invalid/expired/used token: returns 403 with error message

### 3. `dazzle auth rotate-passwords`

```bash
dazzle auth rotate-passwords --all --generate --yes
dazzle auth rotate-passwords --all --password new-pw --yes
dazzle auth rotate-passwords --role teacher --generate --yes
```

**Implementation:** Add command to `src/dazzle/cli/auth.py`.

Flow:
1. Resolve users: `--all` → `list_users()`, `--role X` → `list_users(role=X)`
2. Require `--yes` confirmation
3. For each user: generate or use explicit password, `update_password()`, `delete_user_sessions()`
4. Output table: email, new password (only with `--generate`), sessions revoked

Requires `--generate` or `--password` (mutually exclusive, one required). Uses existing `_generate_temp_password()` for `--generate`.

No new AuthStore methods — composes existing `list_users()`, `update_password()`, `delete_user_sessions()`.

### 4. `dazzle dbshell`

```bash
dazzle dbshell                     # Interactive psql
dazzle dbshell -c "SELECT ..."     # Single query
dazzle dbshell --read-only         # Read-only transaction
```

**Implementation:** New file `src/dazzle/cli/dbshell.py`, registered as top-level command.

Flow:
1. Resolve DATABASE_URL via `resolve_database_url()` (existing)
2. Check `psql` on PATH — error with install instructions if missing
3. Build args: `["psql", database_url]`
4. `-c` → append `["-c", query]`
5. `--read-only` → append `["-v", "default_transaction_read_only=on"]`
6. `subprocess.run(args)` — pass through stdin/stdout

## File Changes

| File | Action | Content |
|------|--------|---------|
| `src/dazzle/cli/auth.py` | Modify | Add flush-sessions, impersonate, rotate-passwords commands |
| `src/dazzle_back/runtime/auth/store.py` | Modify | Add `delete_all_sessions()` method to SessionStoreMixin |
| `src/dazzle_back/runtime/auth/magic_link.py` | Create | Magic link token creation, validation, table DDL |
| `src/dazzle/cli/dbshell.py` | Create | dbshell command |
| `src/dazzle/cli/__init__.py` | Modify | Register dbshell command |
| `tests/unit/test_admin_commands.py` | Create | Tests for flush-sessions, impersonate, rotate-passwords |
| `tests/unit/test_dbshell.py` | Create | Tests for dbshell argument building |
| `tests/unit/test_magic_link.py` | Create | Tests for magic link token lifecycle |

## Testing Strategy

| Component | Test Approach | Key Cases |
|-----------|--------------|-----------|
| `flush-sessions` | Mock AuthStore | All 3 modes; --yes confirm; JSON output |
| `impersonate` | Mock AuthStore | Cookie format; --url token; --ttl parsing; user not found |
| `magic_link.py` | Mock DB cursor | Token uniqueness; expiry; single-use; used_at marking |
| Magic link route | Mock store | Valid → cookie + redirect; expired → 403; reused → 403 |
| `rotate-passwords` | Mock AuthStore | --all vs --role; --generate vs --password; sessions revoked |
| `dbshell` | Mock subprocess | Args correct; -c flag; --read-only; psql missing error |

## Follow-Up

- Batch 2: `dazzle routes` + `dazzle down`/`up` (maintenance mode) — separate spec
- Environment profiles (#718) — `--env` flag for all commands
- Magic link reuse: passwordless email login, API-driven session creation
