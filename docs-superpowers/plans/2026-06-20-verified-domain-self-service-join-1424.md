# Verified-Domain Self-Service Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a non-SSO (password) user with a DNS-verified email address self-service join the tenant that owns their email domain, governed by a per-tenant join policy, with a tenant-wide membership-domain admission restriction.

**Architecture:** Reuse the existing connection + DNS-TXT domain-verification machinery by adding a provider-less connection `type="domain"`. Add per-tenant settings (`domain_join_policy`, `restrict_membership_to_verified_domains`) on a new `organizations.settings` JSON column. Two pure decision mappers — `decide_domain_join` (policy → outcome) and `assert_domain_admissible` (the uniform restriction gate) — keep behaviour traceable and exhaustively unit-testable. A `JoinRequest` record backs the `admin_approval` path. Routing is unchanged: a membership (auto-created or admin-approved) is the grant; apex discovery then routes on the next request. No pre-membership host routing (no 403 bounce, no enumeration oracle).

**Tech Stack:** Python 3.12+, FastAPI, psycopg3 (PostgreSQL-only runtime, ADR-0008), Pydantic models, Alembic (ADR-0017), typed-Fragment views (no Jinja2, ADR-0023), dnspython (`[sso]` extra, lazy).

## Global Constraints

- **PostgreSQL-only** in `src/dazzle/http/` (ADR-0008). No SQLite.
- **All schema changes via Alembic** AND the `_init_db` mirror — auth tables are dual-written; changes go in BOTH (auth-store parity gate). New columns/tables: `dazzle db revision -m "..."` then mirror in `store._init_db`.
- **No `from __future__ import annotations`** in FastAPI route files (ADR-0014).
- **No new singletons** — thread state via `app.state` / `RuntimeServices` (ADR-0005).
- **No backward-compat shims** — clean breaks, update all callers in the same commit (ADR-0003).
- **Type hints required** on all public functions (mypy `mypy src/dazzle`).
- **Pre-ship gates:** `pytest tests/ -m "not e2e"`, `ruff check src/ tests/ --fix && ruff format src/ tests/`, `mypy src/dazzle`. When touching migrations/boot, also `DATABASE_URL=… pytest -m postgres`.
- **email_verified is load-bearing:** no self-service join path may create a membership for an identity whose `email_verified` is False. This is the anti-hijack invariant for self-asserted emails.
- **Routing is never a grant:** membership creation is the only grant; routing follows an existing membership.
- **Default-off:** `domain_join_policy` default `admin_approval` but inert until a domain is verified; `restrict_membership_to_verified_domains` default `False`. Phases 1–2 land safely without changing any existing app's behaviour.
- **Ship discipline:** `/bump patch` + CHANGELOG entry per shipped phase; clean worktree.

---

## File Structure

**New files:**
- `src/dazzle/http/runtime/auth/org_settings.py` — typed per-tenant settings model + parse/serialize helpers (`OrgSettings`, `domain_join_policy`, `restrict_membership_to_verified_domains`).
- `src/dazzle/http/runtime/auth/domain_join.py` — pure decision logic: `decide_domain_join`, `assert_domain_admissible`, `resolve_domain_tenant`, `tenant_verified_domains`, shared `email_domain`.
- `src/dazzle/http/runtime/auth/join_requests.py` — `JoinRequest` record + store-agnostic create/approve/deny orchestration helpers.
- `src/dazzle/http/runtime/auth/join_request_routes.py` — the "request submitted" view + admin approve/deny actions.
- `src/dazzle/http/alembic/versions/0017_org_settings.py` — `organizations.settings` column.
- `src/dazzle/http/alembic/versions/0018_join_requests.py` — `join_requests` table.
- `examples/domain_join_co/` — worked-example app (Gap 2): DSL + guides.
- `docs/reference/verified-domain-join.md` — CLI runbook (Gap 2).

**Modified files:**
- `src/dazzle/http/runtime/auth/connections.py` — register a no-op provider OR document type guard; add `"domain"` to the type docstring.
- `src/dazzle/http/runtime/auth/store.py` — `get_connection_by_verified_domain` SSO-type filter; org-settings accessors; join-request CRUD; `_init_db` mirrors; connections-by-type helper.
- `src/dazzle/http/runtime/auth/models.py` — add `settings: dict` to `OrganizationRecord`; add `JoinRequestRecord`.
- `src/dazzle/http/runtime/auth/enterprise_routes.py` + `saml_routes.py` — restrict domain→connection routing to SSO types (exclude `"domain"`).
- `src/dazzle/http/runtime/auth/invitations.py` — `assert_domain_admissible` gate before `create_membership` (line 175).
- `src/dazzle/http/runtime/auth/enterprise_login.py` — `assert_domain_admissible` gate (line ~145, uniform; no-op in practice for SSO).
- `src/dazzle/http/runtime/auth/scim_provisioning.py` — `assert_domain_admissible` gate before `create_membership` (line 385).
- `src/dazzle/http/runtime/auth/password_login_routes.py` — evaluate `decide_domain_join` when login resolves no membership and email is verified.
- `src/dazzle/http/runtime/auth/email_verification_routes.py` — re-evaluate `decide_domain_join` post-verification (line ~108).
- `src/dazzle/http/runtime/auth/connection_admin_routes.py` + `connection_admin_views.py` — domain-connection create affordance, join-policy selector, restrict toggle.
- `src/dazzle/http/runtime/auth/member_admin_routes.py` + `member_admin_views.py` — join-requests approval queue.
- `.claude/CLAUDE.md` (examples line) + `tests/unit/test_docs_drift.py` — register the new example.

---

## Phase 1 — Data model + admission gate

Lands the settings column, the `JoinRequest` table, the pure restriction gate, and wires the gate into every membership-creating path. All inert by default (`restrict=False`).

### Task 1.1: `OrganizationRecord.settings` + Alembic + `_init_db` mirror

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py:86-107` (OrganizationRecord)
- Create: `src/dazzle/http/alembic/versions/0017_org_settings.py`
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db` connections/orgs DDL area ~line 2487; `_row_to_organization` / `get_organization`; `create_organization`)
- Test: `tests/unit/test_org_settings.py`, `tests/integration/test_org_settings_pg.py`

**Interfaces:**
- Produces: `OrganizationRecord.settings: dict[str, Any]` (default `{}`); `store.get_org_settings(tenant_id) -> dict`, `store.set_org_settings(tenant_id, settings: dict) -> None`.

- [ ] **Step 1: Write the failing test** (`tests/unit/test_org_settings.py`)

```python
from dazzle.http.runtime.auth.models import OrganizationRecord


def test_organization_record_has_settings_default_empty():
    org = OrganizationRecord(id="t1", slug="acme", name="Acme")
    assert org.settings == {}


def test_organization_record_settings_roundtrip():
    org = OrganizationRecord(
        id="t1", slug="acme", name="Acme",
        settings={"domain_join_policy": "auto_join"},
    )
    assert org.settings["domain_join_policy"] == "auto_join"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_org_settings.py -v`
Expected: FAIL — `OrganizationRecord` has no `settings` field (pydantic ignores/errors on unknown kwarg).

- [ ] **Step 3: Add the field**

In `models.py`, add to `OrganizationRecord` (after `is_test`):

```python
    settings: dict[str, Any] = Field(default_factory=dict)
```

Ensure `from typing import Any` and `Field` are imported (Field already is).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_org_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Add the Alembic migration** (`0017_org_settings.py`)

Mirror `0011_connections.py`'s guarded style. `down_revision` = the current head (verify with `dazzle db heads`; the auth lineage head as of this plan is the latest `00NN_*`):

```python
"""Add organizations.settings JSON column (verified-domain join, #1424)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0017_org_settings"
down_revision = "0016_<CURRENT_HEAD>"  # set to the real current head
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa_inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("organizations", "settings"):
        op.add_column(
            "organizations",
            sa.Column("settings", sa.Text(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    if _has_column("organizations", "settings"):
        op.drop_column("organizations", "settings")
```

- [ ] **Step 6: Mirror in `_init_db` + read/write path**

In `store.py`: add `settings TEXT NOT NULL DEFAULT '{}'` to the organizations `CREATE TABLE IF NOT EXISTS` in `_init_db`; in `_row_to_organization` parse `json.loads(row["settings"] or "{}")` into `settings`; in `create_organization` insert `settings='{}'`. Add accessors:

```python
    def get_org_settings(self, tenant_id: str) -> dict[str, Any]:
        org = self.get_organization(tenant_id)
        return dict(org.settings) if org else {}

    def set_org_settings(self, tenant_id: str, settings: dict[str, Any]) -> None:
        self._execute(
            "UPDATE organizations SET settings = %s, updated_at = %s WHERE id = %s",
            (json.dumps(settings), _now_iso(), tenant_id),
            commit=True,
        )
```

(Match the exact `_execute`/commit and timestamp idiom already used in `store.py`; `json` is already imported.)

- [ ] **Step 7: Add the Postgres integration test** (`tests/integration/test_org_settings_pg.py`, `@pytest.mark.postgres`)

```python
import pytest


@pytest.mark.postgres
def test_org_settings_roundtrip_pg(auth_store_pg):
    org = auth_store_pg.create_organization(slug="acme", name="Acme")
    auth_store_pg.set_org_settings(org.id, {"domain_join_policy": "auto_join"})
    assert auth_store_pg.get_org_settings(org.id) == {"domain_join_policy": "auto_join"}
```

(Use the existing PG auth-store fixture — find its name in `tests/integration/conftest.py`; replace `auth_store_pg` to match.)

- [ ] **Step 8: Run, then commit**

Run: `pytest tests/unit/test_org_settings.py -v` (PASS) and, with a DB, `DATABASE_URL=… pytest tests/integration/test_org_settings_pg.py -v`.

```bash
git add src/dazzle/http/runtime/auth/models.py src/dazzle/http/runtime/auth/store.py \
  src/dazzle/http/alembic/versions/0017_org_settings.py \
  tests/unit/test_org_settings.py tests/integration/test_org_settings_pg.py
git commit -m "feat(auth): organizations.settings JSON column (#1424 phase 1)"
```

### Task 1.2: Typed `OrgSettings` accessor

**Files:**
- Create: `src/dazzle/http/runtime/auth/org_settings.py`
- Test: `tests/unit/test_org_settings_model.py`

**Interfaces:**
- Produces: `OrgSettings` (frozen pydantic) with `domain_join_policy: Literal["off","auto_join","admin_approval"] = "admin_approval"`, `restrict_membership_to_verified_domains: bool = False`; `OrgSettings.from_dict(d) -> OrgSettings`; `.to_dict() -> dict`.

- [ ] **Step 1: Write the failing test**

```python
from dazzle.http.runtime.auth.org_settings import OrgSettings


def test_defaults_admin_approval_and_unrestricted():
    s = OrgSettings.from_dict({})
    assert s.domain_join_policy == "admin_approval"
    assert s.restrict_membership_to_verified_domains is False


def test_unknown_policy_coerced_to_default():
    s = OrgSettings.from_dict({"domain_join_policy": "garbage"})
    assert s.domain_join_policy == "admin_approval"


def test_roundtrip():
    s = OrgSettings(domain_join_policy="auto_join", restrict_membership_to_verified_domains=True)
    assert OrgSettings.from_dict(s.to_dict()) == s
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/unit/test_org_settings_model.py -v` → import error.

- [ ] **Step 3: Implement** (`org_settings.py`)

```python
"""Typed per-tenant auth settings (verified-domain join, #1424).

Stored as the ``organizations.settings`` JSON blob; this is the typed view.
Unknown / malformed values coerce to the safe default (fail-closed posture).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

JoinPolicy = Literal["off", "auto_join", "admin_approval"]
_POLICIES: frozenset[str] = frozenset({"off", "auto_join", "admin_approval"})


class OrgSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_join_policy: JoinPolicy = "admin_approval"
    restrict_membership_to_verified_domains: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrgSettings":
        raw = d.get("domain_join_policy")
        policy: JoinPolicy = raw if raw in _POLICIES else "admin_approval"  # type: ignore[assignment]
        return cls(
            domain_join_policy=policy,
            restrict_membership_to_verified_domains=bool(
                d.get("restrict_membership_to_verified_domains", False)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_join_policy": self.domain_join_policy,
            "restrict_membership_to_verified_domains": self.restrict_membership_to_verified_domains,
        }
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/org_settings.py tests/unit/test_org_settings_model.py
git commit -m "feat(auth): typed OrgSettings for domain-join policy (#1424 phase 1)"
```

### Task 1.3: `assert_domain_admissible` + domain helpers (pure)

**Files:**
- Create: `src/dazzle/http/runtime/auth/domain_join.py`
- Test: `tests/unit/test_domain_join_admission.py`

**Interfaces:**
- Consumes: `store.get_org_settings`, `store.get_connections_for_tenant` (exists, store.py:1282).
- Produces:
  - `email_domain(email: str) -> str`
  - `tenant_verified_domains(store, tenant_id: str) -> set[str]`
  - `assert_domain_admissible(store, tenant_id: str, email: str) -> None` (raises `DomainNotAdmissibleError` when the tenant restricts and the email domain is not verified; no-op otherwise).
  - `class DomainNotAdmissibleError(RuntimeError)` with `.reason = "domain_not_admissible"`.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from dazzle.http.runtime.auth.domain_join import (
    DomainNotAdmissibleError,
    assert_domain_admissible,
    email_domain,
    tenant_verified_domains,
)


class _Conn:
    def __init__(self, verified): self.verified_domains = verified


class _Store:
    def __init__(self, settings, conns): self._s = settings; self._c = conns
    def get_org_settings(self, t): return self._s
    def get_connections_for_tenant(self, t): return self._c


def test_email_domain_lowercased():
    assert email_domain("Alice@BigCorp.COM") == "bigcorp.com"


def test_union_of_verified_domains():
    store = _Store({}, [_Conn(["a.com"]), _Conn(["B.com", "a.com"])])
    assert tenant_verified_domains(store, "t1") == {"a.com", "b.com"}


def test_admissible_noop_when_unrestricted():
    store = _Store({"restrict_membership_to_verified_domains": False}, [])
    assert_domain_admissible(store, "t1", "x@anywhere.com")  # no raise


def test_restricted_rejects_outside_domain():
    store = _Store({"restrict_membership_to_verified_domains": True}, [_Conn(["bigcorp.com"])])
    with pytest.raises(DomainNotAdmissibleError):
        assert_domain_admissible(store, "t1", "x@other.com")


def test_restricted_allows_verified_domain():
    store = _Store({"restrict_membership_to_verified_domains": True}, [_Conn(["bigcorp.com"])])
    assert_domain_admissible(store, "t1", "x@BigCorp.com")  # no raise
```

- [ ] **Step 2: Run to verify it fails** — import error.

- [ ] **Step 3: Implement** (`domain_join.py`, admission portion)

```python
"""Verified-domain self-service join — pure decision logic (#1424).

Two concerns, kept separate:
  * admission control (``assert_domain_admissible``) — the uniform tenant
    restriction enforced on EVERY membership-creating path;
  * join policy (``decide_domain_join``, Task 3.x) — what a verified-domain
    match does (off / auto_join / admin_approval).

No FastAPI, no DB driver — the store is passed in, so this is exhaustively
unit-testable (mirrors apex_discovery.resolve_apex_redirect's style).
"""

from typing import Any

from dazzle.http.runtime.auth.org_settings import OrgSettings


class DomainNotAdmissibleError(RuntimeError):
    """A membership cannot be created: the tenant restricts membership to its
    verified domains and this email's domain is not among them."""

    reason = "domain_not_admissible"


def email_domain(email: str) -> str:
    """Lowercased domain part of ``email``, or ``""`` if malformed."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def tenant_verified_domains(store: Any, tenant_id: str) -> set[str]:
    """Union of verified domains across all the tenant's connections."""
    out: set[str] = set()
    for conn in store.get_connections_for_tenant(tenant_id):
        out.update(d.strip().lower() for d in (conn.verified_domains or []))
    return out


def assert_domain_admissible(store: Any, tenant_id: str, email: str) -> None:
    """Fail-closed admission gate. No-op when the tenant does not restrict;
    otherwise the email's domain MUST be in the tenant's verified set."""
    settings = OrgSettings.from_dict(store.get_org_settings(tenant_id))
    if not settings.restrict_membership_to_verified_domains:
        return
    domain = email_domain(email)
    if not domain or domain not in tenant_verified_domains(store, tenant_id):
        raise DomainNotAdmissibleError(
            f"email domain {domain!r} is not a verified domain for this organization"
        )
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/domain_join.py tests/unit/test_domain_join_admission.py
git commit -m "feat(auth): assert_domain_admissible admission gate (#1424 phase 1)"
```

### Task 1.4: Wire the admission gate into all membership-creating paths

**Files:**
- Modify: `src/dazzle/http/runtime/auth/invitations.py:165-175` (after email_verified gate, before create_membership)
- Modify: `src/dazzle/http/runtime/auth/enterprise_login.py:144-146` (before create_membership)
- Modify: `src/dazzle/http/runtime/auth/scim_provisioning.py:383-385` (before create_membership)
- Test: `tests/unit/test_membership_admission_gate.py`

**Interfaces:**
- Consumes: `assert_domain_admissible` (Task 1.3).
- Note: `qa_provision.py:45` and `store.ensure_single_org_membership` (store.py:2105) are framework/admin-internal — **exempt** (do not gate).
- Note: the manual admin "add member" flow goes through `invitations.accept_invitation`, so gating invitations covers it.

- [ ] **Step 1: Write the failing test** — each path raises when the tenant restricts and the email is off-domain. Example for invitations:

```python
import pytest

from dazzle.http.runtime.auth.domain_join import DomainNotAdmissibleError
from dazzle.http.runtime.auth import invitations


def test_accept_invitation_rejects_off_domain_when_restricted(restricting_store, pending_invite):
    with pytest.raises(DomainNotAdmissibleError):
        invitations.accept_invitation(
            restricting_store, pending_invite.token,
            identity_id="u1", accepting_email="x@other.com", email_verified=True,
        )
```

(Build `restricting_store`/`pending_invite` from the existing invitation test fixtures in `tests/unit/test_invitations.py`; the store must return `restrict_membership_to_verified_domains: True` and a connection whose verified domains exclude `other.com`.)

- [ ] **Step 2: Run to verify it fails** — no gate yet, `create_membership` is reached.

- [ ] **Step 3: Insert the gate**

`invitations.py` after the `email_verified` check (~line 165), before `create_membership`:

```python
    from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

    assert_domain_admissible(store, inv.org_id, accepting_email)
```

`enterprise_login.py` immediately before the `create_membership` call (~line 145):

```python
    from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

    assert_domain_admissible(store, connection.tenant_id, email)
```

`scim_provisioning.py` before its `create_membership` (~line 384) — use the asserted/provisioned email variable in scope:

```python
    from dazzle.http.runtime.auth.domain_join import assert_domain_admissible

    assert_domain_admissible(store, connection.tenant_id, <provisioned_email_var>)
```

(Replace `<provisioned_email_var>` with the email already computed in that function.)

- [ ] **Step 4: Run to verify it passes** — all three path tests PASS; existing invitation/SSO/SCIM tests still green (`pytest tests/unit/test_invitations.py tests/unit/test_enterprise_login.py -q`).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/invitations.py src/dazzle/http/runtime/auth/enterprise_login.py \
  src/dazzle/http/runtime/auth/scim_provisioning.py tests/unit/test_membership_admission_gate.py
git commit -m "feat(auth): enforce domain admission on all membership paths (#1424 phase 1)"
```

### Task 1.5: `JoinRequest` record + table + store CRUD

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py` (add `JoinRequestRecord`)
- Create: `src/dazzle/http/alembic/versions/0018_join_requests.py`
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db` mirror + CRUD)
- Test: `tests/unit/test_join_request_store.py`, `tests/integration/test_join_requests_pg.py`

**Interfaces:**
- Produces: `JoinRequestRecord` (`id, tenant_id, identity_id, email, status, created_at, decided_at, decided_by`); store methods:
  - `create_join_request(*, tenant_id, identity_id, email) -> JoinRequestRecord` (idempotent on an existing pending `(tenant_id, identity_id)` — returns it).
  - `get_pending_join_requests(tenant_id) -> list[JoinRequestRecord]`
  - `get_join_request(request_id) -> JoinRequestRecord | None`
  - `decide_join_request(request_id, *, status: Literal["approved","denied"], decided_by: str) -> JoinRequestRecord`

- [ ] **Step 1: Write the failing test** (unit, against a fake or the PG store — prefer PG integration for the CRUD; a unit test for the record shape):

```python
from dazzle.http.runtime.auth.models import JoinRequestRecord


def test_join_request_defaults_pending():
    jr = JoinRequestRecord(id="r1", tenant_id="t1", identity_id="u1", email="x@a.com")
    assert jr.status == "pending"
    assert jr.decided_at is None and jr.decided_by is None
```

- [ ] **Step 2: Run to verify it fails** — no `JoinRequestRecord`.

- [ ] **Step 3: Add the record** (`models.py`)

```python
class JoinRequestRecord(BaseModel):
    """A pending/decided self-service join request (verified-domain join, #1424).

    Created when a verified-email identity hits a tenant whose domain_join_policy
    is ``admin_approval``. Approval creates the membership; denial is terminal.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    identity_id: str
    email: str
    status: str = "pending"  # pending | approved | denied
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Migration `0018_join_requests.py`** (mirror `0007_memberships.py` shape)

```python
"""join_requests table — verified-domain self-service join (#1424)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0018_join_requests"
down_revision = "0017_org_settings"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("join_requests"):
        op.create_table(
            "join_requests",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("identity_id", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.Text(), nullable=True),
            sa.Column("decided_by", sa.Text(), nullable=True),
        )
        op.create_index("ix_join_requests_tenant", "join_requests", ["tenant_id"])
        # one non-terminal request per (tenant, identity)
        op.create_index(
            "uq_join_requests_pending",
            "join_requests",
            ["tenant_id", "identity_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    if _has_table("join_requests"):
        op.drop_table("join_requests")
```

- [ ] **Step 6: `_init_db` mirror + CRUD in `store.py`** — add the `CREATE TABLE IF NOT EXISTS join_requests (...)` + partial unique index in `_init_db`, and the four methods. `create_join_request` catches the unique violation and re-reads the existing pending row (mirror the `create_membership` UniqueViolation pattern at store.py ~847). `decide_join_request` sets `status`, `decided_at`, `decided_by`.

- [ ] **Step 7: Postgres CRUD test** (`tests/integration/test_join_requests_pg.py`, `@pytest.mark.postgres`): create → list pending → idempotent re-create returns same id → decide approved → no longer pending.

- [ ] **Step 8: Run + commit**

```bash
git add src/dazzle/http/runtime/auth/models.py src/dazzle/http/runtime/auth/store.py \
  src/dazzle/http/alembic/versions/0018_join_requests.py \
  tests/unit/test_join_request_store.py tests/integration/test_join_requests_pg.py
git commit -m "feat(auth): JoinRequest record + store CRUD (#1424 phase 1)"
```

### Task 1.6: Ship Phase 1

- [ ] **Step 1:** `ruff check src/ tests/ --fix && ruff format src/ tests/`
- [ ] **Step 2:** `pytest tests/ -m "not e2e"` (green) + `DATABASE_URL=… pytest -m postgres` (touches migrations).
- [ ] **Step 3:** `mypy src/dazzle` (clean).
- [ ] **Step 4:** CHANGELOG `### Added` entry: org settings column, JoinRequest table, uniform domain-admission gate (default-off). `/bump patch`. Commit + push. Hold the `.dazzle/improve.lock` across the push if coordinating with `/improve`.

---

## Phase 2 — Domain-type connection + verification reuse

Adds the provider-less `type="domain"` connection and ensures it (a) verifies domains via the existing DNS-TXT flow and (b) never enters an SSO provider path.

### Task 2.1: Exclude `type="domain"` from SSO domain routing

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py:1299` (`get_connection_by_verified_domain` — add an SSO-type filter param) OR add `get_sso_connection_by_verified_domain`.
- Modify: `src/dazzle/http/runtime/auth/enterprise_routes.py:56`, `saml_routes.py:60` to use the SSO-restricted lookup.
- Test: `tests/unit/test_domain_connection_routing.py`

**Interfaces:**
- Produces: `store.get_connection_by_verified_domain(domain, *, types: tuple[str, ...] | None = None)` — when `types` given, only matches connections whose `type` is in the set. SSO callers pass `types=("oidc","saml")`.

- [ ] **Step 1: Failing test** — a domain owned only by a `type="domain"` connection returns `None` for an SSO-typed lookup but the connection for an unfiltered lookup:

```python
def test_sso_lookup_skips_domain_type_connection(store_with_domain_conn):
    assert store_with_domain_conn.get_connection_by_verified_domain(
        "bigcorp.com", types=("oidc", "saml")
    ) is None
    assert store_with_domain_conn.get_connection_by_verified_domain("bigcorp.com") is not None
```

- [ ] **Step 2: Run to verify it fails** — `types` kwarg unknown.

- [ ] **Step 3: Implement** the `types` filter in `get_connection_by_verified_domain` (filter the scanned rows by `type` when `types` is not None). Update the two SSO call sites to pass `types=("oidc","saml")`.

- [ ] **Step 4: Run to verify it passes** — PASS; existing SSO routing tests green.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py src/dazzle/http/runtime/auth/enterprise_routes.py \
  src/dazzle/http/runtime/auth/saml_routes.py tests/unit/test_domain_connection_routing.py
git commit -m "fix(auth): SSO domain routing skips type=domain connections (#1424 phase 2)"
```

### Task 2.2: Guard `resolve_provider` against domain connections

**Files:**
- Modify: `src/dazzle/http/runtime/auth/connections.py:153` (`resolve_provider`) — keep fail-loud, but the docstring/error must name `type="domain"` as routing-only.
- Test: `tests/unit/test_resolve_provider_domain.py`

**Interfaces:**
- Produces: `resolve_provider` raises `ConnectionError` with a clear "domain connections have no IdP provider" message for `type="domain"`.

- [ ] **Step 1: Failing test**

```python
import pytest
from dazzle.http.runtime.auth.connections import ConnectionError, resolve_provider


def test_resolve_provider_rejects_domain_type(domain_connection):
    with pytest.raises(ConnectionError, match="domain"):
        resolve_provider(domain_connection)
```

- [ ] **Step 2: Run to verify it fails** — the generic "no provider registered" message may not match `domain`; assert the clearer message.

- [ ] **Step 3: Implement** — at the top of `resolve_provider`, special-case:

```python
    if connection.type == "domain":
        raise ConnectionError(
            "domain connections are routing-only and have no IdP provider"
        )
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/connections.py tests/unit/test_resolve_provider_domain.py
git commit -m "feat(auth): fail-loud resolve_provider for type=domain (#1424 phase 2)"
```

### Task 2.3: Verify domains on a domain-type connection (integration)

**Files:**
- Test: `tests/integration/test_domain_connection_verify_pg.py` (`@pytest.mark.postgres`)

**Interfaces:** Consumes `store.create_connection(type="domain", config={}, secrets={}, domains=[...], provider="native")`, `verify_domain` (with a fake `DnsTxtResolver`), `claim_verified_domain`.

- [ ] **Step 1: Failing test** — create a domain connection, publish the expected TXT via a fake resolver, `verify_domain` returns True, domain lands in `verified_domains`, and a second connection cannot claim the same domain (`already_verified_elsewhere`):

```python
import pytest
from dazzle.http.runtime.auth.domain_verification import txt_record, verify_domain


class _FakeResolver:
    def __init__(self, mapping): self._m = mapping
    def resolve_txt(self, domain): return self._m.get(domain, [])


@pytest.mark.postgres
def test_domain_connection_verifies(auth_store_pg):
    org = auth_store_pg.create_organization(slug="acme", name="Acme")
    conn = auth_store_pg.create_connection(
        tenant_id=org.id, type="domain", config={}, secrets={}, domains=["bigcorp.com"],
    )
    resolver = _FakeResolver({"bigcorp.com": [txt_record(conn.id, "bigcorp.com")]})
    assert verify_domain(auth_store_pg, conn, "bigcorp.com", resolver=resolver) is True
    refreshed = auth_store_pg.get_connection(conn.id)
    assert "bigcorp.com" in refreshed.verified_domains
```

- [ ] **Step 2: Run** (PASS expected immediately — this exercises existing machinery; the test is the regression guard that a provider-less connection works end-to-end). If it fails, the failure localizes a real reuse gap.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_domain_connection_verify_pg.py
git commit -m "test(auth): domain-type connection verifies via existing DNS-TXT flow (#1424 phase 2)"
```

### Task 2.4: Ship Phase 2 — gates + `/bump patch` + CHANGELOG (`### Added`: type=domain connection).

---

## Phase 3 — Self-service join flow

The pure policy mapper + integration at password login and the email-verification callback.

### Task 3.1: `decide_domain_join` (pure)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/domain_join.py` (add the mapper + outcome types)
- Test: `tests/unit/test_decide_domain_join.py`

**Interfaces:**
- Produces:
  - Outcome dataclasses: `Off()`, `AutoJoin()`, `NeedsApproval()`, `Noop()` (frozen).
  - `decide_domain_join(policy: str, *, email_verified: bool, has_membership: bool) -> Off | AutoJoin | NeedsApproval | Noop`
  - `resolve_domain_tenant(store, email: str) -> str | None` — the tenant owning the email's verified domain (reuses `get_connection_by_verified_domain(domain)` unfiltered, returns `connection.tenant_id`), or None.

- [ ] **Step 1: Failing test**

```python
from dazzle.http.runtime.auth.domain_join import (
    AutoJoin, NeedsApproval, Noop, Off, decide_domain_join,
)


def test_unverified_email_never_joins():
    assert isinstance(decide_domain_join("auto_join", email_verified=False, has_membership=False), Noop)


def test_existing_membership_is_noop():
    assert isinstance(decide_domain_join("auto_join", email_verified=True, has_membership=True), Noop)


def test_off_policy():
    assert isinstance(decide_domain_join("off", email_verified=True, has_membership=False), Off)


def test_auto_join():
    assert isinstance(decide_domain_join("auto_join", email_verified=True, has_membership=False), AutoJoin)


def test_admin_approval():
    assert isinstance(decide_domain_join("admin_approval", email_verified=True, has_membership=False), NeedsApproval)
```

- [ ] **Step 2: Run to verify it fails** — symbols missing.

- [ ] **Step 3: Implement** — add to `domain_join.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Off: ...
@dataclass(frozen=True)
class AutoJoin: ...
@dataclass(frozen=True)
class NeedsApproval: ...
@dataclass(frozen=True)
class Noop: ...

JoinOutcome = Off | AutoJoin | NeedsApproval | Noop


def decide_domain_join(policy: str, *, email_verified: bool, has_membership: bool) -> JoinOutcome:
    """Pure: what a verified-domain match should do. Fail-closed — an unverified
    email or an existing membership is always Noop (routing/membership handled
    elsewhere). Mirrors apex_discovery.resolve_apex_redirect's mapper style."""
    if has_membership or not email_verified:
        return Noop()
    if policy == "off":
        return Off()
    if policy == "auto_join":
        return AutoJoin()
    if policy == "admin_approval":
        return NeedsApproval()
    return Noop()


def resolve_domain_tenant(store: Any, email: str) -> str | None:
    domain = email_domain(email)
    if not domain:
        return None
    conn = store.get_connection_by_verified_domain(domain)
    return conn.tenant_id if conn is not None else None
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/domain_join.py tests/unit/test_decide_domain_join.py
git commit -m "feat(auth): decide_domain_join policy mapper (#1424 phase 3)"
```

### Task 3.2: Join orchestration helper

**Files:**
- Create: `src/dazzle/http/runtime/auth/join_requests.py`
- Test: `tests/unit/test_apply_domain_join.py`

**Interfaces:**
- Produces: `apply_domain_join(store, *, identity_id: str, email: str) -> ApplyResult` where `ApplyResult` carries `kind: Literal["joined","pending","none"]` and optional `membership_id`. It: resolves the tenant for the email; reads the tenant's policy; checks existing membership; calls `decide_domain_join`; for `AutoJoin` calls `assert_domain_admissible` then `create_membership` (default-deny roles `[]`, `reason="verified-domain self-service join"`); for `NeedsApproval` calls `create_join_request`. Returns `none` for `Off`/`Noop`/no-tenant.

- [ ] **Step 1: Failing test** (with a fake store) — auto_join creates a membership; admin_approval creates a join request; off/no-tenant returns none; restricted-but-off-domain auto_join raises `DomainNotAdmissibleError` (the gate still applies).

```python
from dazzle.http.runtime.auth.join_requests import apply_domain_join


def test_auto_join_creates_membership(auto_join_store):
    res = apply_domain_join(auto_join_store, identity_id="u1", email="a@bigcorp.com")
    assert res.kind == "joined" and res.membership_id


def test_admin_approval_creates_request(approval_store):
    res = apply_domain_join(approval_store, identity_id="u1", email="a@bigcorp.com")
    assert res.kind == "pending"


def test_no_tenant_is_none(empty_store):
    res = apply_domain_join(empty_store, identity_id="u1", email="a@unknown.com")
    assert res.kind == "none"
```

(Build the fake stores in the test: each implements `get_connection_by_verified_domain`, `get_connections_for_tenant`, `get_org_settings`, `get_memberships_for_identity`, `create_membership`, `create_join_request`. The fakes assume `email_verified=True` is passed by the caller — `apply_domain_join` takes the verified identity; it does not re-check verification itself beyond requiring the caller to only invoke it for verified emails. Add an explicit `email_verified: bool` param to be safe and assert Noop when False.)

- [ ] **Step 2: Run to verify it fails** — module missing.

- [ ] **Step 3: Implement** `join_requests.py` — `ApplyResult` dataclass + `apply_domain_join` calling the Task 3.1 mapper and the store. Take `email_verified: bool` param; pass it into `decide_domain_join`.

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/join_requests.py tests/unit/test_apply_domain_join.py
git commit -m "feat(auth): apply_domain_join orchestration (#1424 phase 3)"
```

### Task 3.3: Evaluate join at password login

**Files:**
- Modify: `src/dazzle/http/runtime/auth/password_login_routes.py:128-138`
- Test: `tests/unit/test_password_login_domain_join.py`

**Interfaces:** Consumes `apply_domain_join`. After `activate_session_for_login` resolves **no** membership (`membership_id is None`) and `user.email_verified` is True, call `apply_domain_join(auth_store, identity_id=str(user.id), email=normalized_email, email_verified=True)`. On `kind == "joined"`, re-run `activate_session_for_login` (or directly bind the new membership) so the session routes to the host. On `kind == "pending"`, redirect to the "request submitted" view (Task 3.5). Otherwise keep the existing `redirect_to`.

- [ ] **Step 1: Failing test** — a verified-email password login with no membership and an `auto_join` tenant ends with a membership bound + redirect to the host path (assert via a fake auth_store + request). A `admin_approval` tenant redirects to `/auth/join-requested`.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** the branch in `submit_login_password` after line 131 (`membership_id, redirect_to = _login_redirect_for_outcome(...)`):

```python
        if membership_id is None and getattr(user, "email_verified", False):
            from dazzle.http.runtime.auth.join_requests import apply_domain_join

            joined = apply_domain_join(
                auth_store, identity_id=str(user.id), email=normalized_email, email_verified=True,
            )
            if joined.kind == "joined":
                outcome = activate_session_for_login(auth_store, user, request)
                membership_id, redirect_to = _login_redirect_for_outcome(
                    outcome, safe_next, memberships_required=memberships_required(request)
                )
            elif joined.kind == "pending":
                redirect_to = "/auth/join-requested"
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/password_login_routes.py tests/unit/test_password_login_domain_join.py
git commit -m "feat(auth): evaluate domain join at password login (#1424 phase 3)"
```

### Task 3.4: Evaluate join at email-verification callback

**Files:**
- Modify: `src/dazzle/http/runtime/auth/email_verification_routes.py:105-119`
- Test: `tests/unit/test_email_verify_domain_join.py`

**Interfaces:** Consumes `apply_domain_join`. After the token validates and the email is marked verified (and the `emit_user_email_verified` event), call `apply_domain_join(auth_store, identity_id=str(user_id), email=user.email, email_verified=True)`. On `pending`, redirect to `/auth/join-requested`; on `joined`, the next authenticated request routes via apex discovery (no special handling needed beyond the existing redirect). This is the path that lets a fresh signup (created unverified) join once they verify.

- [ ] **Step 1: Failing test** — verifying the email of a user whose domain maps to an `admin_approval` tenant creates a `JoinRequest`; an `auto_join` tenant creates a membership.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** the call after line 108 (event emission), before the redirect (line 119). Guard with try/except logging so a join hiccup never breaks email verification itself (verification must still succeed).

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/email_verification_routes.py tests/unit/test_email_verify_domain_join.py
git commit -m "feat(auth): evaluate domain join after email verification (#1424 phase 3)"
```

### Task 3.5: "Request submitted" view + route

**Files:**
- Create: `src/dazzle/http/runtime/auth/join_request_routes.py` (the `GET /auth/join-requested` page)
- Modify: app router registration (where auth routers mount — find `create_password_login_routes` mount site in `app_factory`/routes wiring; mount the new router alongside it).
- Test: `tests/unit/test_join_request_view.py`

**Interfaces:** Produces a typed-Fragment `Page` rendered via the existing auth-view helpers (mirror `auth_views.build_login_password_view`'s construction). The page must NOT confirm tenant identity (enumeration invariant 4) — copy is generic: "Your request to join has been submitted and is awaiting approval."

- [ ] **Step 1: Failing test** — `GET /auth/join-requested` returns 200 and contains the generic message, no tenant name.
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** the view + route, mirroring an existing simple auth page. Register the router.
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/join_request_routes.py tests/unit/test_join_request_view.py <router-wiring-file>
git commit -m "feat(auth): join-requested confirmation page (#1424 phase 3)"
```

### Task 3.6: Ship Phase 3 — gates + `/bump patch` + CHANGELOG (`### Added`: self-service join at login + post-verification).

---

## Phase 4 — Tenant-admin UX

Extend the capability-gated admin surfaces. These tasks mirror existing view/route functions; write the Fragment code by reading the named view functions at implementation time (do not fabricate markup).

### Task 4.1: Join-policy + restrict toggle on `/auth/connections`

**Files:**
- Modify: `src/dazzle/http/runtime/auth/connection_admin_routes.py` (add `POST /auth/connections/policy` action, gated by the existing `_gate` → `manage_connections`)
- Modify: `src/dazzle/http/runtime/auth/connection_admin_views.py` (render the policy selector + restrict checkbox, sourced from `OrgSettings.from_dict(store.get_org_settings(org_id))`)
- Test: `tests/unit/test_connection_admin_policy.py`

**Interfaces:** The action reads form fields `domain_join_policy` (select: off/auto_join/admin_approval) + `restrict_membership_to_verified_domains` (checkbox), validates the policy against `OrgSettings`, and persists via `store.set_org_settings(org_id, OrgSettings(...).to_dict())`. The view renders current values; mirror the existing form construction in `connection_admin_views.build_connections_view`.

- [ ] **Step 1: Failing test** — posting the policy form updates org settings; a non-`manage_connections` caller gets the fail-closed response (mirror existing `_gate` tests).
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement** route + view (read `connection_admin_views.py` to match the Fragment idiom).
- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** `feat(auth): tenant join-policy admin controls (#1424 phase 4)`

### Task 4.2: "Verify a domain for self-service join" affordance

**Files:**
- Modify: `connection_admin_routes.py` (`create_connection_action` already accepts `type`; allow `type="domain"` → `store.create_connection(type="domain", config={}, secrets={}, domains=[])`; then the existing `add_domain`/`verify_domain_action` apply unchanged)
- Modify: `connection_admin_views.py` (add a "Verify a domain (no SSO)" entry to the create-connection affordance)
- Test: `tests/unit/test_create_domain_connection.py`

**Interfaces:** Reuses `create_connection`/`add_domain`/`verify_domain_action`. A domain connection has empty config/secrets.

- [ ] **Step 1: Failing test** — `create_connection_action` with `type=domain` creates a provider-less connection (no secret key required); the connections page lists it with its add/verify-domain controls.
- [ ] **Step 2–4:** implement + verify (mirror the existing create path; ensure the secret-key precondition is skipped for `type="domain"` since it has no secrets).
- [ ] **Step 5: Commit** `feat(auth): domain-only connection create affordance (#1424 phase 4)`

### Task 4.3: Join-requests approval queue (member-admin)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/member_admin_routes.py` (add `GET /auth/join-requests` queue + `POST /auth/join-requests/approve` + `/deny`, gated by `manage_members`)
- Modify: `src/dazzle/http/runtime/auth/member_admin_views.py` (render the pending list)
- Modify: `src/dazzle/http/runtime/auth/join_requests.py` (add `approve_join_request(store, request_id, *, decided_by)` → calls `assert_domain_admissible` then `create_membership` then `decide_join_request(status="approved")`; `deny_join_request(...)`)
- Test: `tests/unit/test_join_request_approval.py`

**Interfaces:** Approve creates the membership (default-deny roles) and marks the request approved; deny marks denied. Both gated by `manage_members`; both re-run `assert_domain_admissible` at decision time (the restriction may have changed).

- [ ] **Step 1: Failing test** — approve creates a membership + marks approved; deny marks denied without a membership; non-`manage_members` caller fail-closed.
- [ ] **Step 2–4:** implement + verify (mirror `member_admin_routes` mutation handlers at lines 119–193).
- [ ] **Step 5: Commit** `feat(auth): join-request approval queue (#1424 phase 4)`

### Task 4.4: Ship Phase 4 — gates + `/bump patch` + CHANGELOG (`### Added`: admin UX). Add an `### Agent Guidance` note: domain-join config lives on `/auth/connections` (manage_connections) + `/auth/join-requests` (manage_members).

---

## Phase 5 — Routing confirmation + negative security tests

No new behaviour — prove the invariants hold with live tests (these are the "detectors" from the spec's failure-mode note; they must be live, not documented).

### Task 5.1: Post-join routing + anti-enumeration tests

**Files:**
- Test: `tests/integration/test_domain_join_routing_pg.py` (`@pytest.mark.postgres`)

**Interfaces:** End-to-end against PG: (a) after `auto_join`, a second login routes to the tenant host (apex discovery resolves the new membership); (b) a zero-membership verified user under `admin_approval` is never routed to a tenant host (no 302 to `{slug}.{domain}`) before approval; (c) **enumeration:** an unverified or non-matching email yields the same apex/login response as a matching one (no tenant-existence signal).

- [ ] **Step 1: Write the tests** (full scenarios — create org + domain conn + verify + set policy + run login/verify + assert routing/response parity).
- [ ] **Step 2: Run** — they should pass given Phases 1–4; any failure localizes a real invariant break.
- [ ] **Step 3: Commit** `test(auth): post-join routing + anti-enumeration invariants (#1424 phase 5)`

### Task 5.2: Ship Phase 5 — gates + `/bump patch` + CHANGELOG (`### Added`: invariant tests).

---

## Phase 6 — Worked example + guides (Gap 2)

A kayfabe `examples/` app exercising the full loop, with per-persona guides and a CLI runbook. This satisfies #1424 Gap 2 and gives the feature e2e coverage.

### Task 6.1: Scaffold `examples/domain_join_co`

**Files:**
- Create: `examples/domain_join_co/*.dsl` (app with `tenant_host:` + `membership:`, a root entity, a couple of surfaces), `examples/domain_join_co/dazzle.toml`, `.env.example`.
- Modify: `.claude/CLAUDE.md` (examples list line) + `tests/unit/test_docs_drift.py` (examples assertion).
- Test: `dazzle validate` clean; `tests/unit/test_docs_drift.py` green.

**Interfaces:** Mirror `fixtures/tenant_hierarchy/` for the `tenant_host:`/`membership:` DSL shape. The app should set `restrict_membership_to_verified_domains` semantics in its kayfabe (documented in the runbook; the flag is set via the admin UX/CLI, not DSL).

- [ ] **Step 1:** author the DSL; `dazzle validate` (clean).
- [ ] **Step 2:** update the drift lists; `pytest tests/unit/test_docs_drift.py -v` (green).
- [ ] **Step 3: Commit** `feat(examples): domain_join_co worked example (#1424 phase 6 / Gap 2)`

### Task 6.2: Per-persona guides

**Files:**
- Create: guide blocks in the example DSL for two personas — a **tenant technical admin** (configures domains/policy, approves joins) and a **joining employee** (verifies email, joins). Read `docs/reference/guides.md` first (quality bar: coverage + terseness + in-fiction + concordance).
- Test: `tests/unit/test_example_guide_bar.py` (green for the new app); `dazzle ux verify --guides` (e2e oracle).

- [ ] **Step 1:** author guides per the bar; run `pytest tests/unit/test_example_guide_bar.py -v`.
- [ ] **Step 2:** regenerate any committed `expected/` references (guides introduce the framework `OnboardingState` entity into RBAC/compliance — per CLAUDE.md).
- [ ] **Step 3: Commit** `feat(examples): per-persona guides for domain_join_co (#1424 phase 6 / Gap 2)`

### Task 6.3: CLI runbook doc

**Files:**
- Create: `docs/reference/verified-domain-join.md` — the create-connection → `add-domain` → DNS-TXT `verify-domain` → set-policy → join → approve → tenant-host runbook, using `dazzle` CLI (`auth_connection.py` commands) + the admin UX.
- Modify: link it from `docs/reference/` index if one exists.

- [ ] **Step 1:** write the runbook with exact commands.
- [ ] **Step 2: Commit** `docs: verified-domain self-service join runbook (#1424 phase 6 / Gap 2)`

### Task 6.4: Ship Phase 6 + close-out

- [ ] **Step 1:** full gates incl. `dazzle ux verify --guides` and `DATABASE_URL=… pytest -m postgres`.
- [ ] **Step 2:** `/bump patch` + CHANGELOG (`### Added`: worked example + guides + runbook). Push.
- [ ] **Step 3:** comment on #1424 summarizing all phases; close the issue.

---

## Self-Review

**Spec coverage:**
- §2 decisions → Tasks 1.1/1.2 (settings, default admin_approval), 1.3/1.4 (gate-everything restriction), 2.1 (domain connection storage), 3.1 (policy model), 3.x (email_verified gate), 5.1 (routing-never-a-grant, no pre-membership routing). ✓
- §3.1 data model → 1.1, 1.5, 2.1. ✓
- §3.2 pure units → 1.3 (`assert_domain_admissible`, `tenant_verified_domains`, `email_domain`), 3.1 (`decide_domain_join`, `resolve_domain_tenant`). ✓
- §3.3 flow integration → 3.3 (login), 3.4 (email-verify callback), 1.4 (admission everywhere). ✓
- §3.4 admin UX → 4.1/4.2/4.3. ✓
- §4 security invariants → 1.4 (uniform admission), 3.1 (email_verified, never-grant), 5.1 (enumeration, post-join routing), 2.1 (one-owner preserved). ✓
- §5 worked example → Phase 6. ✓
- §6 phasing → Phases 1–6 match. ✓

**Placeholder scan:** Two deliberate `<...>` markers require an implementation-time lookup, each with explicit instructions: `0016_<CURRENT_HEAD>` (run `dazzle db heads`), `<provisioned_email_var>` (the email already in scope in `scim_provisioning`), `<router-wiring-file>` (the auth-router mount site). Phase 4/6 task code is intentionally spec'd as "mirror named function X" rather than fabricated Fragment/DSL markup — the exact view/DSL code must be written against the real files at implementation time. These are grounding instructions, not vague placeholders.

**Type consistency:** `assert_domain_admissible(store, tenant_id, email) -> None` (raises) is used consistently in 1.3/1.4/4.3. `decide_domain_join(policy, *, email_verified, has_membership)` consistent in 3.1/3.2. `apply_domain_join(store, *, identity_id, email, email_verified) -> ApplyResult(kind, membership_id)` consistent in 3.2/3.3/3.4. `OrgSettings` field names match 1.2 across 1.3/4.1. Store method names verified against `store.py` (`get_organization`, `get_connections_for_tenant`, `set_connection_domains`, `create_connection`, `create_membership`, `get_memberships_for_identity`, `get_connection_by_verified_domain`).

## Execution Handoff

This plan implements a large, security-sensitive feature deferred from #1424. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task + two-stage review; adversarial/independent review on the security tasks (1.4, 3.x, 5.1).
2. **Inline Execution** — execute in-session with checkpoints (CLAUDE.md hybrid default for Opus 4.8: inline for cross-task type coherence + independent review at the security checkpoints).
