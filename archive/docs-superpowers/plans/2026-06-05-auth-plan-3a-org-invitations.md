# Auth Plan 3a — Organization Invitations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an org admin invite a person (by email + roles) into their organization, and let the invitee accept — creating an active membership — while honoring the verified-email identity-join rule (the grant binds only to a logged-in identity whose **verified** email matches the invitation, so a stolen link can't grant access to a different account).

**Architecture:** A dedicated `invitations` token table (mirroring `magic_link`) carries the invited *email* + roles + `invited_by` + expiry; the membership is created at **accept** time (not invite time) so an unregistered/unverified invitee never holds a dangling grant. Invite/accept are framework `/auth/` routes (typed-Fragment accept page, `LogMailer`-delivered link in dev). Authorization is a fail-closed, configurable `[auth] org_admin_roles` set: only an active member whose roles intersect that set may invite. Accept reuses Plan 2a's `create_membership` (→ `provisioned` event, `invited_by` attributed) and Plan 1b's `set_session_active_membership` (activate + CSRF rotation).

**Tech Stack:** Python 3.12, psycopg3 (`AuthStore`), FastAPI (`APIRouter`), typed Fragment UI substrate, `secrets.token_urlsafe`, Alembic (ADR-0017), pytest (`e2e`+`postgres`).

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §7 (Tier 1 multi-org), §8 (verified-email identity-join rule), §9 (Plan 3). This is slice **3a** of Plan 3; the org switcher (1b) and member mutations (2a) already exist. **3b** (member-admin UI + in-app switcher) and **3c** (`tenancy: multi_org:` flag + `archetype: profile`) follow.

**Decisions (confirmed):** 3a invitations first; authorization via configurable `[auth] org_admin_roles` (default empty = fail-closed). Mechanism: token-based, membership created at accept, verified-email join.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/auth/invitations.py` (**create**) | `InvitationRecord`, `InvitationError(reason)`, `INVITATIONS_DDL`/`INVITATIONS_INDEXES`, and the store-taking functions `create_invitation`, `get_invitation`, `accept_invitation`, `list_pending_invitations`. The security core (token lifecycle + verified-email join + already-member guard). |
| `src/dazzle/http/runtime/auth/invitation_routes.py` (**create**) | `create_invitation_routes() -> APIRouter`: `POST /auth/invite` (authz-gated), `GET /auth/accept-invite/{token}` (accept page), `POST /auth/accept-invite` (redeem). |
| `src/dazzle/http/runtime/auth/invitation_views.py` (**create**) | `build_accept_invite_view(...)` + `build_invite_result_view(...)` — typed Fragment pages (mirror `org_context_views`). |
| `src/dazzle/http/runtime/auth/mailer.py` (**modify**) | Add `InvitationMailer` Protocol + `LogMailer.send_invitation` + `get_invitation_mailer`. |
| `src/dazzle/http/runtime/auth/store.py` (**modify**) | Add `INVITATIONS_DDL`/indexes to `_init_db`. |
| `src/dazzle/core/manifest.py` (**modify**) | `AuthConfig.org_admin_roles: list[str]` + parse `auth_data.get("org_admin_roles", [])`. |
| `src/dazzle/http/runtime/subsystems/auth.py` (**modify**) | Set `app.state.org_admin_roles`; mount the invitation router. |
| `src/dazzle/http/runtime/csrf.py` (**modify**) | Add `/auth/invite` + `/auth/accept-invite` to `protected_paths` (authenticated `/auth/` POSTs must not fall into NA_PREAUTH). |
| `src/dazzle/http/alembic/versions/0010_invitations.py` (**create**) | Idempotent `invitations` table migration (mirror `0009`). |
| `tests/unit/test_invitations.py` (**create**) | Pure-ish: `InvitationError` reasons, `org_admin_roles` authz predicate. |
| `tests/integration/test_org_invitations_pg.py` (**create**) | Real-PG: full invite→accept happy path; authz gate (non-admin 403); verified-email join (email mismatch / unverified rejected); expiry + single-use; already-member guard; accept emits a `provisioned` event with `invited_by`. |

---

## Task 1: Invitation token substrate (`invitations.py`)

**Files:**
- Create: `src/dazzle/http/runtime/auth/invitations.py`
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db`, after the `membership_events` block ~line 1037)
- Test: `tests/integration/test_org_invitations_pg.py`

- [ ] **Step 1: Write the failing integration test** (happy path)

```python
# tests/integration/test_org_invitations_pg.py
"""Real-PG proof of org invitations (auth Plan 3a)."""

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
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_invite_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=store_url)
    store._init_db()
    return store


def test_invite_then_accept_creates_active_membership(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        accept_invitation,
        create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    # Invitee's email is verified (the join key).
    store._execute_modify("UPDATE users SET email_verified = true WHERE id = %s", (str(invitee.id),))

    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"],
        invited_by=str(inviter.id),
    )
    membership = accept_invitation(
        store, token, identity_id=str(invitee.id),
        accepting_email="bob@acme.test", email_verified=True,
    )
    assert membership.tenant_id == "org-1"
    assert membership.roles == ["member"]
    assert membership.status == "active"
    assert membership.invited_by == str(inviter.id)
    # The accept created a PROVISIONED lifecycle event (Plan 2a) attributed to the inviter.
    events = store.get_membership_events(membership_id=membership.id)
    assert [e.event_type for e in events] == ["provisioned"]
    assert events[0].actor_id == str(inviter.id)
    # The token is now single-use (accepting again raises).
    from dazzle.http.runtime.auth.invitations import InvitationError

    with pytest.raises(InvitationError):
        accept_invitation(
            store, token, identity_id=str(invitee.id),
            accepting_email="bob@acme.test", email_verified=True,
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_org_invitations_pg.py::test_invite_then_accept_creates_active_membership -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.http.runtime.auth.invitations'`

- [ ] **Step 3: Create the module**

```python
# src/dazzle/http/runtime/auth/invitations.py
"""Organization invitations (auth Plan 3a).

An org admin invites a person by *email* + roles; the membership is created when
the invitee *accepts* — never at invite time — so an unregistered or unverified
invitee never holds a dangling grant. The accept binds the grant to a logged-in
identity whose **verified** email matches the invitation (the verified-email
identity-join key, spec §8): a stolen link cannot grant access to a different
account, and JIT provisioning stays safe (no confused-deputy).

Token table mirrors ``magic_link`` (opaque token, TTL, single-use via
``accepted_at``). Accept reuses Plan 2a ``create_membership`` (→ ``provisioned``
event, ``invited_by`` attributed).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

INVITATIONS_DDL = """
CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    email TEXT NOT NULL,
    roles TEXT NOT NULL DEFAULT '[]',
    invited_by TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    created_at TEXT NOT NULL
)
"""

INVITATIONS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_invitations_org ON invitations(org_id)",
    "CREATE INDEX IF NOT EXISTS ix_invitations_email ON invitations(email)",
)


class InvitationError(RuntimeError):
    """An invitation could not be created or accepted. ``reason`` is a stable code
    (``expired`` / ``used`` / ``not_found`` / ``email_mismatch`` / ``unverified``
    / ``already_member``) the routes map to a status + message."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True)
class InvitationRecord:
    token: str
    org_id: str
    email: str
    roles: list[str]
    invited_by: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


def _row_to_invitation(row: dict[str, Any]) -> InvitationRecord:
    return InvitationRecord(
        token=row["token"],
        org_id=row["org_id"],
        email=row["email"],
        roles=json.loads(row["roles"]) if row.get("roles") else [],
        invited_by=row["invited_by"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        accepted_at=datetime.fromisoformat(row["accepted_at"]) if row.get("accepted_at") else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_invitation(
    store: Any,
    *,
    org_id: str,
    email: str,
    roles: list[str],
    invited_by: str,
    ttl_hours: int = 72,
) -> str:
    """Create a pending invitation; returns the opaque token (for the accept URL).

    Authorization (who may invite) is enforced at the route layer, not here.
    Email is normalised to lowercase so the accept-time match is case-insensitive.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
    store._execute_modify(
        """
        INSERT INTO invitations (token, org_id, email, roles, invited_by, expires_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (token, org_id, email.strip().lower(), json.dumps(roles), invited_by, expires_at,
         now.isoformat()),
    )
    return token


def get_invitation(store: Any, token: str) -> InvitationRecord | None:
    rows = store._execute("SELECT * FROM invitations WHERE token = %s", (token,))
    return _row_to_invitation(rows[0]) if rows else None


def list_pending_invitations(store: Any, org_id: str) -> list[InvitationRecord]:
    """Open (not-yet-accepted, not-expired) invitations for an org (for 3b admin UI)."""
    now = datetime.now(UTC).isoformat()
    rows = store._execute(
        "SELECT * FROM invitations WHERE org_id = %s AND accepted_at IS NULL "
        "AND expires_at > %s ORDER BY created_at",
        (org_id, now),
    )
    return [_row_to_invitation(r) for r in rows]


def accept_invitation(
    store: Any,
    token: str,
    *,
    identity_id: str,
    accepting_email: str,
    email_verified: bool,
):  # -> MembershipRecord
    """Redeem an invitation → create an active membership for the accepting identity.

    Enforces (in order): token exists, not already accepted, not expired, and the
    **verified-email join** — the accepting identity's email MUST equal the
    invitation email AND be verified (spec §8; prevents a stolen link granting a
    different account). Idempotency: a pre-existing membership for (org, identity)
    raises ``already_member`` rather than duplicating. Marks the token accepted.
    """
    inv = get_invitation(store, token)
    if inv is None:
        raise InvitationError("not_found", "invitation not found")
    if inv.accepted_at is not None:
        raise InvitationError("used", "invitation already accepted")
    if datetime.now(UTC) > inv.expires_at:
        raise InvitationError("expired", "invitation expired")
    if not email_verified or accepting_email.strip().lower() != inv.email:
        # The grant binds only to the verified identity for the invited email.
        raise InvitationError(
            "email_mismatch" if accepting_email.strip().lower() != inv.email else "unverified",
            "this invitation is for a different (or unverified) email address",
        )
    # Already a member of this org? Don't duplicate (uq_memberships_tenant_identity).
    for m in store.get_memberships_for_identity(identity_id):
        if m.tenant_id == inv.org_id:
            raise InvitationError("already_member", "already a member of this organization")

    membership = store.create_membership(
        tenant_id=inv.org_id,
        identity_id=identity_id,
        roles=inv.roles,
        invited_by=inv.invited_by,
        actor_id=inv.invited_by,
        reason="invitation accepted",
    )
    store._execute_modify(
        "UPDATE invitations SET accepted_at = %s WHERE token = %s",
        (datetime.now(UTC).isoformat(), token),
    )
    return membership
```

- [ ] **Step 4: Add the table to `_init_db`** — in `store.py`, right after the `membership_events` block (the `for _ix in MEMBERSHIP_EVENTS_INDEXES:` loop):

```python
            # auth Plan 3a: org invitation tokens (email-addressed, accept-time
            # membership creation). Mirrors alembic 0010_invitations.
            from dazzle.http.runtime.auth.invitations import (
                INVITATIONS_DDL,
                INVITATIONS_INDEXES,
            )

            cursor.execute(INVITATIONS_DDL)
            for _ix in INVITATIONS_INDEXES:
                cursor.execute(_ix)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_org_invitations_pg.py::test_invite_then_accept_creates_active_membership -q`
Expected: PASS

- [ ] **Step 6: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/invitations.py src/dazzle/http/runtime/auth/store.py tests/integration/test_org_invitations_pg.py --fix
ruff format src/dazzle/http/runtime/auth/invitations.py src/dazzle/http/runtime/auth/store.py tests/integration/test_org_invitations_pg.py
git add src/dazzle/http/runtime/auth/invitations.py src/dazzle/http/runtime/auth/store.py tests/integration/test_org_invitations_pg.py
git commit -m "feat(auth): org invitation token substrate + verified-email accept (Plan 3a)"
```

---

## Task 2: Security edge-case tests (authz join rule, expiry, already-member)

**Files:**
- Test: `tests/integration/test_org_invitations_pg.py` (extend)

- [ ] **Step 1: Add the edge-case tests**

```python
def test_accept_rejects_email_mismatch(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError, accept_invitation, create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    attacker = store.create_user(email="eve@evil.test", password="pw123456", roles=[])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    # Eve holds the link but is a different (even if verified) identity → rejected.
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store, token, identity_id=str(attacker.id),
            accepting_email="eve@evil.test", email_verified=True,
        )
    assert ei.value.reason == "email_mismatch"


def test_accept_rejects_unverified_email(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError, accept_invitation, create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store, token, identity_id=str(invitee.id),
            accepting_email="bob@acme.test", email_verified=False,
        )
    assert ei.value.reason == "unverified"


def test_accept_rejects_expired(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError, accept_invitation, create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"],
        invited_by=str(inviter.id), ttl_hours=0,  # already expired
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store, token, identity_id=str(invitee.id),
            accepting_email="bob@acme.test", email_verified=True,
        )
    assert ei.value.reason == "expired"


def test_accept_rejects_already_member(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        InvitationError, accept_invitation, create_invitation,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    store.create_membership(tenant_id="org-1", identity_id=str(invitee.id), roles=["member"])
    token = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["admin"], invited_by=str(inviter.id)
    )
    with pytest.raises(InvitationError) as ei:
        accept_invitation(
            store, token, identity_id=str(invitee.id),
            accepting_email="bob@acme.test", email_verified=True,
        )
    assert ei.value.reason == "already_member"


def test_list_pending_invitations_excludes_accepted_and_expired(store_url: str) -> None:
    from dazzle.http.runtime.auth.invitations import (
        accept_invitation, create_invitation, list_pending_invitations,
    )

    store = _store(store_url)
    inviter = store.create_user(email="admin@acme.test", password="pw123456", roles=["owner"])
    invitee = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    open_tok = create_invitation(
        store, org_id="org-1", email="carol@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    create_invitation(
        store, org_id="org-1", email="dan@acme.test", roles=["member"],
        invited_by=str(inviter.id), ttl_hours=0,  # expired
    )
    accepted = create_invitation(
        store, org_id="org-1", email="bob@acme.test", roles=["member"], invited_by=str(inviter.id)
    )
    accept_invitation(
        store, accepted, identity_id=str(invitee.id),
        accepting_email="bob@acme.test", email_verified=True,
    )
    pending = list_pending_invitations(store, "org-1")
    assert {p.token for p in pending} == {open_tok}  # only the open one
```

- [ ] **Step 2: Run them**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_org_invitations_pg.py -q`
Expected: PASS (all)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_org_invitations_pg.py
git commit -m "test(auth): invitation accept edge cases — join rule, expiry, dup guard (Plan 3a)"
```

---

## Task 3: `org_admin_roles` config + authz predicate

**Files:**
- Modify: `src/dazzle/core/manifest.py` (`AuthConfig` ~line 160; parsing ~line 855)
- Modify: `src/dazzle/http/runtime/subsystems/auth.py` (set `app.state.org_admin_roles` ~line 66)
- Create: the predicate in `invitations.py`
- Test: `tests/unit/test_invitations.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_invitations.py
"""org_admin_roles authorization predicate + InvitationError (auth Plan 3a)."""

from dazzle.http.runtime.auth.invitations import InvitationError, may_manage_members


def test_may_manage_members_requires_active_membership_role_in_admin_set() -> None:
    # No admin roles configured → nobody may invite (fail-closed).
    assert may_manage_members(["owner"], org_admin_roles=[]) is False
    # Role intersects the configured admin set → allowed.
    assert may_manage_members(["owner", "member"], org_admin_roles=["owner", "admin"]) is True
    # No intersection → denied.
    assert may_manage_members(["member"], org_admin_roles=["owner", "admin"]) is False
    # Empty roles → denied.
    assert may_manage_members([], org_admin_roles=["owner"]) is False


def test_invitation_error_carries_reason() -> None:
    e = InvitationError("expired", "invitation expired")
    assert e.reason == "expired"
    assert "expired" in str(e)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_invitations.py -q`
Expected: FAIL — `ImportError: cannot import name 'may_manage_members'`

- [ ] **Step 3: Add the predicate** to `invitations.py` (after `InvitationError`):

```python
def may_manage_members(effective_roles: list[str], *, org_admin_roles: list[str]) -> bool:
    """True iff a member with ``effective_roles`` may invite/manage members.

    Fail-closed: when no ``org_admin_roles`` are configured, nobody may manage
    members (the app must explicitly designate admin personas). Otherwise the
    member's roles must intersect the configured admin set.
    """
    if not org_admin_roles:
        return False
    return bool(set(effective_roles) & set(org_admin_roles))
```

- [ ] **Step 4: Add `org_admin_roles` to `AuthConfig`** — in `manifest.py`, after `auto_provision_single_org: bool = False` (~line 164):

```python
    # auth Plan 3a: personas allowed to invite / manage org members. Fail-closed —
    # empty means nobody can manage members until the app designates admin roles.
    org_admin_roles: list[str] = field(default_factory=list)
```

And in the `AuthConfig(...)` constructor call (~line 850), add:

```python
        org_admin_roles=auth_data.get("org_admin_roles", []),
```

- [ ] **Step 5: Thread it to `app.state`** — in `subsystems/auth.py`, near `ctx.app.state.memberships_required = _auto_provision` (~line 67):

```python
        _auth_cfg = getattr(ctx.config, "auth_config", None)
        ctx.app.state.org_admin_roles = list(
            getattr(_auth_cfg, "org_admin_roles", []) or []
        )
```

- [ ] **Step 6: Run the unit test to verify it passes**

Run: `python -m pytest tests/unit/test_invitations.py -q`
Expected: PASS

- [ ] **Step 7: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/invitations.py src/dazzle/core/manifest.py src/dazzle/http/runtime/subsystems/auth.py tests/unit/test_invitations.py --fix
ruff format src/dazzle/http/runtime/auth/invitations.py src/dazzle/core/manifest.py src/dazzle/http/runtime/subsystems/auth.py tests/unit/test_invitations.py
git add src/dazzle/http/runtime/auth/invitations.py src/dazzle/core/manifest.py src/dazzle/http/runtime/subsystems/auth.py tests/unit/test_invitations.py
git commit -m "feat(auth): org_admin_roles config + may_manage_members predicate (Plan 3a)"
```

---

## Task 4: Mailer + views

**Files:**
- Modify: `src/dazzle/http/runtime/auth/mailer.py`
- Create: `src/dazzle/http/runtime/auth/invitation_views.py`

- [ ] **Step 1: Add the `InvitationMailer`** to `mailer.py` (after `VerificationMailer`):

```python
@runtime_checkable
class InvitationMailer(Protocol):
    """Contract for delivering an org-invitation accept URL (auth Plan 3a).

    Semantically distinct from magic-link / verification: the link grants
    *membership* of an org on accept (after a verified-email check), not a login.
    """

    def send_invitation(self, *, to_email: str, accept_url: str, org_name: str) -> None: ...
```

Add to `LogMailer`:

```python
    def send_invitation(self, *, to_email: str, accept_url: str, org_name: str) -> None:
        _logger.info("Org-invitation issued for %s to %s: %s", to_email, org_name, accept_url)
```

Add the factory:

```python
def get_invitation_mailer(app_state: object) -> InvitationMailer:
    """Look up an invitation-capable mailer; fall back to LogMailer (dev-safe)."""
    mailer = getattr(app_state, "magic_link_mailer", None)
    if mailer is None or not isinstance(mailer, InvitationMailer):
        return LogMailer()
    typed: InvitationMailer = mailer
    return typed
```

- [ ] **Step 2: Create the views** — `invitation_views.py` (mirror `org_context_views.py`'s Fragment usage):

```python
# src/dazzle/http/runtime/auth/invitation_views.py
"""Typed-Fragment pages for org invitations (auth Plan 3a)."""

from __future__ import annotations

from dazzle.render.fragment.model import (
    Form,
    Heading,
    Hidden,
    Page,
    Stack,
    Submit,
    Text,
)


def build_accept_invite_view(
    *, product_name: str, org_name: str, roles: list[str], token: str, signed_in_email: str | None
) -> Page:
    """The accept-invitation page. Posts the token to POST /auth/accept-invite."""
    role_text = ", ".join(roles) if roles else "member"
    body: list = [
        Heading(text=f"Join {org_name}", level=1),
        Text(text=f"You've been invited to join {org_name} as {role_text}."),
    ]
    if signed_in_email:
        body += [
            Text(text=f"Accepting as {signed_in_email}."),
            Form(
                action="/auth/accept-invite",
                method="post",
                children=[Hidden(name="token", value=token), Submit(label="Accept invitation")],
            ),
        ]
    else:
        body += [
            Text(text="Sign in with the invited email address to accept."),
            Form(
                action=f"/login?next=/auth/accept-invite/{token}",
                method="get",
                children=[Submit(label="Sign in to accept")],
            ),
        ]
    return Page(title=f"Join {org_name} — {product_name}", children=[Stack(children=body)])


def build_invite_result_view(*, product_name: str, message: str) -> Page:
    """A simple result page (invite sent / error)."""
    return Page(
        title=f"Invitation — {product_name}",
        children=[Stack(children=[Heading(text="Invitation", level=1), Text(text=message)])],
    )
```

**NOTE:** the exact Fragment primitive names (`Hidden`, `Form`, `Submit`, `Combobox`, …) must match what `org_context_views.py` actually imports from `dazzle.render.fragment.model`. Before writing, open `org_context_views.py` and reuse the SAME imports/构造 — if `Hidden` doesn't exist, render the token via the form `action` path param instead, or use the primitive the picker uses for its hidden membership_id field.

- [ ] **Step 3: Verify the views import + render** (smoke):

Run: `python -c "from dazzle.http.runtime.auth.invitation_views import build_accept_invite_view; from dazzle.render.fragment.renderer import FragmentRenderer; print('OK' if 'Join' in FragmentRenderer().render(build_accept_invite_view(product_name='X', org_name='Acme', roles=['member'], token='t', signed_in_email='b@x.test')) else 'FAIL')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
ruff check src/dazzle/http/runtime/auth/mailer.py src/dazzle/http/runtime/auth/invitation_views.py --fix
ruff format src/dazzle/http/runtime/auth/mailer.py src/dazzle/http/runtime/auth/invitation_views.py
git add src/dazzle/http/runtime/auth/mailer.py src/dazzle/http/runtime/auth/invitation_views.py
git commit -m "feat(auth): invitation mailer seam + accept-page views (Plan 3a)"
```

---

## Task 5: Invitation routes + mounting + CSRF

**Files:**
- Create: `src/dazzle/http/runtime/auth/invitation_routes.py`
- Modify: `src/dazzle/http/runtime/subsystems/auth.py` (mount the router)
- Modify: `src/dazzle/http/runtime/csrf.py` (`protected_paths`)
- Test: `tests/integration/test_org_invitations_pg.py` (CLI/route-level — optional in-process app test)

- [ ] **Step 1: Add the paths to CSRF `protected_paths`** — in `csrf.py`, the `protected_paths` default list (~line 123) currently has `"/auth/select-org"`, `"/auth/switch-org"`. Add:

```python
            "/auth/invite",
            "/auth/accept-invite",
```

- [ ] **Step 2: Create the routes** — `invitation_routes.py`:

```python
# src/dazzle/http/runtime/auth/invitation_routes.py
"""Org invitation routes (auth Plan 3a): invite / accept.

``POST /auth/invite``               — an org admin invites email+roles into their
                                       active org (authz: may_manage_members)
``GET  /auth/accept-invite/{token}`` — accept page (verified-email gated on POST)
``POST /auth/accept-invite``         — redeem token → active membership + activate

Authz: the inviter must have an ACTIVE membership in their active org whose roles
intersect ``app.state.org_admin_roles`` (fail-closed). Accept enforces the
verified-email join rule in ``invitations.accept_invitation``.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def create_invitation_routes() -> APIRouter:
    from dazzle.http.runtime.auth.cookie_name import read_session_id

    router = APIRouter(tags=["auth"])

    @router.post("/auth/invite", include_in_schema=False)
    async def invite(
        request: Request,
        email: Annotated[str, Form()] = "",
        roles: Annotated[str, Form()] = "",  # comma-separated personas
    ) -> HTMLResponse:
        from dazzle.http.runtime.auth.invitation_views import build_invite_result_view
        from dazzle.http.runtime.auth.invitations import create_invitation, may_manage_members
        from dazzle.http.runtime.auth.mailer import get_invitation_mailer
        from dazzle.http.runtime.auth.models import effective_roles_of
        from dazzle.render.fragment.renderer import FragmentRenderer

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.active_membership is None:
            return HTMLResponse("Forbidden", status_code=403)
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        if not may_manage_members(
            list(effective_roles_of(ctx)), org_admin_roles=org_admin_roles
        ):
            return HTMLResponse("Forbidden — you cannot manage members of this org", status_code=403)
        if not email.strip():
            return HTMLResponse("Email required", status_code=400)

        org_id = ctx.active_membership.tenant_id
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        token = create_invitation(
            store, org_id=org_id, email=email, roles=role_list, invited_by=str(ctx.user.id)
        )
        org = store.get_organization(org_id)
        org_name = org.name if org is not None else org_id
        accept_url = f"{request.base_url}auth/accept-invite/{token}".rstrip("/")
        get_invitation_mailer(request.app.state).send_invitation(
            to_email=email.strip().lower(), accept_url=accept_url, org_name=org_name
        )
        page = build_invite_result_view(
            product_name=_product_name(request),
            message=f"Invitation sent to {email.strip().lower()}.",
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.get("/auth/accept-invite/{token}", response_class=HTMLResponse, include_in_schema=False)
    async def accept_page(request: Request, token: str) -> str:
        from dazzle.http.runtime.auth.invitation_views import build_accept_invite_view
        from dazzle.http.runtime.auth.invitations import get_invitation
        from dazzle.render.fragment.renderer import FragmentRenderer

        store = request.app.state.auth_store
        inv = get_invitation(store, token)
        if inv is None or inv.accepted_at is not None:
            return FragmentRenderer().render(
                build_accept_invite_view(
                    product_name=_product_name(request), org_name="(invalid)", roles=[],
                    token=token, signed_in_email=None,
                )
            )
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        signed_in_email = (
            ctx.user.email if ctx is not None and ctx.is_authenticated and ctx.user else None
        )
        org = store.get_organization(inv.org_id)
        return FragmentRenderer().render(
            build_accept_invite_view(
                product_name=_product_name(request),
                org_name=org.name if org is not None else inv.org_id,
                roles=inv.roles,
                token=token,
                signed_in_email=signed_in_email,
            )
        )

    @router.post("/auth/accept-invite", include_in_schema=False)
    async def accept_submit(
        request: Request, token: Annotated[str, Form()] = ""
    ) -> HTMLResponse | RedirectResponse:
        from dazzle.http.runtime.auth.crypto import cookie_secure
        from dazzle.http.runtime.auth.invitations import InvitationError, accept_invitation

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return RedirectResponse(url=f"/login?next=/auth/accept-invite/{token}", status_code=303)
        try:
            membership = accept_invitation(
                store, token, identity_id=str(ctx.user.id),
                accepting_email=ctx.user.email,
                email_verified=bool(getattr(ctx.user, "email_verified", False)),
            )
        except InvitationError as exc:
            return HTMLResponse(f"Cannot accept invitation: {exc.reason}", status_code=400)
        # Activate the new membership (+ CSRF rotation), then land in the app.
        store.set_session_active_membership(session_id, membership.id, identity_id=str(ctx.user.id))
        response = RedirectResponse(url="/app", status_code=303)
        new_secret = store.regenerate_session_csrf(session_id)
        response.set_cookie(
            key="dazzle_csrf", value=new_secret, httponly=False,
            secure=cookie_secure(request), samesite="lax",
        )
        return response

    return router
```

- [ ] **Step 3: Mount the router** — in `subsystems/auth.py`, near `create_org_context_routes()` mount (search for `create_org_context_routes`), add:

```python
        from dazzle.http.runtime.auth.invitation_routes import create_invitation_routes

        ctx.app.include_router(create_invitation_routes())
```

(Use the SAME `ctx.app.include_router(...)` form the file already uses for `create_org_context_routes()` — match it exactly.)

- [ ] **Step 4: Route-level integration test** — append to `tests/integration/test_org_invitations_pg.py` an in-process app test that boots a minimal app, logs in an admin, POSTs `/auth/invite`, scrapes the LogMailer URL, and accepts. If wiring a full in-process app is heavy, assert the authz gate at the predicate level (Task 3) + the store flow (Tasks 1–2) and add a focused route test only for the **403 authz gate** (non-admin invite) using the boot harness pattern from `tests/integration/test_auth_activation_pg.py`. Match that file's app-boot fixture.

```python
def test_invite_route_denies_non_admin(store_url: str) -> None:
    # The route gate: a member whose roles don't intersect org_admin_roles gets 403.
    from dazzle.http.runtime.auth.invitations import may_manage_members

    # Unit-level guard already covers may_manage_members; this asserts the empty
    # (fail-closed) default denies even an "owner".
    assert may_manage_members(["owner"], org_admin_roles=[]) is False
```

(If the boot harness is readily reusable, prefer a real `POST /auth/invite` 403 assertion; otherwise the predicate guard above plus the store-level tests are sufficient coverage for 3a — note the gap.)

- [ ] **Step 5: Run + commit**

```bash
ruff check src/dazzle/http/runtime/auth/invitation_routes.py src/dazzle/http/runtime/subsystems/auth.py src/dazzle/http/runtime/csrf.py --fix
ruff format src/dazzle/http/runtime/auth/invitation_routes.py src/dazzle/http/runtime/subsystems/auth.py src/dazzle/http/runtime/csrf.py
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_org_invitations_pg.py -q
git add -A
git commit -m "feat(auth): invitation routes (invite/accept) + mount + CSRF protect (Plan 3a)"
```

---

## Task 6: Alembic migration `0010_invitations`

**Files:**
- Create: `src/dazzle/http/alembic/versions/0010_invitations.py`
- Test: `tests/integration/test_org_invitations_pg.py` (migration-applies test)

- [ ] **Step 1: Write the failing test** (mirror `test_membership_events_pg.test_migration_0009_*`):

```python
def test_migration_0010_creates_invitations(store_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    _store(store_url)  # auth tables present (incl. invitations via _init_db)
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS invitations")

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option("sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://"))
    command.stamp(cfg, "0009_membership_events")
    command.upgrade(cfg, "0010_invitations")

    with psycopg.connect(store_url) as c:
        ok = c.execute("SELECT to_regclass('public.invitations') IS NOT NULL").fetchone()[0]
        ver = c.execute("SELECT version_num FROM alembic_version").fetchone()
    assert ok is True
    assert ver is not None and ver[0] == "0010_invitations"
```

- [ ] **Step 2: Run to verify it fails** (revision not found), then create the migration:

```python
# src/dazzle/http/alembic/versions/0010_invitations.py
"""Add invitations table (auth Plan 3a — org invitation tokens).

Email-addressed invitation tokens; the membership is created at accept time
(verified-email join). Idempotent (guards on table presence); mirrors
0009_membership_events. No DB FK (auth tables live outside the DSL metadata).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0010_invitations"
down_revision = "0009_membership_events"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("invitations"):
        op.create_table(
            "invitations",
            sa.Column("token", sa.Text(), primary_key=True),
            sa.Column("org_id", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("roles", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("invited_by", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("accepted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
        op.create_index("ix_invitations_org", "invitations", ["org_id"])
        op.create_index("ix_invitations_email", "invitations", ["email"])


def downgrade() -> None:
    if _has_table("invitations"):
        op.drop_table("invitations")
```

- [ ] **Step 3: Run the test + commit**

```bash
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_org_invitations_pg.py::test_migration_0010_creates_invitations -q
git add src/dazzle/http/alembic/versions/0010_invitations.py tests/integration/test_org_invitations_pg.py
git commit -m "feat(auth): alembic 0010 invitations table (Plan 3a)"
```

---

## Task 7: Full verification + regression

- [ ] **Step 1:** `mypy src/dazzle` (clean). New cross-module attrs: `effective_roles_of` import in routes, `app.state.org_admin_roles`. Fix any typing.
- [ ] **Step 2:** `python -m pytest tests/ -m "not e2e" -q` — full unit slice. Watch: `manifest` parsing tests (AuthConfig got a field), CSRF disposition tests (protected_paths grew), api-surface drift (runtime-urls baseline — a new router adds routes; if `tests/unit/test_api_surface_drift.py` flags `runtime-urls`, regenerate with `dazzle inspect api runtime-urls --write` and add a CHANGELOG note).
- [ ] **Step 3:** `TEST_DATABASE_URL=... python -m pytest tests/integration/test_org_invitations_pg.py tests/integration/test_membership_events_pg.py tests/integration/test_auth_membership_pg.py -q` — invitation + the create_membership-caller regression.
- [ ] **Step 4:** Commit any regen/drift fixes.

---

## Task 8: Adversarial review checkpoint (MANDATORY — security-sensitive)

- [ ] **Step 1: Dispatch an independent reviewer** with this brief:
  - **Verified-email join (the core invariant):** can a stolen accept link grant access to a *different* account? Is the email compared case-insensitively and trimmed on BOTH write and accept? Is `email_verified` actually enforced (not just present)? Can an unverified or mismatched email ever create a membership?
  - **Authorization (invite):** is the invite gate fail-closed (empty `org_admin_roles` → nobody)? Does it use `effective_roles_of` (membership-sourced, Plan 1b) not `user.roles`? Can a member invite into an org they're NOT an active member of (the org is taken from the *active membership*, not request input — confirm)? Can a suspended member invite?
  - **Token security:** opaque (`token_urlsafe(32)`), single-use (`accepted_at`), expiring? Any timing/enumeration leak in `get_invitation`? Is the token ever logged except via the dev `LogMailer`?
  - **CSRF:** are `/auth/invite` + `/auth/accept-invite` actually in `protected_paths` (authenticated `/auth/` POSTs, else NA_PREAUTH-exempt)? Does the accept POST rotate CSRF on the privilege change?
  - **Privilege escalation via roles:** the inviter sets the invitee's roles — can they grant roles they don't hold / above their own? (3a allows any roles; flag whether that's intended or needs a "can't grant above self" guard — likely a 3b policy concern, note it.)
  - **Already-member / idempotency:** does the dup guard prevent a second membership? Does a `UniqueViolation` leak a 500 instead of a clean `already_member`?
  - **Silent failure:** does `accept_invitation` ever swallow an error and create a partial state (token marked accepted but membership not created, or vice versa)? Note: the membership create + token-mark are two statements — is there a window where the membership is created but the token isn't marked (replayable)?

- [ ] **Step 2:** Fix CRITICAL/HIGH inline; re-run. The two-statement accept (create membership, then mark token) is the most likely finding — consider doing both in one `_transaction()` (like 2a) so an accepted token always corresponds to a created membership and vice versa.

- [ ] **Step 3:** `git commit -m "fix(auth): Plan 3a adversarial review hardening"`

---

## Task 9: CHANGELOG + ship

- [ ] **Step 1: CHANGELOG `### Added`:** describe `POST /auth/invite` + accept flow, the verified-email join rule, `[auth] org_admin_roles` (fail-closed), the `invitations` table + Alembic 0010, accept→`provisioned` event reuse. `### Agent Guidance`: invites are email-addressed, membership created at accept under a verified-email check; configure `[auth] org_admin_roles` or nobody can invite; the dev `LogMailer` logs the accept URL.
- [ ] **Step 2:** `/bump patch`, then `/ship`.

---

## Self-Review

**1. Spec coverage:** invitations (§9 Plan 3) → invite/accept flow ✓. Verified-email identity-join (§8) → `accept_invitation` enforces verified + matching email ✓. Multi-org Tier 1 (§7) — invitations are the first piece; switcher (1b) + member-admin (3b) + `multi_org`/`profile` (3c) are the rest, explicitly deferred. Authz → `org_admin_roles` fail-closed ✓.

**2. Placeholder scan:** every code step has full code. The one soft spot — Task 4's Fragment primitive names and Task 5's route-mount form — are explicitly flagged to match the existing `org_context_views.py`/`subsystems/auth.py` at execution time (verify-then-write), not guessed. The Task 5 route test is scoped down with a noted coverage boundary.

**3. Type consistency:** `InvitationRecord`/`InvitationError(reason)`/`create_invitation`/`accept_invitation`/`may_manage_members` signatures match across `invitations.py`, the routes, and the tests. `accept_invitation` returns a `MembershipRecord` (from `store.create_membership`) used by the route's `set_session_active_membership`. `effective_roles_of(ctx)` (Plan 1b) is the role source. `org_admin_roles` flows manifest→AuthConfig→app.state→route.

**Open risks flagged for execution:** (a) the two-statement accept atomicity (Task 8 — wrap in `_transaction()` if the reviewer confirms the replay window); (b) api-surface `runtime-urls` drift from the new router (Task 7 — regenerate baseline + CHANGELOG); (c) exact Fragment primitives (Task 4 — match `org_context_views.py`).
