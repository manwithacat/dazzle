# M2 — complete case-insensitive `users.email` uniqueness — Design

**Issue:** #1342 (enterprise auth deferred backlog), item **M2** — "store hardening: case-insensitive `users.email`".

## Status going in

M2's **structural core already shipped**: `AuthStore._ensure_email_ci_uniqueness` creates the functional unique index `users_email_lower_key ON users (LOWER(email))` with a loud collision pre-flight (raises an actionable `RuntimeError` if pre-existing rows collide on `LOWER(email)`), wired into boot after `_init_db`, covered by `test_email_case_insensitive_uniqueness` + `test_email_ci_uniqueness_preflight_reports_collisions`.

So the security invariant — "a second row differing only by case is structurally rejected" — already holds. This slice **completes** M2 by closing two residual gaps, not re-doing the core.

## Gap 1 — Alembic parity mirror (required by the dual-write rule)

The index lives only in `_init_db`. Per [[project_authstore_alembic_parity]] the auth schema is dual-written: `_init_db` (primary) **and** a guarded Alembic mirror. `users_email_lower_key` has no mirror, so an Alembic-only provisioning path (or a future single-source consolidation) would miss it.

**Add** a new migration `0015_users_email_ci_unique.py` (down_revision `0014_memberships_external_id_unique`) that:
- Guards on `users` table existence (`_has_table`).
- Runs the **same collision pre-check** before creating the index — but as a *migration*, a collision must fail the upgrade loudly (data integrity), consistent with `_ensure_email_ci_uniqueness`.
- `CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))` — byte-identical DDL to `_init_db` (the parity gate's contract).
- `downgrade` drops the index.

Idempotent: a DB already bootstrapped by `_init_db` no-ops (the `IF NOT EXISTS` + the collision check passes on clean data).

Extend `test_authstore_alembic_parity_pg.py` to assert `users_email_lower_key` is present after `_init_db` + `alembic upgrade head`, and that head is now `0015`.

## Gap 2 — Normalize email at the store chokepoint

`create_user` and `get_user_by_email` operate on `email` verbatim; lowercasing is a caller convention. The index prevents the *split* but not the *surprise*: a mixed-case first insert (`Foo@x.com`) stores mixed-case, then a convention-following lowercased lookup misses it, and the re-create trips a raw `IntegrityError`. Make the store the enforcement point so the invariant holds regardless of caller.

**Change** (single normalization helper `_normalize_email(email) -> str` = `(email or "").strip().lower()`):
- `create_user`: normalize `email` before constructing `UserRecord` / INSERT. Storage becomes canonical-lowercase.
- `get_user_by_email`: normalize the argument before the `WHERE email = %s` lookup, so any-case input finds the canonical row.
- `authenticate` benefits transitively (it calls `get_user_by_email`).

This is idempotent for the SCIM/OIDC/SAML JIT paths (they already lowercase) and backward-compatible: all existing rows are already lowercase by convention, so no data migration is needed. The functional index remains the structural backstop for **raw-SQL** paths that bypass `create_user` (excision, provisioning fixtures, tests).

### Test impact

`test_email_case_insensitive_uniqueness` currently asserts the **functional** index (`users_email_lower_key`) fires on `create_user("SPLIT@…")` after `create_user("split@…")`. Once `create_user` normalizes, both rows store the identical lowercased string, so the **plain** `email UNIQUE` (`users_email_key`) fires first and the assertion on `users_email_lower_key` breaks. Rework the test to keep proving the *structural* backstop honestly: insert the mixed-case duplicate via **raw SQL** (bypassing normalization) and assert `users_email_lower_key` rejects it — that is exactly the non-normalizing-path threat the functional index exists for. Add a separate assertion that `create_user` normalizes (store `Foo@x.com` → `get_user_by_email("foo@x.com")` finds it; `get_user_by_email("FOO@X.COM")` finds it too).

## Non-goals

- **CITEXT extension** — rejected; the functional `LOWER(email)` index needs no extension and no column-type change (lower migration risk, matches what already shipped).
- No change to the **DSL User entity** table lookup (`_load_domain_user_attributes`, a different app-owned table) — out of scope.
- No data backfill — existing rows are already lowercase by convention; the pre-flight would fail loud if not.

## Verification

- `pytest src/dazzle/http/tests/test_auth.py -m postgres` (reworked + new normalization tests, against real PG).
- `pytest tests/integration/test_authstore_alembic_parity_pg.py -m postgres` (head 0015 + index present).
- Pre-ship drift/policy gates + the auth-store↔alembic completeness gate.
