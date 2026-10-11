# Auth Plan 1b — Two-Phase Activation + Org-Context Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline execution with an independent adversarial-review checkpoint on the login/activation path before the role-source switchover). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make login a two-phase flow — prove the identity (Phase 1, already exists) then *activate an org context* (Phase 2): pin `session.active_membership_id` from a host-pin or membership-count rule, expose an org-picker + org-switch, and re-source the runtime `permit:`/`scope:` role decisions from the active membership's `effective_roles`.

**Architecture:** A pure activation resolver (`org_activation.py`) maps `(identity's memberships, host-pinned org id)` → one of `Activated / NeedsPicker / NoOrgs / HostForbidden`. The interactive login routes (password, signup, magic-link, SSO, 2FA-form) call it and thread the chosen `active_membership_id` into `create_session(...)`; multi-org → redirect to the framework `/auth/select-org` picker; host-pin mismatch → 403. A `set_session_active_membership` store method (ownership-checked) backs both the picker POST and a `/auth/switch-org` endpoint (rotates active membership + CSRF, per spec §3 "org-switch ≠ re-auth"). Finally the route-generator + policy + atomic-flow authorization sites stop reading `user.roles` and read `auth_context.effective_roles` (membership-first; the dependency gates already did this in 1a).

**Tech Stack:** Python 3.12, Pydantic v2 (frozen models), psycopg3 (raw SQL, `%s` params), FastAPI routes returning `RedirectResponse`/typed-Fragment `Page`, pytest (+ `pytest.mark.postgres` integration tests against `TEST_DATABASE_URL`).

---

## Scope

**In scope (Plan 1b):**
- Pure activation resolver + outcome types (`org_activation.py`).
- `host_tenant_id_from_request` + `activate_session_for_login` glue.
- `AuthStore.set_session_active_membership` (ownership + active-status checked).
- Threading `active_membership_id` into the session at login for the five interactive entry points (password login, password signup, magic-link, SSO callback, 2FA-form completion).
- Org-picker surface: `build_select_org_view` + `GET/POST /auth/select-org`.
- Org-switch endpoint: `POST /auth/switch-org` (+ CSRF rotation; GUC re-bind happens on the next request via 1a's `validate_session`).
- "No orgs yet" surface: `build_no_orgs_view` + `GET /auth/no-orgs`.
- Mounting the new org-context router in `subsystems/auth.py`.
- Role-source switchover: `route_generator.py` Cedar/permit + scope sites, `policy.py` `check_entity_op`, `server.py` atomic-flow extractor — all from `user.roles` → `auth_context.effective_roles`.

**Out of scope (later slices / explicitly deferred):**
- Single-org auto-provision + invisible degradation when zero memberships exist on a single-org app (Plan 1c — the `NoOrgs` surface here is the honest interim; 1c removes it for single-org apps).
- Migrating `examples/`+`fixtures/` + retiring the preferences-tenant fallback (Plan 1d).
- Audit-record *membership attribution* (`route_generator` audit `user_roles=` content, spec §6) — Plan 2 (compliance evidence); 1b leaves audit content sourcing the actor's global `user.roles` and switches only authorization-decision sites.
- Multi-org invitations / member-admin surfaces / `tenancy: multi_org:` DSL (Plan 3); enterprise `Connection`s (Plans 4–5).
- Legacy JSON `routes.py` login endpoints gaining picker UX (they auto-activate single/host via the same helper in Task 6's note, but multi-org returns a JSON "select org" signal, not a redirect).

## Design decisions resolved here (spec §10 open questions)

- **Host-pin ↔ membership key.** Spec §2.2: *"Organization IS the tenant root."* So the org's tenant-root row id (as a string) is the membership discriminator `tenant_id` (the value bound to `dazzle.tenant_id`). The host-pin resolves to a `ResolvedTenant` (set on `request.state.tenant` by `TenantResolutionMiddleware`, #1289); we match `str(ResolvedTenant.id) == Membership.tenant_id`. **This is the highest-risk assumption — it is the adversarial-review focus in the checkpoint after Task 7.** If a repo app stores a non-id discriminator, that app is migrated in Plan 1d; greenfield uses id-as-discriminator.
- **`active_membership_id` storage.** Stored on the `sessions` row (1a added the column) — *not* re-derived from the host each request. Org-switch rotates it (this plan). Rationale: a switcher (shared-domain) session has no host to re-derive from, so the session must carry the choice.
- **Org-switch rotation.** Update `active_membership_id` + `regenerate_session_csrf` (1a/CSRF-capstone's privilege-change-rotation primitive). The session id is *kept* (switch ≠ re-auth ≠ fixation event); CSRF rotates because the privilege set changed. The RLS GUC re-binds automatically on the next request (`validate_session` → `_bind_rls_tenant_id`, 1a).

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/auth/org_activation.py` | Pure activation resolver + outcome types + request/store glue | **Create** |
| `src/dazzle/http/runtime/auth/org_context_views.py` | Typed-Fragment `build_select_org_view` + `build_no_orgs_view` | **Create** |
| `src/dazzle/http/runtime/auth/org_context_routes.py` | `GET/POST /auth/select-org`, `POST /auth/switch-org`, `GET /auth/no-orgs` | **Create** |
| `src/dazzle/http/runtime/auth/store.py` | `set_session_active_membership` (ownership-checked) | **Modify** |
| `src/dazzle/http/runtime/auth/password_login_routes.py` | Activate at login + signup; thread `active_membership_id`; picker/no-orgs/403 | **Modify** |
| `src/dazzle/http/runtime/auth/magic_link_routes.py` | Activate at magic-link login | **Modify** |
| `src/dazzle/http/runtime/auth/sso_routes.py` | Activate at SSO callback | **Modify** |
| `src/dazzle/http/runtime/auth/two_factor_form_routes.py` | Activate at 2FA completion | **Modify** |
| `src/dazzle/http/runtime/subsystems/auth.py` | Mount `org_context_routes` | **Modify** |
| `src/dazzle/http/runtime/site_routes.py` | Serve `GET /auth/select-org` + `/auth/no-orgs` views (if not co-located) | **(see Task 8 — routes live in `org_context_routes.py`)** |
| `src/dazzle/http/runtime/route_generator.py` | Cedar/permit + scope role source → `effective_roles` | **Modify** |
| `src/dazzle/http/runtime/policy.py` | `check_entity_op` role source → `effective_roles` | **Modify** |
| `src/dazzle/http/runtime/server.py` | atomic-flow `user_role_extractor` → `effective_roles` | **Modify** |
| `tests/unit/test_org_activation.py` | Pure resolver + glue tests | **Create** |
| `tests/unit/test_role_source_effective.py` | Role-switch unit tests (route_generator + policy) | **Create** |
| `tests/integration/test_auth_activation_pg.py` | Real-PG: activation, picker, switch, host-pin | **Create** |

---

## Task 1: Activation resolver + outcome types (`org_activation.py`)

**Files:**
- Create: `src/dazzle/http/runtime/auth/org_activation.py`
- Test: `tests/unit/test_org_activation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_org_activation.py
"""Pure two-phase activation resolver (auth Plan 1b)."""

from dazzle.http.runtime.auth.models import MembershipRecord
from dazzle.http.runtime.auth.org_activation import (
    Activated,
    HostForbidden,
    NeedsPicker,
    NoOrgs,
    resolve_activation,
)


def _m(mid: str, tid: str, status: str = "active") -> MembershipRecord:
    return MembershipRecord(id=mid, tenant_id=tid, identity_id="u-1", status=status)


class TestResolveActivation:
    def test_zero_memberships_is_no_orgs(self) -> None:
        assert isinstance(resolve_activation(memberships=[], host_tenant_id=None), NoOrgs)

    def test_single_active_membership_auto_activates(self) -> None:
        out = resolve_activation(memberships=[_m("m-1", "t-1")], host_tenant_id=None)
        assert isinstance(out, Activated)
        assert out.membership_id == "m-1"

    def test_multiple_active_memberships_need_picker(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1"), _m("m-2", "t-2")], host_tenant_id=None
        )
        assert isinstance(out, NeedsPicker)
        assert {m.id for m in out.memberships} == {"m-1", "m-2"}

    def test_non_active_memberships_are_ignored(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1", status="suspended"), _m("m-2", "t-2")],
            host_tenant_id=None,
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"

    def test_host_pin_matches_membership(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1"), _m("m-2", "t-2")], host_tenant_id="t-2"
        )
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"

    def test_host_pin_no_matching_membership_is_forbidden(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1")], host_tenant_id="t-OTHER"
        )
        assert isinstance(out, HostForbidden)

    def test_host_pin_matches_only_active_membership(self) -> None:
        out = resolve_activation(
            memberships=[_m("m-1", "t-1", status="suspended")], host_tenant_id="t-1"
        )
        assert isinstance(out, HostForbidden)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_org_activation.py -q`
Expected: FAIL — `ModuleNotFoundError: dazzle.http.runtime.auth.org_activation`.

- [ ] **Step 3: Write the resolver**

```python
# src/dazzle/http/runtime/auth/org_activation.py
"""Two-phase auth: Phase-2 org-context activation (auth Plan 1b).

Phase 1 (prove identity) lives in the existing login routes. This module is
Phase 2: given the proven identity's memberships and an optional host-pinned org
id, decide which org context the session activates — or whether the user must
pick, has no orgs, or is forbidden on this host.

The core resolver is pure (no DB, no request) so it is exhaustively unit-tested;
`host_tenant_id_from_request` and `activate_session_for_login` are the thin glue
that read the request + the auth store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.http.runtime.auth.models import MembershipRecord


@dataclass(frozen=True)
class Activated:
    """Exactly one org context resolved — bind this membership to the session."""

    membership_id: str


@dataclass(frozen=True)
class NeedsPicker:
    """The identity has >1 active membership and no host pin — show the picker."""

    memberships: tuple[MembershipRecord, ...]


@dataclass(frozen=True)
class NoOrgs:
    """The identity has no active membership — "no orgs yet" (await invite/create)."""


@dataclass(frozen=True)
class HostForbidden:
    """Host-pinned to an org the identity has no active membership in → 403."""


ActivationOutcome = Activated | NeedsPicker | NoOrgs | HostForbidden


def resolve_activation(
    *, memberships: list[MembershipRecord], host_tenant_id: str | None
) -> ActivationOutcome:
    """Pure Phase-2 decision.

    `host_tenant_id` is `str(ResolvedTenant.id)` when the request is host-pinned
    (subdomain → org, #1289), else None (shared-domain switcher).
    """
    active = [m for m in memberships if m.status == "active"]
    if host_tenant_id is not None:
        match = next((m for m in active if m.tenant_id == host_tenant_id), None)
        return Activated(match.id) if match is not None else HostForbidden()
    if not active:
        return NoOrgs()
    if len(active) == 1:
        return Activated(active[0].id)
    return NeedsPicker(tuple(active))


def host_tenant_id_from_request(request: Any) -> str | None:
    """The host-pinned org id (`str`) for this request, or None.

    `TenantResolutionMiddleware` (#1289) sets `request.state.tenant` to a
    `ResolvedTenant` for a subdomain-pinned host, or `None` for the canonical
    host / apps without `tenant_host:`. Organization IS the tenant root, so the
    resolved tenant's `id` is the membership discriminator.
    """
    state = getattr(request, "state", None)
    resolved = getattr(state, "tenant", None) if state is not None else None
    tid = getattr(resolved, "id", None)
    return str(tid) if tid is not None else None


def activate_session_for_login(auth_store: Any, user: Any, request: Any) -> ActivationOutcome:
    """Resolve Phase 2 for a just-proven `user` on this `request`."""
    memberships = auth_store.get_memberships_for_identity(str(user.id))
    return resolve_activation(
        memberships=memberships,
        host_tenant_id=host_tenant_id_from_request(request),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_org_activation.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/org_activation.py tests/unit/test_org_activation.py
git commit -m "feat(auth): pure two-phase activation resolver (Plan 1b)"
```

---

## Task 2: `host_tenant_id_from_request` + `activate_session_for_login` glue tests

**Files:**
- Test: `tests/unit/test_org_activation.py` (append)
- (No new implementation — Task 1 wrote the glue; this task pins its behaviour with fakes.)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/unit/test_org_activation.py
from types import SimpleNamespace

from dazzle.http.runtime.auth.org_activation import (
    activate_session_for_login,
    host_tenant_id_from_request,
)


class _FakeStore:
    def __init__(self, memberships: list[MembershipRecord]) -> None:
        self._m = memberships

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._m)


def _req(tenant: object | None) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(tenant=tenant))


class TestRequestGlue:
    def test_host_tenant_id_none_when_no_state(self) -> None:
        assert host_tenant_id_from_request(SimpleNamespace()) is None

    def test_host_tenant_id_none_for_canonical_host(self) -> None:
        assert host_tenant_id_from_request(_req(None)) is None

    def test_host_tenant_id_stringifies_resolved_id(self) -> None:
        resolved = SimpleNamespace(id="t-7", slug="acme")
        assert host_tenant_id_from_request(_req(resolved)) == "t-7"

    def test_activate_for_login_uses_store_and_request(self) -> None:
        store = _FakeStore([_m("m-1", "t-1"), _m("m-2", "t-2")])
        user = SimpleNamespace(id="u-1")
        # Host-pinned to t-2 → activates m-2.
        out = activate_session_for_login(store, user, _req(SimpleNamespace(id="t-2")))
        assert isinstance(out, Activated)
        assert out.membership_id == "m-2"
        # No host pin, multiple → picker.
        out2 = activate_session_for_login(store, user, _req(None))
        assert isinstance(out2, NeedsPicker)
```

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `pytest tests/unit/test_org_activation.py -q`
Expected: PASS (the glue already exists from Task 1; if `host_tenant_id_from_request` mishandles a missing `state`, fix it there).

- [ ] **Step 3: (no new implementation)** — fix Task 1's glue only if a test fails.

- [ ] **Step 4: Re-run**

Run: `pytest tests/unit/test_org_activation.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_org_activation.py
git commit -m "test(auth): pin activation request/store glue (Plan 1b)"
```

---

## Task 3: `AuthStore.set_session_active_membership` (ownership-checked)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py`
- Test: `tests/integration/test_auth_activation_pg.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_auth_activation_pg.py
"""Real-PostgreSQL proof of two-phase activation + org-switch (auth Plan 1b).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_membership_pg.py's scratch-DB harness.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_auth_1b_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _seed_user(store, email: str = "a@b.test") -> str:
    from dazzle.http.runtime.auth.models import UserRecord

    user = UserRecord(email=email, password_hash="x")
    store.create_user(user)
    return str(user.id)


def test_set_session_active_membership_happy_path(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])
    session = store.create_session(user)  # no active membership yet

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is True
    ctx = store.validate_session(session.id)
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == m.id


def test_set_session_active_membership_rejects_foreign_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid_a = _seed_user(store, "a@b.test")
    uid_b = _seed_user(store, "b@b.test")
    user_a = store.get_user_by_id(uid_a)
    assert user_a is not None
    m_b = store.create_membership(tenant_id="t-b", identity_id=uid_b, roles=["admin"])
    session_a = store.create_session(user_a)

    # A must not be able to activate B's membership.
    ok = store.set_session_active_membership(session_a.id, m_b.id, identity_id=uid_a)
    assert ok is False
    ctx = store.validate_session(session_a.id)
    assert ctx.active_membership is None


def test_set_session_active_membership_rejects_suspended(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    m = store.create_membership(
        tenant_id="t-1", identity_id=uid, roles=["admin"], status="suspended"
    )
    session = store.create_session(user)

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is False
```

> `get_user_by_id` may take a `UUID` — pass `uuid.UUID(uid)` if its signature requires it (grep `def get_user_by_id` in `store.py`; 1a's integration test already calls it with the `str` `uid`, so mirror that). Assertions unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k set_session_active_membership -q`
Expected: FAIL — `AuthStore` has no `set_session_active_membership`.

- [ ] **Step 3: Add the method**

In `src/dazzle/http/runtime/auth/store.py`, add near `regenerate_session_csrf` / the session methods:

```python
    def set_session_active_membership(
        self, session_id: str, membership_id: str, *, identity_id: str
    ) -> bool:
        """Pin (or rotate) a session's active org membership — ownership-checked.

        The membership must belong to `identity_id` (the session's user) and be
        `status="active"`; otherwise this is a no-op returning False (a user must
        not activate another identity's org, nor a suspended membership). The
        `AND user_id = %s` on the UPDATE is defence-in-depth so a stale/foreign
        `session_id` cannot be repointed. Returns True iff exactly one row moved.
        """
        membership = self.get_membership(membership_id)
        if (
            membership is None
            or membership.identity_id != identity_id
            or membership.status != "active"
        ):
            return False
        rowcount = self._execute_modify(
            "UPDATE sessions SET active_membership_id = %s "
            "WHERE id = %s AND user_id = %s",
            (membership_id, session_id, identity_id),
        )
        return rowcount == 1
```

> `_execute_modify` is the same rowcount-returning helper `regenerate_session_csrf` uses. `sessions.user_id` is stored as `str(uuid)` (see `create_session`), and `membership.identity_id` / `identity_id` are the `str(user.id)` written by `create_membership` — so the comparison is string-to-string and consistent.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k set_session_active_membership -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_activation_pg.py
git commit -m "feat(auth): ownership-checked set_session_active_membership (Plan 1b)"
```

---

## Task 4: Activate at password login + signup

**Files:**
- Modify: `src/dazzle/http/runtime/auth/password_login_routes.py`
- Test: `tests/integration/test_auth_activation_pg.py` (append — uses an in-process FastAPI app)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_activation_pg.py
def _app_with_store(store):
    """Minimal FastAPI app wiring the password-login router to `store`."""
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.password_login_routes import (
        create_password_login_routes,
    )

    app = FastAPI()
    app.state.auth_store = store
    app.state.auth_password_mode_enabled = True
    app.include_router(create_password_login_routes())
    return app


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=False)


def test_password_login_single_membership_auto_activates(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "solo@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    # The created session carries the single membership.
    sid = resp.cookies.get("dazzle_session")
    assert sid is not None
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == "t-1"
    assert resp.headers["location"] == "/app"


def test_password_login_multi_membership_redirects_to_picker(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="multi@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])
    store.create_membership(tenant_id="t-2", identity_id=str(user.id), roles=["member"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "multi@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/select-org"
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is None  # not yet chosen


def test_password_login_no_membership_redirects_to_no_orgs(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_user(email="orphan@b.test", password="pw123456")

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "orphan@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/no-orgs"
```

> `create_user(email=..., password=...)` is the keyword form `password_login_routes` already uses (line ~170); it returns a `UserRecord`. If your local signature differs, mirror the call already in `submit_signup_password`.

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k password_login -q`
Expected: FAIL — login currently always redirects to `/app` and never sets `active_membership_id` (picker/no-orgs assertions fail).

- [ ] **Step 3: Thread activation into both handlers**

In `src/dazzle/http/runtime/auth/password_login_routes.py`, add a shared helper above `create_password_login_routes`:

```python
from dazzle.http.runtime.auth.org_activation import (
    Activated,
    HostForbidden,
    NeedsPicker,
    activate_session_for_login,
)


def _login_redirect_for_outcome(outcome: object, next_target: str) -> tuple[str | None, str]:
    """Map a Phase-2 activation outcome → (active_membership_id, redirect_path).

    `active_membership_id` is None unless exactly one org resolved. `HostForbidden`
    is signalled by a sentinel redirect the caller turns into a 403.
    """
    if isinstance(outcome, Activated):
        return outcome.membership_id, next_target
    if isinstance(outcome, NeedsPicker):
        return None, "/auth/select-org"
    if isinstance(outcome, HostForbidden):
        return None, "__forbidden__"
    return None, "/auth/no-orgs"  # NoOrgs
```

Then in `submit_login_password`, replace the success block (the lines from `pre_auth_sid = read_session_id(request)` through `return response`) with:

```python
        pre_auth_sid = read_session_id(request)
        outcome = activate_session_for_login(auth_store, user, request)
        membership_id, redirect_to = _login_redirect_for_outcome(
            outcome,
            next if next and next != "/" and _is_safe_redirect_path(next) else "/app",
        )
        if redirect_to == "__forbidden__":
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="no membership for this organization")
        session = auth_store.create_session(user, active_membership_id=membership_id)
        if pre_auth_sid and pre_auth_sid != session.id:
            auth_store.delete_session(pre_auth_sid)
        response = RedirectResponse(url=redirect_to, status_code=303)
        _set_session_cookie(
            response,
            request,
            session.id,
            session.csrf_secret,
            user_roles=list(getattr(user, "roles", []) or []),
        )
        return response
```

Apply the identical pattern to `submit_signup_password`'s success block (a brand-new user has no memberships yet, so it resolves to `NoOrgs` → `/auth/no-orgs` — honest until Plan 1c auto-provisions a single-org membership at signup).

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k password_login -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/password_login_routes.py tests/integration/test_auth_activation_pg.py
git commit -m "feat(auth): two-phase activation at password login/signup (Plan 1b)"
```

---

## Task 5: Activate at magic-link login

**Files:**
- Modify: `src/dazzle/http/runtime/auth/magic_link_routes.py`
- Test: covered by the in-process route test in Task 13 (magic-link needs a verified token; the unit-level proof is the shared helper from Task 4).

- [ ] **Step 1: Read the current success block**

In `src/dazzle/http/runtime/auth/magic_link_routes.py` around line 97, the handler creates `session = auth_store.create_session(user)` then sets the cookie and redirects. Identify the `user`, `request`, and the redirect target variable.

- [ ] **Step 2: Apply activation**

Replace `session = auth_store.create_session(user)` and the subsequent redirect-target computation with the same pattern as Task 4 — import the helpers at the top of the file:

```python
from dazzle.http.runtime.auth.org_activation import activate_session_for_login
from dazzle.http.runtime.auth.password_login_routes import _login_redirect_for_outcome
```

and in the handler:

```python
        outcome = activate_session_for_login(auth_store, user, request)
        membership_id, redirect_to = _login_redirect_for_outcome(outcome, <existing_safe_target>)
        if redirect_to == "__forbidden__":
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="no membership for this organization")
        session = auth_store.create_session(user, active_membership_id=membership_id)
```

Replace `<existing_safe_target>` with whatever safe redirect the handler already computed (e.g. `redirect_to` it had, or `"/app"`). Keep the existing cookie-set call. If importing `_login_redirect_for_outcome` from `password_login_routes` creates an awkward dependency, **move `_login_redirect_for_outcome` into `org_activation.py`** and import it from there in both files (preferred — do this if the magic-link/SSO/2FA files would otherwise all import from `password_login_routes`).

> **DRY note for the executor:** if you find yourself importing `_login_redirect_for_outcome` into a third file, relocate it to `org_activation.py` now and update Task 4's import. One canonical home.

- [ ] **Step 3: Run the unit + the existing magic-link tests**

Run: `pytest tests/unit/test_org_activation.py -q && pytest tests/ -m "not e2e" -k magic -q`
Expected: PASS (no regression in existing magic-link tests).

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/http/runtime/auth/magic_link_routes.py src/dazzle/http/runtime/auth/org_activation.py src/dazzle/http/runtime/auth/password_login_routes.py
git commit -m "feat(auth): two-phase activation at magic-link login (Plan 1b)"
```

---

## Task 6: Activate at SSO callback + 2FA-form completion

**Files:**
- Modify: `src/dazzle/http/runtime/auth/sso_routes.py` (line ~205), `src/dazzle/http/runtime/auth/two_factor_form_routes.py` (line ~103)
- Test: covered by Task 13 end-to-end; here, no-regression on existing SSO/2FA tests.

- [ ] **Step 1: SSO callback**

In `sso_routes.py`, where `session = auth_store.create_session(user)` (line ~205), apply the Task-5 pattern: resolve the outcome via `activate_session_for_login(auth_store, user, request)`, map with `_login_redirect_for_outcome` (now in `org_activation.py`), raise `HTTPException(403)` on `__forbidden__`, and pass `active_membership_id=membership_id` to `create_session`. If the SSO handler computes its own post-login redirect, override it with `redirect_to` only when the outcome is `NeedsPicker`/`NoOrgs` (so the picker/no-orgs interception wins); otherwise keep the SSO redirect target as the `Activated` `next_target` you pass in.

- [ ] **Step 2: 2FA-form completion**

In `two_factor_form_routes.py` (line ~103), the post-2FA session is the *real* authenticated session for 2FA users — apply the same activation pattern there. The `user` is the one whose pending session passed the challenge; `request` is in scope.

> **Legacy JSON `routes.py` note (in-scope-minimal):** at the JSON login/register `create_session` sites (lines ~113, ~216, ~317, ~403), thread activation too, but instead of redirects return the membership outcome in the JSON body. Minimal contract: `Activated` → `create_session(active_membership_id=...)` as today; `NeedsPicker` → `create_session(...)` with no membership + add `"requires_org_selection": true` to the response JSON; `NoOrgs` → add `"no_orgs": true`; `HostForbidden` → HTTP 403. Keep this change small; the HTML picker is the primary UX. If a `routes.py` site lacks `request`, it is available on the FastAPI handler signature — add it if missing.

- [ ] **Step 3: Run no-regression suites**

Run: `pytest tests/ -m "not e2e" -k "sso or two_factor or 2fa or auth_routes" -q`
Expected: PASS (existing auth-route tests stay green).

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/http/runtime/auth/sso_routes.py src/dazzle/http/runtime/auth/two_factor_form_routes.py src/dazzle/http/runtime/auth/routes.py
git commit -m "feat(auth): two-phase activation at SSO + 2FA + JSON login (Plan 1b)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 7)
> Before the role-source switchover, dispatch an **independent reviewer subagent** (or run `/code-review`) over the *login/activation path* (Tasks 1–7). Brief it to attack specifically: (1) the host-pin ↔ `Membership.tenant_id` identity assumption — can a user activate the wrong org, or be wrongly 403'd, if the discriminator isn't the tenant-root id? (2) session-fixation: does the pre-auth-session deletion still hold with the new activation branch? (3) can `set_session_active_membership` / `/auth/switch-org` be used to cross into another identity's org (IDOR)? (4) does a `NeedsPicker` session (no active membership) leave the user in a usable-but-unfenced state — confirm the fence *denies* (1a: no membership → unbound GUC → RLS denies), so an un-activated session sees nothing rather than everything. Apply receiving-code-review rigor to the findings (verify before implementing). Only proceed to Task 8 once the path is clean.

---

## Task 7: Org-context router — `/auth/select-org`, `/auth/switch-org`, `/auth/no-orgs`

**Files:**
- Create: `src/dazzle/http/runtime/auth/org_context_views.py`
- Create: `src/dazzle/http/runtime/auth/org_context_routes.py`
- Test: `tests/integration/test_auth_activation_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_activation_pg.py
def _app_with_org_routes(store):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.auth_password_mode_enabled = True
    app.include_router(create_org_context_routes())
    return app


def _login_session(store, email: str, n_orgs: int) -> tuple[str, str, list[str]]:
    """Create a user + n memberships + a session with no active membership."""
    user = store.create_user(email=email, password="pw123456")
    mids = [
        store.create_membership(tenant_id=f"t-{i}", identity_id=str(user.id), roles=["member"]).id
        for i in range(n_orgs)
    ]
    session = store.create_session(user)
    return session.id, str(user.id), mids


def test_select_org_post_activates_owned_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid, _uid, mids = _login_session(store, "multi@b.test", 2)
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid)

    resp = client.post("/auth/select-org", data={"membership_id": mids[1]})
    assert resp.status_code == 303
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == mids[1]


def test_switch_org_rotates_active_membership_and_csrf(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid, _uid, mids = _login_session(store, "multi@b.test", 2)
    # Start on org 0.
    assert store.set_session_active_membership(sid, mids[0], identity_id=_uid)
    csrf_before = store.get_session(sid).csrf_secret
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid)

    resp = client.post("/auth/switch-org", data={"membership_id": mids[1]})
    assert resp.status_code == 303
    ctx = store.validate_session(sid)
    assert ctx.active_membership.id == mids[1]
    assert store.get_session(sid).csrf_secret != csrf_before  # CSRF rotated


def test_select_org_rejects_unowned_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid_a, _uid_a, _ = _login_session(store, "a@b.test", 1)
    _sid_b, uid_b, mids_b = _login_session(store, "b@b.test", 1)
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid_a)

    # A tries to activate B's membership → rejected, session A unchanged.
    resp = client.post("/auth/select-org", data={"membership_id": mids_b[0]})
    assert resp.status_code in (303, 403)
    ctx = store.validate_session(sid_a)
    assert ctx.active_membership is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k "select_org or switch_org" -q`
Expected: FAIL — `create_org_context_routes` does not exist.

- [ ] **Step 3a: Write the views**

```python
# src/dazzle/http/runtime/auth/org_context_views.py
"""Typed-Fragment views for Phase-2 org context (auth Plan 1b).

`build_select_org_view` lists the identity's active memberships as a radio-style
form posting to `/auth/select-org`. `build_no_orgs_view` is the honest interim
"no orgs yet" page (Plan 1c auto-provisions a single-org membership so single-org
apps never see it).
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment.models import (
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
    URL,
)


def build_select_org_view(
    *,
    product_name: str,
    memberships: tuple[Any, ...],
    next_url: str = "/app",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Org picker — one selectable option per active membership."""
    form_action = "/auth/select-org"
    if next_url and next_url != "/":
        form_action = f"{form_action}?next={next_url}"
    options = tuple(
        (m.id, (m.tenant_id if not getattr(m, "name", None) else m.name)) for m in memberships
    )
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="Choose an organization", level=1),
        FormStack(
            action=URL(form_action),
            method="POST",
            fields=(
                Field(
                    name="membership_id",
                    label="Organization",
                    kind="select",
                    required=True,
                    options=options,
                ),
            ),
            submit=Submit(label="Continue", variant="primary"),
        ),
    ]
    return Page(
        title=f"Choose an organization — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_no_orgs_view(
    *,
    product_name: str,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """"No orgs yet" — the identity is proven but has no active membership."""
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="No organizations yet", level=1),
        Text(
            body="You're signed in, but you don't belong to any organization yet. "
            "Ask an admin for an invitation, or create one.",
            tone="muted",
        ),
    ]
    return Page(
        title=f"No organizations yet — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
```

> **Verify the Fragment imports + `Field(kind="select", options=...)` shape** against `auth_views.py` and `dazzle/render/fragment/models.py`. If `Field` has no `options`/`select` kind, render one `Submit` per membership inside a `FormStack` (a button per org, each posting its `membership_id` via a hidden field), or use the existing `RadioGroup`/`Choice` primitive — grep `class Field` and the form primitives in `dazzle/render/fragment/models.py` and mirror the closest existing select pattern. The assertion in Task 7's test is on the POST behaviour, not the markup, so the exact primitive can flex.

- [ ] **Step 3b: Write the routes**

```python
# src/dazzle/http/runtime/auth/org_context_routes.py
"""Phase-2 org-context routes (auth Plan 1b): pick / switch / no-orgs.

`/auth/select-org`   GET  — picker (a session with no active membership yet)
`/auth/select-org`   POST — activate one of the identity's memberships
`/auth/switch-org`   POST — rotate the active membership (+ CSRF) without re-auth
`/auth/no-orgs`      GET  — honest "no orgs yet" page

All POSTs are ownership-checked in the store (`set_session_active_membership`).
A successful switch rotates the CSRF secret (privilege change) and re-sets the
`dazzle_csrf` cookie; the RLS GUC re-binds on the next request via 1a's
`validate_session` → `_bind_rls_tenant_id`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dazzle.http.runtime.auth.cookie_name import read_session_id
from dazzle.http.runtime.auth.crypto import cookie_secure
from dazzle.http.runtime.auth.redirect_safety import is_safe_redirect_path


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return brand.get("product_name", "Dazzle")


async def _activate_and_redirect(
    request: Request, membership_id: str, next_target: str, *, rotate_csrf: bool
) -> RedirectResponse:
    auth_store = request.app.state.auth_store
    session_id = read_session_id(request)
    if not session_id:
        return RedirectResponse(url="/login", status_code=303)
    ctx = auth_store.validate_session(session_id)
    if not ctx.is_authenticated or ctx.user is None:
        return RedirectResponse(url="/login", status_code=303)
    ok = auth_store.set_session_active_membership(
        session_id, membership_id, identity_id=str(ctx.user.id)
    )
    if not ok:
        # Not the user's membership / not active — bounce to the picker.
        return RedirectResponse(url="/auth/select-org?error=invalid_org", status_code=303)
    response = RedirectResponse(url=next_target, status_code=303)
    if rotate_csrf:
        new_secret = auth_store.regenerate_session_csrf(session_id)
        response.set_cookie(
            key="dazzle_csrf",
            value=new_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
        )
    return response


def create_org_context_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/auth/select-org", response_class=HTMLResponse, include_in_schema=False)
    async def select_org_page(request: Request, next: Annotated[str, Query()] = "/app") -> str:
        from dazzle.http.runtime.auth.org_context_views import build_select_org_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        auth_store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = auth_store.validate_session(session_id) if session_id else None
        memberships: tuple[Any, ...] = ()
        if ctx is not None and ctx.is_authenticated and ctx.user is not None:
            memberships = tuple(
                m
                for m in auth_store.get_memberships_for_identity(str(ctx.user.id))
                if m.status == "active"
            )
        page = build_select_org_view(
            product_name=_product_name(request),
            memberships=memberships,
            next_url=next if is_safe_redirect_path(next) else "/app",
        )
        return FragmentRenderer().render(page)

    @router.post("/auth/select-org", include_in_schema=False)
    async def select_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> RedirectResponse:
        target = next if next and next != "/" and is_safe_redirect_path(next) else "/app"
        # First activation of a session → rotate CSRF too (privilege acquired).
        return await _activate_and_redirect(request, membership_id, target, rotate_csrf=True)

    @router.post("/auth/switch-org", include_in_schema=False)
    async def switch_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> RedirectResponse:
        target = next if next and next != "/" and is_safe_redirect_path(next) else "/app"
        return await _activate_and_redirect(request, membership_id, target, rotate_csrf=True)

    @router.get("/auth/no-orgs", response_class=HTMLResponse, include_in_schema=False)
    async def no_orgs_page(request: Request) -> str:
        from dazzle.http.runtime.auth.org_context_views import build_no_orgs_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        return FragmentRenderer().render(build_no_orgs_view(product_name=_product_name(request)))

    return router
```

> Verify `read_session_id` is importable from `cookie_name` (it is — `password_login_routes` imports it). Verify `request.app.state.sitespec` is the right place for the product name; if not present in this minimal context, `_product_name` already falls back to `"Dazzle"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k "select_org or switch_org" -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/org_context_views.py src/dazzle/http/runtime/auth/org_context_routes.py tests/integration/test_auth_activation_pg.py
git commit -m "feat(auth): org-context routes — select/switch/no-orgs (Plan 1b)"
```

---

## Task 8: Mount the org-context router

**Files:**
- Modify: `src/dazzle/http/runtime/subsystems/auth.py`
- Test: `tests/integration/test_auth_activation_pg.py` (append — boot-wiring smoke is covered by Task 13; here, assert the router is included on a real app factory if feasible, else a unit include check)

- [ ] **Step 1: Mount it next to the password-login router**

In `src/dazzle/http/runtime/subsystems/auth.py`, after the `password_login_router` include (line ~139), add:

```python
        # Phase-2 org-context routes (auth Plan 1b): /auth/select-org,
        # /auth/switch-org, /auth/no-orgs. Mounted unconditionally — they
        # no-op (redirect to /login) for unauthenticated callers and only
        # matter once an identity has >1 membership.
        from dazzle.http.runtime.auth.org_context_routes import (
            create_org_context_routes,
        )

        ctx.app.include_router(create_org_context_routes())
```

- [ ] **Step 2: Write a wiring assertion (append to the integration file)**

```python
# append to tests/integration/test_auth_activation_pg.py
def test_org_context_routes_are_mountable() -> None:
    """The router exposes the four Phase-2 paths."""
    from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes

    paths = {r.path for r in create_org_context_routes().routes}
    assert {"/auth/select-org", "/auth/switch-org", "/auth/no-orgs"} <= paths
```

(This test has no `pytestmark`-DB dependency — it runs in the normal unit pass too. If it must live with the e2e file, it still runs since it touches no DB; alternatively move it to `tests/unit/test_org_activation.py`.)

- [ ] **Step 3: Run**

Run: `pytest tests/integration/test_auth_activation_pg.py::test_org_context_routes_are_mountable -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/http/runtime/subsystems/auth.py tests/integration/test_auth_activation_pg.py
git commit -m "feat(auth): mount org-context router (Plan 1b)"
```

---

## Task 9: Switch route_generator Cedar/permit role source → `effective_roles`

**Files:**
- Modify: `src/dazzle/http/runtime/route_generator.py`
- Test: `tests/unit/test_role_source_effective.py`

The authorization-decision sites currently read `auth_context.user.roles`. Each has `auth_context` in scope; switch them to `auth_context.effective_roles` (membership-first per 1a), keeping the existing `_normalize_role` wrapping (membership roles are bare DSL names, so normalization is a no-op on them; the legacy fallback stays normalized).

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_role_source_effective.py
"""Authorization sites source roles from active membership (Plan 1b)."""

from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord


def _ctx_with_membership(membership_roles: list[str], user_roles: list[str]) -> AuthContext:
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x", roles=user_roles),
        is_authenticated=True,
        roles=user_roles,
        active_membership=MembershipRecord(
            id="m-1", tenant_id="t-1", identity_id="u-1", roles=membership_roles
        ),
    )


def test_build_access_runtime_context_uses_membership_roles() -> None:
    from dazzle.http.runtime.route_generator import _build_access_runtime_context

    # Membership says admin; legacy user.roles says nothing — admin must win.
    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=[])
    _user, runtime_ctx = _build_access_runtime_context(ctx)
    assert "admin" in set(runtime_ctx.roles)


def test_cedar_row_filters_use_membership_roles() -> None:
    """A role-gated unrestricted permit is recognised from membership roles."""
    from types import SimpleNamespace

    from dazzle.http.runtime.route_generator import _extract_cedar_row_filters

    spec = SimpleNamespace(
        permissions=[
            SimpleNamespace(
                operation=SimpleNamespace(value="list"),
                effect=SimpleNamespace(value="permit"),
                condition=None,
                personas=["admin"],
            )
        ]
    )
    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=[])
    # Admin (from membership) → unrestricted permit → no row filters.
    assert _extract_cedar_row_filters(spec, user_id="u-1", auth_context=ctx) == {}
```

> Confirm the real function name at line ~1400 (the test calls `_build_access_runtime_context`). Grep `def ` immediately above line 1413 in `route_generator.py`; if the name differs, use the actual one in the test import. The assertion (membership roles flow into the runtime context) is the invariant.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_role_source_effective.py -q`
Expected: FAIL — the sites read `user.roles` (empty here) so `admin` is absent / filters are applied.

- [ ] **Step 3: Switch the gate sites**

In `src/dazzle/http/runtime/route_generator.py`, make these exact edits (line numbers approximate — match on the surrounding text):

1. **`_extract_cedar_row_filters` (~line 859–866):** replace the role-collection loop
   ```python
   user_roles: set[str] = set()
   if auth_context is not None:
       _user_obj = getattr(auth_context, "user", None)
       if _user_obj:
           for r in getattr(_user_obj, "roles", []):
               name = r if isinstance(r, str) else getattr(r, "name", str(r))
               user_roles.add(_normalize_role(name))
   ```
   with
   ```python
   # auth Plan 1b: source roles from the active membership (effective_roles),
   # not the global user.roles.
   user_roles: set[str] = set()
   if auth_context is not None:
       for r in auth_context.effective_roles:
           name = r if isinstance(r, str) else getattr(r, "name", str(r))
           user_roles.add(_normalize_role(name))
   ```

2. **`_build_access_runtime_context` (~line 1413):** replace
   ```python
   raw_roles = list(getattr(user, "roles", [])) if user else []
   ```
   with
   ```python
   raw_roles = list(auth_context.effective_roles)  # auth Plan 1b: membership-first
   ```
   (Keep the following `roles=[_normalize_role(r) for r in raw_roles]`. `effective_roles` returns `[]` when unauthenticated, matching the old `if user else []`.)

3. **Mutation `_auth_impl` (~line 1800):** replace
   ```python
   raw_roles = list(getattr(user, "roles", [])) if user else []
   ```
   with
   ```python
   raw_roles = list(auth_context.effective_roles)  # auth Plan 1b: membership-first
   ```

4. **Scope predicate role collection (~line 2225):** replace the loop
   ```python
   user = getattr(auth_context, "user", None)
   if user is not None:
       user_id = str(user.id) if getattr(user, "id", None) is not None else None
       for r in getattr(user, "roles", []) or []:
           r_name = r if isinstance(r, str) else getattr(r, "name", str(r))
           user_roles.add(_normalize_role(r_name))
   ```
   with
   ```python
   user = getattr(auth_context, "user", None)
   if user is not None:
       user_id = str(user.id) if getattr(user, "id", None) is not None else None
   for r in auth_context.effective_roles:  # auth Plan 1b: membership-first
       r_name = r if isinstance(r, str) else getattr(r, "name", str(r))
       user_roles.add(_normalize_role(r_name))
   ```
   (`user_id` still comes from the user; only the *roles* move to `effective_roles`.)

5. **Admin-persona bypass (~line 2723):** replace
   ```python
   user_roles = set(getattr(user, "roles", []) or [])
   ```
   with
   ```python
   user_roles = set(auth_context.effective_roles)  # auth Plan 1b: membership-first
   ```

6. **Forbidden-detail content (~line 1713):** replace `current_roles=list(getattr(user, "roles", [])) if user else []` with `current_roles=list(auth_context.effective_roles)` — the 403 should report the roles actually in effect.

> **Leave the audit `user_roles=` content at ~line 1504 and the audit `user=user` at ~line 1707 UNCHANGED** — audit *attribution* (which roles the actor globally holds) is Plan 2 (compliance-evidence) territory, not an authorization decision. A one-line comment `# Plan 1b: audit attribution stays user-sourced; membership attribution is Plan 2` documents the deliberate boundary.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_role_source_effective.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the route_generator unit slice for regressions**

Run: `pytest tests/ -m "not e2e" -k "route_generator or cedar or scope or permit" -q`
Expected: PASS (no regression).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/route_generator.py tests/unit/test_role_source_effective.py
git commit -m "feat(auth): route_generator permit/scope roles from effective_roles (Plan 1b)"
```

---

## Task 10: Switch `policy.py` + `server.py` atomic extractor role source

**Files:**
- Modify: `src/dazzle/http/runtime/policy.py` (`check_entity_op`, ~line 179), `src/dazzle/http/runtime/server.py` (~line 1636)
- Test: `tests/unit/test_role_source_effective.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/unit/test_role_source_effective.py
def test_policy_check_entity_op_sources_membership_roles(monkeypatch) -> None:
    """check_entity_op's permit gate reads effective_roles off the request's
    auth_context (membership-first)."""
    from types import SimpleNamespace

    captured: dict[str, object] = {}

    import dazzle.http.runtime.policy as policy_mod

    def _fake_permit_passes(spec, op, user_roles, user_id):  # noqa: ANN001
        captured["roles"] = list(user_roles)
        return True

    monkeypatch.setattr(policy_mod, "_permit_passes", _fake_permit_passes, raising=True)

    ctx = _ctx_with_membership(membership_roles=["admin"], user_roles=["legacy"])
    # Minimal request + registry with an access spec so the permit gate runs.
    access_spec = SimpleNamespace()
    info = SimpleNamespace(cedar_access_spec=access_spec)
    registry = SimpleNamespace(get=lambda name: info)
    request = SimpleNamespace(
        state=SimpleNamespace(auth_context=ctx, policy_registry=registry)
    )
    # Call through; we only assert the captured roles came from the membership.
    try:
        policy_mod.check_entity_op(request, "Note", "read")  # type: ignore[attr-defined]
    except Exception:
        pass  # downstream scope gate may raise; we only care about captured roles
    assert captured.get("roles") == ["admin"]
```

> The exact call signature of `check_entity_op` (positional vs request-on-state, how `registry` is obtained) must match the real one — read `policy.py` lines ~150–200 and adapt the harness (the `request.state.policy_registry` / `app.state` lookup). The assertion is invariant: the roles handed to `_permit_passes` are `effective_roles`, not `user.roles`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_role_source_effective.py -k policy -q`
Expected: FAIL — `_permit_passes` receives `["legacy"]` (from `user.roles`).

- [ ] **Step 3a: Switch `policy.py`**

In `src/dazzle/http/runtime/policy.py`, line ~179, replace
```python
user_roles_raw = list(getattr(user, "roles", []) or [])
```
with
```python
# auth Plan 1b: permit/scope gates read the active membership's roles
# (effective_roles), falling back to global user roles only when no
# membership is active (1a transition).
user_roles_raw = list(getattr(auth_ctx, "effective_roles", None) or getattr(user, "roles", []) or [])
```
(`auth_ctx` is already in scope at line ~171.)

- [ ] **Step 3b: Switch `server.py` atomic extractor**

In `src/dazzle/http/runtime/server.py`, line ~1636, replace
```python
user_role_extractor=lambda user: list(getattr(user, "roles", []) or []),
```
with
```python
# auth Plan 1b: the atomic-flow router calls this with the AuthContext
# (see atomic_flow_routes `auth_context=user`), so read effective_roles
# (membership-first) — not the global user.roles.
user_role_extractor=lambda ac: list(getattr(ac, "effective_roles", None) or []),
```

> Confirm via `atomic_flow_routes.py` (~line 207, `auth_context=user`) that the extractor's argument is the `AuthContext`, so `ac.effective_roles` is valid. It is.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_role_source_effective.py -q`
Expected: PASS.

- [ ] **Step 5: Run policy + atomic regression slice**

Run: `pytest tests/ -m "not e2e" -k "policy or atomic or check_entity" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/policy.py src/dazzle/http/runtime/server.py tests/unit/test_role_source_effective.py
git commit -m "feat(auth): policy + atomic-flow roles from effective_roles (Plan 1b)"
```

---

## Task 11: End-to-end keystone — host-pin activation + fenced read

**Files:**
- Test: `tests/integration/test_auth_activation_pg.py` (append)

Proves the full Phase-2 host-pin path: a host-pinned login activates *only* the matching org's membership, and the bound fence returns only that org's rows.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_activation_pg.py
def test_host_pin_activates_matching_org_and_403s_on_mismatch(scratch_url: str) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import activate_session_for_login
    from dazzle.http.runtime.auth.org_activation import Activated, HostForbidden
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="multi@b.test", password="pw123456")
    store.create_membership(tenant_id="t-A", identity_id=str(user.id), roles=["admin"])
    store.create_membership(tenant_id="t-B", identity_id=str(user.id), roles=["member"])

    def _req(tenant_id: str | None):
        tenant = SimpleNamespace(id=tenant_id, slug=tenant_id) if tenant_id else None
        return SimpleNamespace(state=SimpleNamespace(tenant=tenant))

    # Host-pinned to t-B → activates the t-B membership.
    out_b = activate_session_for_login(store, user, _req("t-B"))
    assert isinstance(out_b, Activated)
    m_b = store.get_membership(out_b.membership_id)
    assert m_b.tenant_id == "t-B"

    # Host-pinned to an org the user isn't in → forbidden.
    out_x = activate_session_for_login(store, user, _req("t-UNKNOWN"))
    assert isinstance(out_x, HostForbidden)
```

- [ ] **Step 2: Run test to verify it passes (the pipeline already exists)**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -k host_pin -q`
Expected: PASS — composes Tasks 1+3; if it fails the defect is in those tasks, fix there.

- [ ] **Step 3: Run the whole Plan-1b integration suite**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_activation_pg.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_auth_activation_pg.py
git commit -m "test(auth): host-pin activation keystone (Plan 1b)"
```

---

## Final verification (run before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean (the CI command per saved memory; not the narrower core/cli/mcp subset)
- [ ] `pytest tests/ -m "not e2e"` — green (unit suite incl. the two new unit files; `test_org_context_routes_are_mountable` runs here too)
- [ ] With `TEST_DATABASE_URL="postgresql://localhost:5432/postgres"`: `pytest tests/integration/test_auth_activation_pg.py -q` — green
- [ ] `pytest tests/ -m "not e2e" -k "auth or login or magic or sso or 2fa or two_factor"` — no regression in existing auth-route tests
- [ ] `/bump patch` + CHANGELOG entry under **Added** (two-phase activation + org-context routes) and **Changed** (permit/scope role source → active membership) with an **Agent Guidance** note:
  - "Login now activates an org context (Phase 2): single membership auto-activates, host-pin (`tenant_host` #1289) activates the matching org or 403s, multiple → `/auth/select-org`, zero → `/auth/no-orgs`. `session.active_membership_id` is set at login; `/auth/switch-org` rotates it (+ CSRF). Runtime `permit:`/`scope:` role decisions now source `auth_context.effective_roles` (active membership), not `user.roles` — update any custom route/policy code that read `user.roles` for authorization. Audit *attribution* still uses global user roles (membership attribution is Plan 2)."

---

## Forward outline (Plans 1c–1d + 2 — each its own plan)

- **Plan 1c — single-org auto-provision + invisible degradation.** Replace the `NoOrgs` → `/auth/no-orgs` interim for single-org apps: at signup/first-boot, ensure one Organization (tenant root + `public.tenants` row) and create one membership per signup, so Phase 2 auto-activates invisibly. Resolves spec §10's auto-provision-trigger question.
- **Plan 1d — migrate repo apps/fixtures + retire preferences-indirection.** Update `examples/`+`fixtures/` to memberships; documented single-org migration recipe (+ optional `dazzle auth migrate`); remove the `_bind_rls_tenant_id` preferences fallback and the `_load_domain_user_attributes` tenant copy once all callers are migrated. Verifies the host-pin discriminator assumption per real app.
- **Plan 2 — RBAC re-sourcing + compliance evidence.** Switch audit *attribution* to membership (the deliberately-deferred audit sites in Task 9); platform roles on identity; lifecycle events → audit trail → access-review export.

## Self-review notes

- **Spec coverage (§3 two-phase + §4 RBAC re-source):** Phase-1 unchanged (existing login); Phase-2 activation → Tasks 1–8; host-pin/switcher/zero rules → Task 1 resolver + Tasks 4–7 wiring; "org-switch ≠ re-auth" (re-scope + CSRF rotation, no identity re-proof) → Task 7 `/auth/switch-org` + Task 3 store method; graceful degradation → honest `NoOrgs` interim now, invisible in Plan 1c (explicitly deferred, outlined). §4 permit/scope re-source → Tasks 9–10 (`effective_roles`); `grant_schema` re-source + platform roles + audit attribution are §4/§6 items routed to Plan 2 (noted). SSO/SCIM phase mapping (§5) is Plans 4–5.
- **Placeholder scan:** the resolver, store method, routes, and switch edits all carry concrete code. The flagged "verify the exact name/primitive" notes (`get_user_by_id` signature, `_build_access_runtime_context` name, `Field(kind="select")` shape, `check_entity_op` harness, Fragment imports) are real-codebase reconciliations with an explicit confirm step and an invariant assertion that does not change — not deferred work.
- **Type consistency:** `ActivationOutcome` variants (`Activated.membership_id: str`, `NeedsPicker.memberships: tuple[MembershipRecord, ...]`, `NoOrgs`, `HostForbidden`) are used identically in the resolver (Task 1), the login glue (Tasks 4–6), and the routes (Task 7). `set_session_active_membership(session_id, membership_id, *, identity_id) -> bool` has one signature across Task 3 (def), Task 7 (`_activate_and_redirect`), and the tests. `effective_roles` (1a property) is the single roles accessor switched to in Tasks 9–10. `active_membership_id` threads `create_session` (1a) ← login (Tasks 4–6) ← `set_session_active_membership` (Task 3) consistently.
