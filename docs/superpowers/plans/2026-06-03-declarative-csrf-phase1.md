# Declarative CSRF — Phase 1: Session-Bound Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `dazzle_csrf` token a property of the server-side session — minted with the session, reset on login, cleared on logout — replacing the free-floating random cookie that is independent of the auth session.

**Architecture:** Add a `csrf_secret` column to the `sessions` table and a matching field on the frozen `SessionRecord`. The login route sets the `dazzle_csrf` cookie to `session.csrf_secret`; logout clears it. Double-submit validation semantics (`header == cookie`) are unchanged in this phase — Phase 1 only changes *where the token comes from* (the session) and *when it rotates* (session lifecycle), which is the foundation Phases 2–4 build on.

**Tech Stack:** Python 3.12, Pydantic v2 (frozen models), psycopg/PostgreSQL, Alembic (ADR-0017), FastAPI.

**Spec:** `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md` §4.3.

---

## Scope boundary (read first)

- **In scope:** session-bound secret; cookie derived from it at login; cleared at logout; persisted/loaded in the store; Alembic migration + idempotent bootstrap; a `regenerate_session_csrf` store primitive with a test.
- **Out of scope (deferred, with rationale):** *mid-session* privilege-change rotation (role change without re-login). Dazzle re-derives roles from `UserRecord` on every `validate_session`, so authorization is always current regardless of the CSRF token; the residual concern is only token-fixation across a privilege boundary, which Phase 4 addresses when it enumerates the privilege-elevation call-sites (spec §9). Login already mints a fresh secret per session, so login/logout rotation is delivered here.
- **Validation unchanged:** the middleware still checks `header == cookie`. Binding the *validation* to the stored secret (reject a cookie that doesn't equal `session.csrf_secret`) is Phase 2/3, when the middleware resolves the session. Do **not** add session-lookup to the middleware in this phase.

## Files

- **Modify** `src/dazzle/http/runtime/auth/models.py` (`SessionRecord`, ~line 40) — add `csrf_secret` field.
- **Create** `src/dazzle/http/alembic/versions/0005_session_csrf_secret.py` — add the column.
- **Modify** `src/dazzle/http/runtime/auth/store.py` — bootstrap `CREATE TABLE` (~675), `create_session` INSERT (~462), `get_session` SELECT mapping (~491); add `regenerate_session_csrf`.
- **Modify** `src/dazzle/http/runtime/auth/routes.py` — set `dazzle_csrf` at login (~137), clear at logout (~174).
- **Test** `src/dazzle/http/tests/test_auth.py` (store/model tests) and a new `tests/unit/test_csrf_session_binding_phase1.py` (cookie behaviour).

---

### Task 1: Add `csrf_secret` to `SessionRecord`

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py:40-50`
- Test: `tests/unit/test_csrf_session_binding_phase1.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_csrf_session_binding_phase1.py
"""Phase 1 of the declarative-CSRF spec: the token is session-bound."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dazzle.http.runtime.auth.models import SessionRecord


def _session() -> SessionRecord:
    return SessionRecord(
        user_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


class TestSessionRecordCsrfSecret:
    def test_session_record_has_csrf_secret(self) -> None:
        s = _session()
        assert isinstance(s.csrf_secret, str) and len(s.csrf_secret) >= 32

    def test_csrf_secret_is_unique_per_session(self) -> None:
        assert _session().csrf_secret != _session().csrf_secret
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py -v`
Expected: FAIL — `SessionRecord` has no attribute `csrf_secret`.

- [ ] **Step 3: Add the field**

In `models.py`, inside `SessionRecord` (after `user_agent`):

```python
    user_agent: str | None = None
    # Declarative-CSRF Phase 1: the CSRF token is the session's own secret,
    # minted with the session and rotated only on session lifecycle events
    # (login/logout). See docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    csrf_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
```

(`secrets` and `Field` are already imported at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/models.py tests/unit/test_csrf_session_binding_phase1.py
git commit -m "feat(csrf): session-bound csrf_secret on SessionRecord (Phase 1)"
```

---

### Task 2: Alembic migration + idempotent bootstrap for the column

**Files:**
- Create: `src/dazzle/http/alembic/versions/0005_session_csrf_secret.py`
- Modify: `src/dazzle/http/runtime/auth/store.py:675-682` (bootstrap `CREATE TABLE`)
- Test: `tests/unit/test_csrf_session_binding_phase1.py`

- [ ] **Step 1: Write the failing test (migration is idempotent + adds the column)**

Append to `tests/unit/test_csrf_session_binding_phase1.py`:

```python
import importlib.util
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "src/dazzle/http/alembic/versions/0005_session_csrf_secret.py"
    )
    spec = importlib.util.spec_from_file_location("m0005", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigration0005:
    def test_revision_chain(self) -> None:
        m = _load_migration()
        assert m.revision == "0005_session_csrf_secret"
        assert m.down_revision == "0004_widen_alembic_version_num"

    def test_upgrade_adds_column_idempotently(self) -> None:
        """upgrade() adds csrf_secret and is safe to run twice."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine = sa.create_engine("sqlite://")
        with engine.connect() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, "
                    "created_at TEXT, expires_at TEXT, ip_address TEXT, user_agent TEXT)"
                )
            )
            ctx = MigrationContext.configure(conn)
            m = _load_migration()
            with Operations.context(ctx):
                m.upgrade()
                m.upgrade()  # second run must not raise (idempotent)
            cols = {c["name"] for c in sa.inspect(conn).get_columns("sessions")}
            assert "csrf_secret" in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py::TestMigration0005 -v`
Expected: FAIL — migration file does not exist.

- [ ] **Step 3: Create the migration**

```python
# src/dazzle/http/alembic/versions/0005_session_csrf_secret.py
"""Add csrf_secret to sessions (declarative-CSRF Phase 1).

Revision ID: 0005_session_csrf_secret
Revises: 0004_widen_alembic_version_num
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0005_session_csrf_secret"
down_revision = "0004_widen_alembic_version_num"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # Idempotent: framework migrations may re-run on a partially-migrated tree
    # (see memory: framework migrations must guard with the inspector, not
    # PG-only to_regclass, so they work on the test SQLite path too).
    if _has_column("sessions", "csrf_secret"):
        return
    # Backfill existing rows with a fresh per-row secret so sessions predating
    # this column still present a valid token; NOT NULL after backfill.
    op.add_column("sessions", sa.Column("csrf_secret", sa.Text(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM sessions")).fetchall()
    for (sid,) in rows:
        bind.execute(
            sa.text("UPDATE sessions SET csrf_secret = :s WHERE id = :id"),
            {"s": secrets.token_urlsafe(32), "id": sid},
        )


def downgrade() -> None:
    if _has_column("sessions", "csrf_secret"):
        op.drop_column("sessions", "csrf_secret")
```

- [ ] **Step 4: Update the bootstrap `CREATE TABLE`**

In `store.py`, change the sessions bootstrap (lines 675-682) to include the column:

```python
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    csrf_secret TEXT
                )
```

(Fresh installs get the column from the bootstrap; existing DBs get it from migration 0005. Both paths converge — the bootstrap uses `IF NOT EXISTS` so it never fights the migration.)

- [ ] **Step 5: Run the migration test**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py::TestMigration0005 -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/alembic/versions/0005_session_csrf_secret.py \
        src/dazzle/http/runtime/auth/store.py \
        tests/unit/test_csrf_session_binding_phase1.py
git commit -m "feat(csrf): alembic 0005 + bootstrap add sessions.csrf_secret (Phase 1)"
```

---

### Task 3: Persist and load `csrf_secret` in the store

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py:462-484` (`create_session` INSERT)
- Modify: `src/dazzle/http/runtime/auth/store.py:486-500` (`get_session` SELECT mapping)
- Modify: `src/dazzle/http/runtime/auth/store.py` (new `regenerate_session_csrf`)
- Test: `src/dazzle/http/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `src/dazzle/http/tests/test_auth.py` (follow the existing store-fixture pattern in that file; it already constructs a store against a test DB):

```python
def test_create_session_persists_csrf_secret(auth_store, sample_user):
    session = auth_store.create_session(sample_user)
    loaded = auth_store.get_session(session.id)
    assert loaded is not None
    assert loaded.csrf_secret == session.csrf_secret
    assert len(loaded.csrf_secret) >= 32


def test_regenerate_session_csrf_changes_secret(auth_store, sample_user):
    session = auth_store.create_session(sample_user)
    new_secret = auth_store.regenerate_session_csrf(session.id)
    assert new_secret != session.csrf_secret
    assert auth_store.get_session(session.id).csrf_secret == new_secret
```

(Reuse whatever `auth_store` / `sample_user` fixtures `test_auth.py` already defines. If the fixture names differ, match the file's existing convention rather than inventing new ones.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/dazzle/http/tests/test_auth.py -k csrf -v`
Expected: FAIL — `get_session` returns a record whose `csrf_secret` came from the model default (mismatch), and `regenerate_session_csrf` does not exist.

- [ ] **Step 3: Wire the INSERT**

In `create_session`, change the INSERT (lines 469-482) to include the column:

```python
        self._execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at, ip_address, user_agent, csrf_secret)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.id,
                str(session.user_id),
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.ip_address,
                session.user_agent,
                session.csrf_secret,
            ),
        )
```

- [ ] **Step 4: Wire the SELECT mapping**

In `get_session`, map the column (lines 491-498):

```python
            return SessionRecord(
                id=row["id"],
                user_id=UUID(row["user_id"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
                csrf_secret=row["csrf_secret"],
            )
```

- [ ] **Step 5: Add `regenerate_session_csrf`**

Add this method to the store class (next to `get_session`):

```python
    def regenerate_session_csrf(self, session_id: str) -> str:
        """Mint a fresh CSRF secret for an existing session and return it.

        Used to rotate the token within a session lifecycle without forcing a
        full re-login (Phase 4 privilege-change call sites; Phase 1 ships the
        primitive). Returns the new secret.
        """
        new_secret = secrets.token_urlsafe(32)
        self._execute(
            "UPDATE sessions SET csrf_secret = %s WHERE id = %s",
            (new_secret, session_id),
        )
        return new_secret
```

(`secrets` is imported at the top of `store.py`; if not, add `import secrets`.)

- [ ] **Step 6: Run tests**

Run: `python -m pytest src/dazzle/http/tests/test_auth.py -k csrf -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py src/dazzle/http/tests/test_auth.py
git commit -m "feat(csrf): persist+load+regenerate sessions.csrf_secret in store (Phase 1)"
```

---

### Task 4: Derive the `dazzle_csrf` cookie from the session at login; clear at logout

**Files:**
- Modify: `src/dazzle/http/runtime/auth/routes.py:137-145` (login `set_cookie`)
- Modify: `src/dazzle/http/runtime/auth/routes.py:151-175` (`_logout`)
- Test: `tests/unit/test_csrf_session_binding_phase1.py`

- [ ] **Step 1: Read the login handler to find the `session` and `response` in scope**

Run: `sed -n '108,150p' src/dazzle/http/runtime/auth/routes.py`
Confirm the handler has built `session` (the `SessionRecord` from `create_session`) and a `response` object before line 137. Use those exact names.

- [ ] **Step 2: Write the failing test (login sets dazzle_csrf to the session secret; logout clears it)**

Add to `tests/unit/test_csrf_session_binding_phase1.py`. Use the project's existing app-boot/test-client fixture for the auth routes (search `tests/` and `src/dazzle/http/tests/` for the FastAPI `TestClient` auth fixture — e.g. `client` / `app_client` — and reuse it rather than constructing a new app):

```python
class TestLoginCookie:
    def test_login_sets_dazzle_csrf_to_session_secret(self, auth_client, registered_user):
        resp = auth_client.post(
            "/auth/login",
            json={"email": registered_user.email, "password": registered_user.password},
        )
        assert resp.status_code == 200
        csrf = resp.cookies.get("dazzle_csrf")
        assert csrf and len(csrf) >= 32
        # It must equal the session's stored secret, not a random middleware value.
        sid = resp.cookies.get(auth_client.app.state.auth_deps.cookie_name)
        assert sid is not None

    def test_logout_clears_dazzle_csrf(self, auth_client, registered_user):
        auth_client.post(
            "/auth/login",
            json={"email": registered_user.email, "password": registered_user.password},
        )
        resp = auth_client.post("/auth/logout")
        assert resp.status_code in (200, 204)
        # delete_cookie emits an expiry; the cookie is no longer set to a live value.
        assert resp.cookies.get("dazzle_csrf", "") == ""
```

(Match the real fixture names — `auth_client`, `registered_user`, and the cookie-name accessor — to whatever the auth test module already exposes. If the project has no such fixture, model it on the `TestClient` setup in `src/dazzle/http/tests/test_auth.py`.)

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py::TestLoginCookie -v`
Expected: FAIL — `dazzle_csrf` is either absent or a random value not tied to the session.

- [ ] **Step 4: Set the cookie at login**

Immediately after the existing auth-cookie `response.set_cookie(...)` at line 137, add the CSRF cookie (note `httponly=False` — JS/htmx must read it; this mirrors the middleware's current cookie flags):

```python
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )
```

(`cookie_secure` and `deps` are already in scope at line 137 — they are used by the adjacent auth-cookie call.)

- [ ] **Step 5: Clear the cookie at logout**

In `_logout` (after the existing `response.delete_cookie(name)` loop around line 174), add:

```python
    response.delete_cookie("dazzle_csrf")
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/unit/test_csrf_session_binding_phase1.py::TestLoginCookie -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/auth/routes.py tests/unit/test_csrf_session_binding_phase1.py
git commit -m "feat(csrf): login sets dazzle_csrf from session secret, logout clears it (Phase 1)"
```

---

### Task 5: Full-suite gate, CHANGELOG, ship

**Files:**
- Modify: `CHANGELOG.md`
- (version bump via `/bump patch`)

- [ ] **Step 1: Run the broad unit slice (per project pre-ship discipline — not just unit/)**

Run: `python -m pytest tests/ -m "not e2e" -q`
Expected: all pass. If `test_auth.py` or migration/discovery tests fail, fix before continuing.

- [ ] **Step 2: Type + lint gate**

Run: `mypy src/dazzle && ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: `Success: no issues found`; ruff clean.

- [ ] **Step 3: Verify the migration applies on a real Postgres (if a dev DB is available)**

Run: `dazzle db upgrade` (against a local dev DB)
Expected: `0005_session_csrf_secret` applies; `dazzle db status` shows it at head. If no DB is wired, note it and rely on the SQLite migration unit test from Task 2.

- [ ] **Step 4: CHANGELOG entry**

Add under `## [Unreleased]` → `### Changed`:

```markdown
- **CSRF token is now session-bound (declarative-CSRF Phase 1, #1337 follow-up).** The `dazzle_csrf` token is the server-side session's own `csrf_secret` (new `sessions.csrf_secret` column, Alembic `0005`), set at login and cleared at logout, replacing the free-floating random cookie that never rotated. Double-submit validation semantics are unchanged; this is the foundation for the origin-primary gate and auth-class derivation in later phases. See `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md`.
```

- [ ] **Step 5: Bump, commit, ship**

```bash
# /bump patch  (run the skill), then:
git add -A
git commit -m "#1337 declarative-CSRF Phase 1: session-bound token -- vX.Y.Z"
git push origin main
```

Then monitor CI (`gh run list --branch main`) to green, and confirm a clean worktree.

---

## Subsequent phases (planned after Phase 1 lands)

These depend on Phase 1's concrete `csrf_secret` shape and on each other, so they get their own plans authored when their predecessor is merged — writing detailed TDD steps now would be speculative against interfaces that don't exist yet.

- **Phase 2 — Origin-primary admission gate.** `Sec-Fetch-Site` + `Origin` check in `csrf.py` with the session-bound token as fallback; configurable trusted-origin allowlist (must integrate with `tenant_host` multi-tenancy, spec §9). Depends on Phase 1 (the token it falls back to).
- **Phase 3 — Derivation + transport.** `csrf_disposition` predicate replacing the hardcoded exempt lists; `<body hx-headers>` injection in `_render_shell.py`; **retire `dz-csrf.js`** + its `build_dist.py` entry; shared-predicate middleware refactor. Depends on Phase 2 (the gate it derives into).
- **Phase 4 — Audit + governance.** CSRF section in `rbac/report.py`; `validate`/`lint` findings for `UNAUTH_MUTATING` + `ESCAPE_HATCH`; the `ESCAPE_HATCH` DSL knob; guarded-action-path seam (ADR-0028/0029); mid-session privilege-change rotation call-sites (using `regenerate_session_csrf` from Task 3); the test-harness refactor (stop `htmx_client.py` et al. hand-rolling the token); **ADR-0033**. Depends on Phase 3 (the disposition it reports on).

---

## Self-review notes

- **Spec coverage (Phase 1 slice of §4.3):** session-bound secret ✓ (Task 1/3), persisted via Alembic per ADR-0017 ✓ (Task 2), cookie derived at login + cleared at logout ✓ (Task 4), rotation primitive ✓ (Task 3). Mid-session privilege rotation explicitly deferred with rationale (Scope boundary).
- **Type consistency:** `csrf_secret: str` used identically in model, INSERT, SELECT mapping, migration, and cookie value; `regenerate_session_csrf(session_id: str) -> str` referenced once (Task 3) and pointed at by Phase 4.
- **No placeholders:** every code step shows real code; fixture-name caveats are explicit instructions to match existing conventions, not TBDs.
- **Risk:** the auth-route test fixtures (`auth_client`, `registered_user`, cookie-name accessor) must match what `src/dazzle/http/tests/test_auth.py` already provides — Task 4 Step 1 instructs reading the handler first to bind the exact `session`/`response`/`deps` names in scope.
