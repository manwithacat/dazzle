# RLS Phase E.2 — QA-Auth + Ephemeral Provisioning + Containment Invariant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline execution with a MANDATORY independent adversarial-review checkpoint on the mint/containment path — this is a "mint a session" endpoint). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a CI/QA harness provision an ephemeral, isolated test tenant and mint a session into it over a signed channel that — by a DB-enforced containment invariant — can **never** mint into a real tenant. Closes #1339; completes RLS Phase E.

**Architecture:** Three pieces on the auth Plan 1a–1c membership model. (1) `provision_test_tenant(auth_store, run_id)` creates a framework `organizations` row `slug=qa-<run_id>, is_test=true` (the framework org IS the QA tenant — no domain tenant-root row, so no 1d coupling) + a first admin identity + its membership; teardown reuses E.1's `excise_tenant`. (2) A stdlib-`hmac` signer over `email:run_id:timestamp` with a ~60s replay window (no new dependency; `hmac` already in `auth/crypto.py`). (3) A **self-disabling** `qa_secure_routes.py` — not mounted unless `QA_AUTH_SECRET` is set — whose `/qa/secure/mint` verifies the signature, resolves the target user's org **from the DB** (`organizations` by `slug=qa-<run_id>`), and **refuses 403 unless that org is `is_test=true`, `qa-`-namespaced, and run-matched**, then mints a session scoped to that org's membership. The QA secret thus cannot reach a real org (the DB `is_test` gate is unforgeable from the request), and the bound `dazzle.tenant_id` makes cross-tenant access structurally impossible at the RLS layer (Phase B). Recorded as **ADR-0035**.

**Tech Stack:** Python 3.12, stdlib `hmac`/`hashlib`/`time` (constant-time compare), psycopg3 (auth store), FastAPI (the `/qa/` prefix is already CSRF-exempt — these requests carry their own HMAC credential, structurally CSRF-immune per ADR-0033 `NA_SIGNATURE`), pytest (adversarial security tests first-class + a real-PG provisioning test).

---

## Scope

**In scope (Phase E.2):**
- `provision_test_tenant(auth_store, run_id, *, roles=("admin",)) -> ProvisionedTestTenant` + `teardown_test_tenant(appspec, org_id, *, conn)` (wraps E.1 `excise_tenant`).
- `sign_qa_token(email, run_id, *, secret, now) -> str` + `verify_qa_token(token, *, secret, max_age_seconds=60, now) -> QaTokenClaims` (raises `QaTokenError` on bad sig / expiry / malformed).
- `qa_secure_routes.py`: `create_qa_secure_routes() -> APIRouter | None` (None when `QA_AUTH_SECRET` unset); `POST /qa/secure/mint` enforcing the containment invariant + minting a contained session cookie.
- Mount in `subsystems/auth.py` only when `QA_AUTH_SECRET` is set.
- **ADR-0035** — the containment invariant as a recorded security guarantee.
- Adversarial tests: cannot mint into a non-`is_test` org (403); replay outside the window (403); tampered/bad signature (403); run-id ↔ org-slug mismatch (403); self-disabled (router is None) without the secret; happy path mints a session scoped to the test org.

**Out of scope / deferred:**
- Schema-isolation (premium) parity for provisioning — shared-schema (framework-org-as-tenant) only, per spec (the case the QA harness exercises).
- The dev `qa_routes.py` magic-link path — untouched (the "dev route stays dev" promise; this is a physically separate secret-gated module).
- Auto-teardown scheduling / reaper loops — the harness calls `teardown_test_tenant` (E.1 excise) explicitly.
- Multi-admin / role-mapping beyond the seeded admin; the `run_id`↔domain-root 1:1 seed (Plan 1d — N/A for framework-org QA tenants).

## Design decisions

- **Containment is DB-resolved, not request-supplied (no confused-deputy).** The mint never trusts a tenant id from the request. It resolves `organizations` by `slug=qa-<run_id>` (run_id comes from the *signed* token) and checks `is_test=true` AND `slug` startswith `qa-` AND the user has a membership there. Any one failing → 403. `is_test` is a column (unforgeable), not a slug heuristic.
- **Self-disabling, not runtime-branched.** `create_qa_secure_routes()` returns `None` when `QA_AUTH_SECRET` is unset, and `subsystems/auth.py` skips the mount — prod-off-by-default with no request-time flag to misconfigure. (Defence-in-depth: the route also re-checks the secret at request time.)
- **Signed channel = `NA_SIGNATURE`.** The HMAC over `email:run_id:timestamp` is the credential; CSRF is categorically N/A (ADR-0033). Constant-time compare (`hmac.compare_digest`); ~60s window bounds replay; the secret is env-only, never logged.
- **Reuse, don't reinvent.** Provisioning uses 1c's `create_organization`/`create_user`/`create_membership`; teardown uses E.1's `excise_tenant`; the mint uses 1b's session-activation shape (`create_session(active_membership_id=…)` + cookie). The QA tenant is framework-org-as-tenant, so none of the 1d domain-root work is needed.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/auth/qa_provision.py` | `provision_test_tenant` + `teardown_test_tenant` + `ProvisionedTestTenant` | **Create** |
| `src/dazzle/http/runtime/auth/qa_sign.py` | `sign_qa_token` / `verify_qa_token` + `QaTokenClaims`/`QaTokenError` | **Create** |
| `src/dazzle/http/runtime/auth/store.py` | `get_organization(org_id)` (by id, for the mint) | **Modify** |
| `src/dazzle/http/runtime/qa_secure_routes.py` | self-disabling mint route + containment invariant | **Create** |
| `src/dazzle/http/runtime/subsystems/auth.py` | mount when `QA_AUTH_SECRET` set | **Modify** |
| `docs/adr/0035-qa-auth-containment-invariant.md` | the security ADR | **Create** |
| `docs/adr/INDEX.md` | ADR index entry | **Modify** |
| `tests/unit/test_qa_sign.py` | signer round-trip + tamper/expiry | **Create** |
| `tests/unit/test_qa_secure_routes_disabled.py` | self-disable (no secret → None) | **Create** |
| `tests/integration/test_qa_auth_containment_pg.py` | provision + mint happy path + adversarial 403s | **Create** |

---

## Task 1: `provision_test_tenant` + `teardown_test_tenant`

**Files:**
- Create: `src/dazzle/http/runtime/auth/qa_provision.py`
- Test: `tests/integration/test_qa_auth_containment_pg.py`

- [ ] **Step 1: Write the failing integration test (real PG)**

```python
# tests/integration/test_qa_auth_containment_pg.py
"""Real-PG proof of ephemeral QA-tenant provisioning + containment (Phase E.2, #1339)."""

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
    scratch = f"dazzle_qaauth_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
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


def test_provision_test_tenant_creates_qa_org_admin_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="run123", roles=["admin"])

    assert prov.org.slug == "qa-run123"
    assert prov.org.is_test is True
    # The admin has exactly one membership, in the test org, with the given roles.
    mships = store.get_memberships_for_identity(str(prov.admin.id))
    assert len(mships) == 1
    assert mships[0].tenant_id == prov.org.id
    assert mships[0].roles == ["admin"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_qa_auth_containment_pg.py -k provision -q`
Expected: FAIL — `ModuleNotFoundError: ...qa_provision`.

- [ ] **Step 3: Write the module**

```python
# src/dazzle/http/runtime/auth/qa_provision.py
"""Ephemeral QA test-tenant provisioning + teardown (RLS Phase E.2, #1339).

A QA test tenant is a framework ``organizations`` row (``slug=qa-<run_id>``,
``is_test=true``) plus a seeded admin identity + membership — the framework org
IS the tenant (no domain tenant-root row, so no Plan-1d coupling). Teardown
reuses the E.1 excision primitive.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

QA_SLUG_PREFIX = "qa-"


@dataclass
class ProvisionedTestTenant:
    org: Any  # OrganizationRecord
    admin: Any  # UserRecord


def provision_test_tenant(
    auth_store: Any,
    run_id: str,
    *,
    roles: list[str] | tuple[str, ...] = ("admin",),
    admin_email: str | None = None,
) -> ProvisionedTestTenant:
    """Provision an ephemeral, reserved-namespace, is_test org + admin (Phase E.2).

    ``slug = qa-<run_id>`` (the reserved namespace, unforgeable + queryable
    ``is_test`` — the containment invariant keys off both). The admin gets a
    random password (login is via the signed QA mint, not credentials) and a
    membership in the org carrying ``roles``.
    """
    org = auth_store.create_organization(
        slug=f"{QA_SLUG_PREFIX}{run_id}", name=f"QA {run_id}", is_test=True
    )
    email = admin_email or f"qa-admin-{run_id}@qa.test"
    admin = auth_store.create_user(
        email=email, password=secrets.token_urlsafe(32), roles=list(roles)
    )
    auth_store.create_membership(
        tenant_id=org.id, identity_id=str(admin.id), roles=list(roles)
    )
    return ProvisionedTestTenant(org=org, admin=admin)


def teardown_test_tenant(appspec: Any, org_id: str, *, conn: Any) -> Any:
    """Excise a provisioned QA tenant (delegates to the E.1 engine)."""
    from dazzle.db.excision import excise_tenant

    return excise_tenant(appspec, org_id, conn=conn)
```

> `create_organization` (1c) accepts an arbitrary slug + `is_test`; the reserved-namespace validator (`tenant/config.py`) guards the schema-isolation `public.tenants` registry, not the framework `organizations` table, so `qa-<run_id>` is created directly here.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_qa_auth_containment_pg.py -k provision -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/qa_provision.py tests/integration/test_qa_auth_containment_pg.py
git commit -m "feat(auth): provision_test_tenant + teardown (Phase E.2)"
```

---

## Task 2: HMAC QA token signer

**Files:**
- Create: `src/dazzle/http/runtime/auth/qa_sign.py`
- Test: `tests/unit/test_qa_sign.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_qa_sign.py
"""HMAC QA token signer (RLS Phase E.2)."""

import pytest

from dazzle.http.runtime.auth.qa_sign import (
    QaTokenError,
    sign_qa_token,
    verify_qa_token,
)

_SECRET = "test-secret"


def test_round_trip() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    claims = verify_qa_token(tok, secret=_SECRET, now=1010.0)
    assert claims.email == "a@qa.test"
    assert claims.run_id == "run1"


def test_expired_token_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    with pytest.raises(QaTokenError, match="expired"):
        verify_qa_token(tok, secret=_SECRET, now=1000.0 + 61)


def test_future_token_rejected() -> None:
    # Clock skew the other way: a token from the future beyond the window.
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=2000.0)
    with pytest.raises(QaTokenError):
        verify_qa_token(tok, secret=_SECRET, now=2000.0 - 61)


def test_tampered_signature_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    body, _, _sig = tok.rpartition(".")
    forged = body + ".deadbeef"
    with pytest.raises(QaTokenError, match="signature"):
        verify_qa_token(forged, secret=_SECRET, now=1010.0)


def test_wrong_secret_rejected() -> None:
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    with pytest.raises(QaTokenError, match="signature"):
        verify_qa_token(tok, secret="other-secret", now=1010.0)


def test_tampered_payload_rejected() -> None:
    # Swapping the email after signing must fail the signature.
    tok = sign_qa_token("a@qa.test", "run1", secret=_SECRET, now=1000.0)
    _body, _, sig = tok.rpartition(".")
    forged = f"evil@qa.test:run1:1000." + sig
    with pytest.raises(QaTokenError):
        verify_qa_token(forged, secret=_SECRET, now=1010.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qa_sign.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the signer**

```python
# src/dazzle/http/runtime/auth/qa_sign.py
"""Signed QA-auth tokens (RLS Phase E.2, #1339).

A token is ``<email>:<run_id>:<issued_ts>.<hmac_hex>`` — an HMAC-SHA256 over the
payload keyed by ``QA_AUTH_SECRET``. The signature IS the credential (ADR-0033
NA_SIGNATURE); the ~60s window bounds replay. Constant-time verify; no logging
of the secret or token.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

DEFAULT_MAX_AGE_SECONDS = 60


class QaTokenError(ValueError):
    """A QA token failed verification (bad signature, expiry, or shape)."""


@dataclass(frozen=True)
class QaTokenClaims:
    email: str
    run_id: str
    issued_at: float


def _payload(email: str, run_id: str, issued_ts: float) -> str:
    # `:` separates fields; email/run_id are caller-controlled but the signature
    # binds the exact string, so re-parsing the signed payload is safe.
    return f"{email}:{run_id}:{issued_ts}"


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_qa_token(email: str, run_id: str, *, secret: str, now: float) -> str:
    """Sign ``email:run_id:now`` → ``payload.signature``. ``now`` is the issue
    time (``time.time()`` at the caller; passed in for deterministic tests)."""
    payload = _payload(email, run_id, now)
    return f"{payload}.{_sign(payload, secret)}"


def verify_qa_token(
    token: str, *, secret: str, now: float, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
) -> QaTokenClaims:
    """Verify signature + replay window; return claims or raise ``QaTokenError``."""
    payload, sep, sig = token.rpartition(".")
    if not sep:
        raise QaTokenError("malformed token (no signature)")
    expected = _sign(payload, secret)
    if not hmac.compare_digest(sig, expected):
        raise QaTokenError("bad signature")
    parts = payload.split(":")
    if len(parts) != 3:
        raise QaTokenError("malformed payload")
    email, run_id, issued_raw = parts
    try:
        issued_at = float(issued_raw)
    except ValueError as exc:
        raise QaTokenError("malformed timestamp") from exc
    # Reject both stale (replay) and far-future (clock-skew/forgery) tokens.
    if abs(now - issued_at) > max_age_seconds:
        raise QaTokenError("token expired or outside the replay window")
    return QaTokenClaims(email=email, run_id=run_id, issued_at=issued_at)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_qa_sign.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/qa_sign.py tests/unit/test_qa_sign.py
git commit -m "feat(auth): HMAC QA token signer (~60s window, constant-time) (Phase E.2)"
```

---

## Task 3: `get_organization(org_id)` store accessor

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py`
- Test: `tests/integration/test_qa_auth_containment_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_qa_auth_containment_pg.py
def test_get_organization_by_id(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    org = store.create_organization(slug="acme", name="Acme")
    got = store.get_organization(org.id)
    assert got is not None and got.slug == "acme"
    assert store.get_organization("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_qa_auth_containment_pg.py -k get_organization_by_id -q`
Expected: FAIL — no `get_organization`.

- [ ] **Step 3: Add the method**

In `src/dazzle/http/runtime/auth/store.py`, next to `get_organization_by_slug`:

```python
    def get_organization(self, org_id: str) -> "OrganizationRecord | None":
        row = self._execute_one("SELECT * FROM organizations WHERE id = %s", (org_id,))
        return self._row_to_organization(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_qa_auth_containment_pg.py -k get_organization_by_id -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_qa_auth_containment_pg.py
git commit -m "feat(auth): AuthStore.get_organization by id (Phase E.2)"
```

---

## Task 4: `qa_secure_routes.py` — self-disabling mint + containment invariant

**Files:**
- Create: `src/dazzle/http/runtime/qa_secure_routes.py`
- Test: `tests/unit/test_qa_secure_routes_disabled.py` + `tests/integration/test_qa_auth_containment_pg.py` (append)

- [ ] **Step 1: Write the failing self-disable unit test**

```python
# tests/unit/test_qa_secure_routes_disabled.py
"""qa_secure_routes is self-disabling without QA_AUTH_SECRET (Phase E.2)."""

from dazzle.http.runtime.qa_secure_routes import create_qa_secure_routes


def test_router_is_none_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("QA_AUTH_SECRET", raising=False)
    assert create_qa_secure_routes() is None


def test_router_built_with_secret(monkeypatch) -> None:
    monkeypatch.setenv("QA_AUTH_SECRET", "s3cr3t")
    router = create_qa_secure_routes()
    assert router is not None
    assert any(r.path == "/qa/secure/mint" for r in router.routes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_qa_secure_routes_disabled.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the route**

```python
# src/dazzle/http/runtime/qa_secure_routes.py
"""Secret-gated, contained QA-auth mint (RLS Phase E.2, #1339).

Physically separate from the dev-only `qa_routes.py` (the "dev route stays dev"
promise). **Self-disabling:** `create_qa_secure_routes()` returns None when
`QA_AUTH_SECRET` is unset, so it is never mounted in prod-by-default. The mint
enforces the DB containment invariant (ADR-0035): a session may be minted only
into a `qa-`-namespaced, `is_test=true`, run-matched org the target user belongs
to — the QA secret can NEVER reach a real tenant.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from dazzle.http.runtime.auth.crypto import cookie_secure
from dazzle.http.runtime.auth.qa_provision import QA_SLUG_PREFIX
from dazzle.http.runtime.auth.qa_sign import QaTokenError, verify_qa_token

logger = logging.getLogger(__name__)


class MintRequest(BaseModel):
    token: str


def create_qa_secure_routes() -> APIRouter | None:
    """Build the secret-gated mint router, or None when QA_AUTH_SECRET is unset."""
    secret = os.environ.get("QA_AUTH_SECRET")
    if not secret:
        return None

    router = APIRouter(tags=["qa"])

    @router.post("/qa/secure/mint")
    async def mint(body: MintRequest, request: Request, response: Response) -> dict:
        # Defence-in-depth: re-check the secret at request time (config drift).
        live_secret = os.environ.get("QA_AUTH_SECRET")
        if not live_secret:
            raise HTTPException(status_code=404)
        try:
            claims = verify_qa_token(body.token, secret=live_secret, now=time.time())
        except QaTokenError as exc:
            # Don't echo the reason to the client (no oracle); log server-side.
            logger.warning("[QA-AUTH] token verification failed: %s", exc)
            raise HTTPException(status_code=403, detail="invalid token") from exc

        auth_store = request.app.state.auth_store

        # ── Containment invariant (ADR-0035), resolved from the DB ──────────
        # The target org is derived from the SIGNED run_id, never a
        # request-supplied tenant id. It must be reserved-namespaced AND
        # is_test — both unforgeable from the request.
        org = auth_store.get_organization_by_slug(f"{QA_SLUG_PREFIX}{claims.run_id}")
        if (
            org is None
            or not org.is_test
            or not org.slug.startswith(QA_SLUG_PREFIX)
        ):
            logger.warning(
                "[QA-AUTH] refused mint: org for run_id=%r not a reserved is_test tenant",
                claims.run_id,
            )
            raise HTTPException(status_code=403, detail="not a test tenant")

        user = auth_store.get_user_by_email(claims.email.strip().lower())
        if user is None:
            raise HTTPException(status_code=403, detail="unknown user")
        membership = next(
            (
                m
                for m in auth_store.get_memberships_for_identity(str(user.id))
                if m.tenant_id == org.id and m.status == "active"
            ),
            None,
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="no membership in test tenant")

        # Mint a session scoped to the test org's membership (binds dazzle.tenant_id).
        session = auth_store.create_session(user, active_membership_id=membership.id)
        response.set_cookie(
            key="dazzle_session",
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
        )
        response.set_cookie(
            key="dazzle_csrf",
            value=session.csrf_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
        )
        logger.warning("[QA-AUTH] minted contained session for run_id=%r", claims.run_id)
        return {"ok": True, "tenant_id": org.id}

    return router
```

> The mint sets `dazzle_session` directly (the QA harness uses a fresh client). Using the fixed cookie name is fine for the QA tier; if a `tenant_host` deployment needs the `__Host-` name, switch to `select_write_name(request, ...)` — out of scope for E.2. The CSRF disposition for `/qa/` is already `NA_PREAUTH`/exempt and the request carries the HMAC credential, so no token dance.

- [ ] **Step 4: Run the self-disable test**

Run: `pytest tests/unit/test_qa_secure_routes_disabled.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Write the integration happy-path + adversarial tests (append)**

```python
# append to tests/integration/test_qa_auth_containment_pg.py
import time as _time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.qa_sign import sign_qa_token

_SECRET = "qa-int-secret"


def _app(store, monkeypatch_env: bool = True):
    import os

    os.environ["QA_AUTH_SECRET"] = _SECRET
    from dazzle.http.runtime.qa_secure_routes import create_qa_secure_routes

    app = FastAPI()
    app.state.auth_store = store
    router = create_qa_secure_routes()
    assert router is not None
    app.include_router(router)
    return TestClient(app, follow_redirects=False)


def test_mint_happy_path_scopes_session_to_test_org(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rh", roles=["admin"])
    token = sign_qa_token(prov.admin.email, "rh", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == prov.org.id
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == prov.org.id


def test_mint_refuses_real_non_test_org(scratch_url: str) -> None:
    """The containment crux: even a validly-signed token cannot mint into a
    real (non-test) org — the DB is_test gate refuses."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    # A REAL org named to collide with the qa- namespace check shape but is_test=false.
    real = store.create_organization(slug="qa-realish", name="Real", is_test=False)
    user = store.create_user(email="victim@real.test", password="pw123456", roles=["admin"])
    store.create_membership(tenant_id=real.id, identity_id=str(user.id), roles=["admin"])
    token = sign_qa_token("victim@real.test", "realish", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_expired_token(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rx")
    token = sign_qa_token(prov.admin.email, "rx", secret=_SECRET, now=_time.time() - 120)

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_bad_signature(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rz")
    token = sign_qa_token(prov.admin.email, "rz", secret="WRONG", now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403


def test_mint_rejects_run_mismatch(scratch_url: str) -> None:
    """A token whose run_id doesn't resolve to a provisioned qa- org → 403."""
    from dazzle.http.runtime.auth.qa_provision import provision_test_tenant
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    prov = provision_test_tenant(store, run_id="rm")
    # Sign for a different run_id (no qa-other org exists).
    token = sign_qa_token(prov.admin.email, "other", secret=_SECRET, now=_time.time())

    resp = _app(store).post("/qa/secure/mint", json={"token": token})
    assert resp.status_code == 403
```

- [ ] **Step 6: Run all the new integration tests**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_qa_auth_containment_pg.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/qa_secure_routes.py tests/unit/test_qa_secure_routes_disabled.py tests/integration/test_qa_auth_containment_pg.py
git commit -m "feat(auth): qa_secure_routes — contained QA-auth mint + DB containment invariant (Phase E.2)"
```

---

## Task 5: Mount the secure router when `QA_AUTH_SECRET` is set

**Files:**
- Modify: `src/dazzle/http/runtime/subsystems/auth.py`
- Test: covered by the self-disable unit test + boot smoke; here a wiring import check.

- [ ] **Step 1: Mount it (near the dev qa_routes / password-login mounts)**

In `src/dazzle/http/runtime/subsystems/auth.py`, add (after the org-context router mount from 1b, or near where `qa_routes` is mounted):

```python
        # Phase E.2 — secret-gated contained QA-auth mint. Self-disabling: the
        # factory returns None unless QA_AUTH_SECRET is set, so prod is off by
        # default with no request-time flag to misconfigure.
        from dazzle.http.runtime.qa_secure_routes import create_qa_secure_routes

        _qa_secure = create_qa_secure_routes()
        if _qa_secure is not None:
            ctx.app.include_router(_qa_secure)
            logger.warning(
                "[QA-AUTH] secret-gated QA mint mounted at /qa/secure/mint "
                "(QA_AUTH_SECRET set) — ensure this deployment is a test instance"
            )
```

> Confirm `logger` exists in `subsystems/auth.py` (grep `logger = `); if not, use the module logger pattern the file already uses, or `logging.getLogger(__name__)`.

- [ ] **Step 2: Import smoke**

Run: `python -c "import dazzle.http.runtime.subsystems.auth; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/http/runtime/subsystems/auth.py
git commit -m "feat(auth): mount secret-gated QA mint when QA_AUTH_SECRET set (Phase E.2)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 5) — MANDATORY (mint-a-session endpoint)
> Dispatch an **independent reviewer subagent** (or `/code-review`) over the whole E.2 surface (Tasks 1–5). Brief it to attack: (1) **the containment crux** — can a validly-signed token EVER mint a session into a non-`is_test` / non-`qa-` / cross-run org? Trace every branch; try a real user whose email collides, a `qa-`-slugged but `is_test=false` org, a run_id pointing at a real org. (2) **confused-deputy** — is the org EVER resolved from request-supplied data instead of the signed `run_id`? (3) **signature/replay** — constant-time compare? window bounds both stale and future tokens? any token/secret leakage in logs or error bodies (oracle)? (4) **self-disable** — is the router truly absent without the secret (not just a runtime 404 with a live handler)? config-drift between mount-time and request-time? (5) **session-fixation / cookie** — does the minted session correctly bind `active_membership` so RLS fences it, and is an un-contained session impossible? (6) **secret hygiene** — env-only, never logged, never returned. Apply receiving-code-review rigor; proceed to the ADR only when containment is airtight.

---

## Task 6: ADR-0035 + index

**Files:**
- Create: `docs/adr/0035-qa-auth-containment-invariant.md`
- Modify: `docs/adr/INDEX.md`

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0035-qa-auth-containment-invariant.md` documenting: context (CI/QA needs to authenticate into ephemeral tenants without real credentials, but a QA-auth channel must never reach a real tenant); decision (the DB-resolved containment invariant — mint refuses unless the run-resolved org is `is_test` + `qa-`-namespaced + the user has an active membership there; resolution from the DB record, not request input; `is_test` is a column not a heuristic; self-disabling without `QA_AUTH_SECRET`; HMAC-signed channel = `NA_SIGNATURE` per ADR-0033; defence-in-depth = namespace ∧ is_test ∧ run-match ∧ membership, any one failing refuses); consequences (the QA secret cannot mint into a real org even with a known real email; RLS structurally fences the minted session via `active_membership.tenant_id`); alternatives rejected (request-supplied tenant id → confused-deputy; slug-prefix-only heuristic → forgeable; `itsdangerous` → dependency hygiene, stdlib `hmac` suffices). Mark **Accepted (implemented, #1339)**.

- [ ] **Step 2: Add the INDEX entry**

Append to `docs/adr/INDEX.md` (mirror the existing one-line-per-ADR format):

```markdown
- [0035](0035-qa-auth-containment-invariant.md) — *Accepted (implemented, #1339).* **QA-auth containment invariant.** A secret-gated (`QA_AUTH_SECRET`, self-disabling), HMAC-signed (`NA_SIGNATURE`, ~60s window) mint may scope a session ONLY into a `qa-`-namespaced, `is_test=true`, run-matched `organizations` row the target user has an active membership in — **resolved from the DB, never request-supplied** (no confused-deputy). `is_test` is a column, not a slug heuristic (unforgeable). Defence in depth: namespace ∧ is_test ∧ run-match ∧ membership; any one failing → 403. The QA secret can never reach a real tenant; the minted session's `active_membership.tenant_id` makes cross-tenant access structurally impossible at the RLS layer (Phase B). Engine on the auth Plan 1a–1c membership model; teardown via the E.1 excise primitive. Closes #1339 / completes RLS Phase E.
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0035-qa-auth-containment-invariant.md docs/adr/INDEX.md
git commit -m "docs(adr): ADR-0035 QA-auth containment invariant (Phase E.2)"
```

---

## Final verification (before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean (CI scope)
- [ ] `pytest tests/ -m "not e2e"` — green (new unit tests; confirm no auth-subsystem regression — the secure router is unmounted without the secret, so existing apps are unaffected; confirm `test_docs_drift` is happy with the new ADR)
- [ ] With `TEST_DATABASE_URL="postgresql://localhost:5432/postgres"`: `pytest tests/integration/test_qa_auth_containment_pg.py -q` — green (provision + mint happy path + 4 adversarial 403s)
- [ ] `/bump patch` + CHANGELOG entry under **Added** (QA-auth + containment) with an **Agent Guidance** note:
  - "Phase E.2 (#1339) adds secret-gated contained QA-auth. `provision_test_tenant(store, run_id)` makes a `qa-<run_id>` `is_test` org + admin + membership; `POST /qa/secure/mint` (mounted only when `QA_AUTH_SECRET` set) mints a session into it over an HMAC-signed (~60s) token. The **DB containment invariant** (ADR-0035) refuses any mint into a non-`is_test` / non-`qa-` / cross-run org — resolved from the DB, not request input — so the QA secret can never reach a real tenant. Teardown = E.1 `excise_tenant`. Closes #1339; **RLS Phase E complete**."

---

## Self-review notes

- **Spec coverage (lifecycle §3 Slice 2 + §5 containment + §6 adversarial):** route module physically separate + self-disabling → Task 4/5; stdlib hmac ~60s → Task 2; `provision_test_tenant` (qa-namespace, is_test, seeded admin, shared-schema/framework-org) → Task 1; the containment invariant (DB-resolved, is_test ∧ namespace ∧ run-match) → Task 4 + ADR-0035 (Task 6); adversarial tests first-class → Task 4 (4 × 403 paths) + the mandatory review checkpoint. Teardown via E.1 excise → Task 1 `teardown_test_tenant`. Schema-isolation parity explicitly deferred (spec says shared-schema first).
- **Placeholder scan:** signer, provisioning, route, mount all carry concrete code. The ADR body (Task 6 Step 1) is described as prose-to-write (a doc, not code) with every required section enumerated — not a code placeholder. Flagged confirmations (`logger` presence in `subsystems/auth.py`; the exact mount neighbour) have explicit "grep + mirror" instructions.
- **Type consistency:** `QaTokenClaims(email, run_id, issued_at)` + `sign_qa_token(email, run_id, *, secret, now)` / `verify_qa_token(token, *, secret, now, max_age_seconds)` are used identically in the signer (Task 2), the route (Task 4), and the tests. `provision_test_tenant(auth_store, run_id, *, roles, admin_email) -> ProvisionedTestTenant(org, admin)` matches Task 1 def + Task 4 tests. `QA_SLUG_PREFIX` is the single source of the `qa-` literal (Task 1) reused by the route (Task 4). `get_organization(org_id)` (Task 3) is available to the route though it resolves by slug (the by-id accessor is added for completeness + the ADR's "resolve from DB" story; the route uses `get_organization_by_slug`).
