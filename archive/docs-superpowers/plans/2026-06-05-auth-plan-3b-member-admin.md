# Auth Plan 3b — Member-Admin Surface

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an org admin a page to manage their organization's members — see the roster + pending invitations, invite, change a member's roles, and suspend / reactivate / remove — with every mutation gated on `org_admin_roles`, scoped to the admin's **active** org (no cross-org management), and guarded against orphaning the org (can't drop the last admin).

**Architecture:** A `GET /auth/members` page (typed Fragment) renders the active org's roster (`get_memberships_for_tenant`) + pending invites (`list_pending_invitations`) + an invite form (posts to the 3a `POST /auth/invite`). Four fixed-path mutation routes (`POST /auth/members/{roles,suspend,reactivate,remove}`, membership_id in the query) wrap the Plan 2a store mutations. Each mutation runs the same gate: caller is an active admin of their active org (`may_manage_members` on `effective_roles_of`), the **target** membership belongs to that same org (cross-org guard), and the change won't leave the org with zero active admins (last-admin guard). Same-origin POSTs are admitted by the CSRF origin gate; mutations return `HX-Redirect` (htmx) / 303 back to the page.

**Tech Stack:** Python 3.12, FastAPI (`APIRouter`), psycopg3 (`AuthStore`), typed Fragment UI substrate (`Page`/`Stack`/`Card`/`Table`/`Button`/`FormStack`), pytest (`e2e`+`postgres`). Reuses Plan 2a mutations, 2b `get_memberships_for_tenant`, 3a invitations + `may_manage_members` + `org_admin_roles`.

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §7 (Tier 1 multi-org). Slice **3b** of Plan 3 (3a invitations shipped v0.81.41). The in-app org switcher (shell chrome) + runtime org creation are **out of scope** (later slices).

**Decisions (confirmed):** member-admin surface only; include the last-admin orphan guard.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/auth/member_admin.py` (**create**) | Pure authz/guard helpers: `active_admins(roster, org_admin_roles)`, `would_orphan_org(roster, target_id, *, new_roles, org_admin_roles)`. Unit-testable without a DB. |
| `src/dazzle/http/runtime/auth/member_admin_views.py` (**create**) | `build_members_view(...)` — the roster page (members + per-member action controls + pending invites + invite form). |
| `src/dazzle/http/runtime/auth/member_admin_routes.py` (**create**) | `create_member_admin_routes()`: `GET /auth/members` + `POST /auth/members/roles|suspend|reactivate|remove`. The shared gate (admin + cross-org + last-admin) lives here. |
| `src/dazzle/http/runtime/auth/store.py` | (no change — uses existing 2a/2b mutations + `get_user_by_id`.) |
| `src/dazzle/http/runtime/subsystems/auth.py` (**modify**) | Mount `create_member_admin_routes()`. |
| `src/dazzle/http/runtime/csrf.py` (**modify**) | `protected_paths += /auth/members/roles, /auth/members/suspend, /auth/members/reactivate, /auth/members/remove`. |
| `tests/unit/test_member_admin.py` (**create**) | `active_admins` + `would_orphan_org` (removal, suspension, demotion, non-admin target). |
| `tests/integration/test_member_admin_pg.py` (**create**) | Real-PG route tests: roster page renders; each mutation works; non-admin 403; cross-org target 403/404; last-admin block on remove/suspend/demote. |

---

## Task 1: Last-admin guard logic (`member_admin.py`)

**Files:**
- Create: `src/dazzle/http/runtime/auth/member_admin.py`
- Test: `tests/unit/test_member_admin.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_member_admin.py
"""Last-admin orphan guard + admin-count helpers (auth Plan 3b)."""

from dazzle.http.runtime.auth.member_admin import active_admins, would_orphan_org

# roster rows: (membership_id, roles, status)
_ADMIN_ROLES = ["owner", "admin"]


def test_active_admins_counts_only_active_members_with_an_admin_role() -> None:
    roster = [
        ("m1", ["owner"], "active"),
        ("m2", ["member"], "active"),
        ("m3", ["admin"], "suspended"),  # suspended → not an active admin
    ]
    assert active_admins(roster, _ADMIN_ROLES) == ["m1"]


def test_removing_the_last_admin_would_orphan() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    # new_roles=None models removal/suspension of the target.
    assert would_orphan_org(roster, "m1", new_roles=None, org_admin_roles=_ADMIN_ROLES) is True


def test_removing_a_non_last_admin_is_fine() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["admin"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=None, org_admin_roles=_ADMIN_ROLES) is False


def test_removing_a_non_admin_never_orphans() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    assert would_orphan_org(roster, "m2", new_roles=None, org_admin_roles=_ADMIN_ROLES) is False


def test_demoting_the_last_admin_would_orphan() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["member"], "active")]
    # role-change m1 owner→member leaves zero admins.
    assert (
        would_orphan_org(roster, "m1", new_roles=["member"], org_admin_roles=_ADMIN_ROLES) is True
    )


def test_demotion_that_keeps_another_admin_is_fine() -> None:
    roster = [("m1", ["owner"], "active"), ("m2", ["admin"], "active")]
    assert (
        would_orphan_org(roster, "m1", new_roles=["member"], org_admin_roles=_ADMIN_ROLES) is False
    )


def test_no_guard_when_org_already_has_no_admins() -> None:
    # If there are already zero admins, a change can't "orphan" further.
    roster = [("m1", ["member"], "active")]
    assert would_orphan_org(roster, "m1", new_roles=None, org_admin_roles=_ADMIN_ROLES) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_member_admin.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.http.runtime.auth.member_admin'`

- [ ] **Step 3: Create the module**

```python
# src/dazzle/http/runtime/auth/member_admin.py
"""Member-admin authorization + orphan-guard helpers (auth Plan 3b).

Pure functions over a roster (a list of ``(membership_id, roles, status)``
tuples) so the last-admin guard is unit-testable without a DB. An org must never
be left with zero active members holding an ``org_admin_role`` — otherwise nobody
could manage it.
"""

from __future__ import annotations


def active_admins(
    roster: list[tuple[str, list[str], str]], org_admin_roles: list[str]
) -> list[str]:
    """Membership ids that are ACTIVE and hold at least one admin role."""
    admin_set = set(org_admin_roles)
    return [
        mid
        for (mid, roles, status) in roster
        if status == "active" and admin_set & set(roles)
    ]


def would_orphan_org(
    roster: list[tuple[str, list[str], str]],
    target_id: str,
    *,
    new_roles: list[str] | None,
    org_admin_roles: list[str],
) -> bool:
    """True iff applying the change to ``target_id`` leaves the org with no admin.

    ``new_roles=None`` models removal or suspension (the target stops being an
    active admin). ``new_roles=[...]`` models a role change. Only blocks when the
    org currently HAS at least one admin and the change drops it to zero — an
    already-admin-less org can't be orphaned further.
    """
    before = active_admins(roster, org_admin_roles)
    if not before:
        return False  # nothing to orphan
    admin_set = set(org_admin_roles)
    after: list[str] = []
    for mid, roles, status in roster:
        if mid == target_id:
            if new_roles is None:
                continue  # removed / suspended → no longer an active admin
            if status == "active" and admin_set & set(new_roles):
                after.append(mid)
        elif status == "active" and admin_set & set(roles):
            after.append(mid)
    return len(after) == 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_member_admin.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/member_admin.py tests/unit/test_member_admin.py --fix
ruff format src/dazzle/http/runtime/auth/member_admin.py tests/unit/test_member_admin.py
git add src/dazzle/http/runtime/auth/member_admin.py tests/unit/test_member_admin.py
git commit -m "feat(auth): member-admin last-admin orphan guard helpers (Plan 3b)"
```

---

## Task 2: Member-admin routes (the security core)

**Files:**
- Create: `src/dazzle/http/runtime/auth/member_admin_routes.py`
- Create: `src/dazzle/http/runtime/auth/member_admin_views.py`
- Modify: `src/dazzle/http/runtime/csrf.py` (protected_paths)
- Modify: `src/dazzle/http/runtime/subsystems/auth.py` (mount)
- Test: `tests/integration/test_member_admin_pg.py`

- [ ] **Step 1: Add the CSRF protected paths** — in `csrf.py`, the `protected_paths` default list (after the 3a `/auth/invite`, `/auth/accept-invite` entries):

```python
            "/auth/members/roles",
            "/auth/members/suspend",
            "/auth/members/reactivate",
            "/auth/members/remove",
```

- [ ] **Step 2: Create the views** — `member_admin_views.py`. Reuse the SAME Fragment primitives 3a used (`Page(body=Stack(children=tuple))`, `FormStack(action=URL, fields, submit)`, `Field`, `Heading(body=, level=)`, `Text(body=, tone=)`, `Link`, `Submit`) plus `Button` (htmx action) and `Badge`:

```python
# src/dazzle/http/runtime/auth/member_admin_views.py
"""Typed-Fragment member-admin page (auth Plan 3b)."""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    Badge,
    Button,
    Field,
    FormStack,
    Heading,
    Link,
    Page,
    Stack,
    Submit,
    Text,
)

_CSS = ("/static/dist/dazzle.min.css",)
_JS = ("/static/dist/dazzle.min.js",)


def _member_block(
    *, membership_id: str, email: str, roles: list[str], status: str, is_last_admin: bool
) -> Stack:
    """One member's row: identity + roles + status, plus role-change + action controls."""
    role_text = ", ".join(roles) if roles else "—"
    children: list[Any] = [
        Text(body=f"{email} — {role_text}"),
        Badge(label=status, variant="muted" if status == "active" else "warning"),
        # Role change (plain form; comma-separated personas).
        FormStack(
            action=URL(f"/auth/members/roles?membership_id={membership_id}"),
            method="POST",
            fields=(
                Field(
                    name="roles",
                    label="Roles",
                    kind="text",
                    initial_value=", ".join(roles),
                ),
            ),
            submit=Submit(label="Update roles", variant="secondary"),
        ),
    ]
    # Suspend / reactivate (htmx action button → HX-Redirect back).
    if status == "active":
        children.append(
            Button(
                label="Suspend",
                variant="secondary",
                hx_post=f"/auth/members/suspend?membership_id={membership_id}",
                hx_confirm="Suspend this member's access?",
            )
        )
    elif status == "suspended":
        children.append(
            Button(
                label="Reactivate",
                variant="secondary",
                hx_post=f"/auth/members/reactivate?membership_id={membership_id}",
            )
        )
    # Remove — disabled for the last admin (server also enforces).
    children.append(
        Button(
            label="Remove",
            variant="danger",
            visibility="disabled" if is_last_admin else "default",
            hx_post=f"/auth/members/remove?membership_id={membership_id}",
            hx_confirm="Remove this member from the organization?",
        )
    )
    return Stack(children=tuple(children))


def build_members_view(
    *,
    product_name: str,
    org_name: str,
    members: list[dict[str, Any]],  # {membership_id, email, roles, status, is_last_admin}
    pending: list[dict[str, Any]],  # {email, roles}
) -> Page:
    body: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=f"Members of {org_name}", level=1),
        Heading(body="Invite a member", level=2),
        FormStack(
            action=URL("/auth/invite"),
            method="POST",
            fields=(
                Field(name="email", label="Email", kind="email", required=True),
                Field(name="roles", label="Roles (comma-separated)", kind="text"),
            ),
            submit=Submit(label="Send invitation", variant="primary"),
        ),
        Heading(body="Members", level=2),
    ]
    for m in members:
        body.append(
            _member_block(
                membership_id=m["membership_id"],
                email=m["email"],
                roles=m["roles"],
                status=m["status"],
                is_last_admin=m["is_last_admin"],
            )
        )
    body.append(Heading(body="Pending invitations", level=2))
    if not pending:
        body.append(Text(body="No pending invitations.", tone="muted"))
    else:
        for p in pending:
            roles = ", ".join(p["roles"]) if p["roles"] else "member"
            body.append(Text(body=f"{p['email']} — invited as {roles}"))
    return Page(
        title=f"Members — {product_name}",
        body=Stack(children=tuple(body)),
        css_links=_CSS,
        js_scripts=_JS,
    )
```

**NOTE:** confirm `Button.visibility` accepts `"default"`/`"disabled"` and `Badge.variant` accepts `"muted"`/`"warning"` at execution time (open `primitives/interactive.py` + the Badge primitive). If a value is invalid, use the nearest valid one — do not guess; read the primitive.

- [ ] **Step 3: Create the routes** — `member_admin_routes.py`. The shared gate is the security core:

```python
# src/dazzle/http/runtime/auth/member_admin_routes.py
"""Member-admin routes (auth Plan 3b): roster + role/suspend/reactivate/remove.

Every mutation runs the same gate:
  1. the caller has an ACTIVE membership in their active org whose roles intersect
     ``app.state.org_admin_roles`` (fail-closed `may_manage_members`);
  2. the TARGET membership belongs to the caller's active org (cross-org guard —
     a membership_id from another org is rejected, never managed);
  3. the change won't leave the org with zero active admins (orphan guard).
The org is always the caller's active membership's tenant_id — never request input.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.http.runtime.auth.cookie_name import read_session_id


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def _back_to_members(request: Request) -> Response:
    """HX-Redirect for htmx (action buttons), 303 for a plain form post."""
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": "/auth/members"})
    return RedirectResponse(url="/auth/members", status_code=303)


def create_member_admin_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    def _gate(request: Request):
        """Return (store, ctx, org_id) if the caller may manage members, else None."""
        from dazzle.http.runtime.auth.invitations import may_manage_members
        from dazzle.http.runtime.auth.models import effective_roles_of

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        if not may_manage_members(list(effective_roles_of(ctx)), org_admin_roles=org_admin_roles):
            return None
        return store, ctx, ctx.active_membership.tenant_id

    def _roster_rows(store, org_id):
        """(membership_id, roles, status) tuples for the org's current roster."""
        return [(m.id, list(m.roles), m.status) for m in store.get_memberships_for_tenant(org_id)]

    def _resolve_target(store, org_id, membership_id):
        """The target membership IFF it belongs to ``org_id`` (cross-org guard)."""
        m = store.get_membership(membership_id)
        if m is None or m.tenant_id != org_id:
            return None
        return m

    @router.get("/auth/members", response_class=HTMLResponse, include_in_schema=False)
    async def members_page(request: Request) -> HTMLResponse:
        from dazzle.http.runtime.auth.invitations import list_pending_invitations
        from dazzle.http.runtime.auth.member_admin import active_admins
        from dazzle.http.runtime.auth.member_admin_views import build_members_view
        from dazzle.render.fragment.renderer import FragmentRenderer
        from uuid import UUID

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        roster = _roster_rows(store, org_id)
        admins = set(active_admins(roster, org_admin_roles))
        last_admin = next(iter(admins)) if len(admins) == 1 else None

        members = []
        for m in store.get_memberships_for_tenant(org_id):
            user = store.get_user_by_id(UUID(m.identity_id))
            members.append(
                {
                    "membership_id": m.id,
                    "email": user.email if user is not None else m.identity_id,
                    "roles": list(m.roles),
                    "status": m.status,
                    "is_last_admin": m.id == last_admin,
                }
            )
        pending = [
            {"email": p.email, "roles": p.roles}
            for p in list_pending_invitations(store, org_id)
        ]
        org = store.get_organization(org_id)
        page = build_members_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else org_id,
            members=members,
            pending=pending,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.post("/auth/members/roles", include_in_schema=False)
    async def change_roles(
        request: Request,
        membership_id: Annotated[str, Query()] = "",
        roles: Annotated[str, Form()] = "",
    ) -> Response:
        from dazzle.http.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        target = _resolve_target(store, org_id, membership_id)
        if target is None:
            return HTMLResponse("Not found", status_code=404)
        new_roles = [r.strip() for r in roles.split(",") if r.strip()]
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        if would_orphan_org(
            _roster_rows(store, org_id), membership_id,
            new_roles=new_roles, org_admin_roles=org_admin_roles,
        ):
            return HTMLResponse("Cannot demote the last admin", status_code=409)
        store.update_membership_roles(membership_id, new_roles, actor_id=str(_ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/suspend", include_in_schema=False)
    async def suspend(
        request: Request, membership_id: Annotated[str, Query()] = ""
    ) -> Response:
        from dazzle.http.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        target = _resolve_target(store, org_id, membership_id)
        if target is None:
            return HTMLResponse("Not found", status_code=404)
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        if would_orphan_org(
            _roster_rows(store, org_id), membership_id,
            new_roles=None, org_admin_roles=org_admin_roles,
        ):
            return HTMLResponse("Cannot suspend the last admin", status_code=409)
        store.suspend_membership(membership_id, actor_id=str(_ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/reactivate", include_in_schema=False)
    async def reactivate(
        request: Request, membership_id: Annotated[str, Query()] = ""
    ) -> Response:
        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        target = _resolve_target(store, org_id, membership_id)
        if target is None:
            return HTMLResponse("Not found", status_code=404)
        store.reactivate_membership(membership_id, actor_id=str(_ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/remove", include_in_schema=False)
    async def remove(
        request: Request, membership_id: Annotated[str, Query()] = ""
    ) -> Response:
        from dazzle.http.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        target = _resolve_target(store, org_id, membership_id)
        if target is None:
            return HTMLResponse("Not found", status_code=404)
        org_admin_roles = list(getattr(request.app.state, "org_admin_roles", []) or [])
        if would_orphan_org(
            _roster_rows(store, org_id), membership_id,
            new_roles=None, org_admin_roles=org_admin_roles,
        ):
            return HTMLResponse("Cannot remove the last admin", status_code=409)
        store.remove_membership(membership_id, actor_id=str(_ctx.user.id))
        return _back_to_members(request)

    return router
```

**NOTE (ADR-0014):** this is a FastAPI route file — do NOT add `from __future__ import annotations`. The union return type `-> Response` is fine (single type), but if any handler annotates a union, add `response_model=None` (see 3a's accept route).

- [ ] **Step 4: Mount it** — in `subsystems/auth.py`, right after the 3a invitation-routes mount:

```python
        from dazzle.http.runtime.auth.member_admin_routes import create_member_admin_routes

        ctx.app.include_router(create_member_admin_routes())
```

- [ ] **Step 5: Write the integration route tests**

```python
# tests/integration/test_member_admin_pg.py
"""Real-PG route tests for the member-admin surface (auth Plan 3b)."""

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
    scratch = f"dazzle_memadm_{uuid.uuid4().hex[:8]}"
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


def _app(store, org_admin_roles):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.member_admin_routes import create_member_admin_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = list(org_admin_roles)
    app.state.sitespec = {}
    app.include_router(create_member_admin_routes())
    return app


def _admin_client(store, org, roles=("owner",)):
    """An authenticated TestClient for an admin of ``org`` + the admin membership."""
    from fastapi.testclient import TestClient

    admin = store.create_user(email="admin@acme.test", password="pw123456", roles=[])
    m = store.create_membership(tenant_id=org.id, identity_id=str(admin.id), roles=list(roles))
    sid = store.create_session(admin).id
    store.set_session_active_membership(sid, m.id, identity_id=str(admin.id))
    client = TestClient(_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    return client, admin, m


def test_members_page_lists_roster(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    r = client.get("/auth/members")
    assert r.status_code == 200
    assert "Members of Acme" in r.text
    assert "bob@acme.test" in r.text


def test_members_page_denies_non_admin(store_url: str) -> None:
    from fastapi.testclient import TestClient

    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    member = store.create_user(email="m@acme.test", password="pw123456", roles=[])
    m = store.create_membership(tenant_id=org.id, identity_id=str(member.id), roles=["member"])
    sid = store.create_session(member).id
    store.set_session_active_membership(sid, m.id, identity_id=str(member.id))
    client = TestClient(_app(store, org_admin_roles=["owner"]), follow_redirects=False)
    client.cookies.set("dazzle_session", sid)
    assert client.get("/auth/members").status_code == 403


def test_change_roles(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    r = client.post(f"/auth/members/roles?membership_id={bm.id}", data={"roles": "member, approver"})
    assert r.status_code in (204, 303)
    assert store.get_membership(bm.id).roles == ["member", "approver"]


def test_suspend_and_reactivate(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    assert client.post(f"/auth/members/suspend?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id).status == "suspended"
    assert client.post(f"/auth/members/reactivate?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id).status == "active"


def test_remove(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, _m = _admin_client(store, org)
    bob = store.create_user(email="bob@acme.test", password="pw123456", roles=[])
    bm = store.create_membership(tenant_id=org.id, identity_id=str(bob.id), roles=["member"])

    assert client.post(f"/auth/members/remove?membership_id={bm.id}").status_code in (204, 303)
    assert store.get_membership(bm.id) is None


def test_cross_org_target_is_rejected(store_url: str) -> None:
    # An admin of org A cannot manage a membership in org B (cross-org guard).
    store = _store(store_url)
    org_a = store.create_organization(slug="acme", name="Acme")
    org_b = store.create_organization(slug="other", name="Other")
    client, _admin, _m = _admin_client(store, org_a)
    victim = store.create_user(email="v@other.test", password="pw123456", roles=[])
    vm = store.create_membership(tenant_id=org_b.id, identity_id=str(victim.id), roles=["member"])

    r = client.post(f"/auth/members/remove?membership_id={vm.id}")
    assert r.status_code == 404
    assert store.get_membership(vm.id) is not None  # untouched


def test_cannot_remove_or_demote_last_admin(store_url: str) -> None:
    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    client, _admin, am = _admin_client(store, org)  # the only admin

    assert client.post(f"/auth/members/remove?membership_id={am.id}").status_code == 409
    assert store.get_membership(am.id) is not None
    assert client.post(f"/auth/members/suspend?membership_id={am.id}").status_code == 409
    r = client.post(f"/auth/members/roles?membership_id={am.id}", data={"roles": "member"})
    assert r.status_code == 409
    assert store.get_membership(am.id).roles == ["owner"]  # unchanged
```

- [ ] **Step 6: Run + commit**

```bash
ruff check src/dazzle/http/runtime/auth/member_admin_routes.py src/dazzle/http/runtime/auth/member_admin_views.py src/dazzle/http/runtime/subsystems/auth.py src/dazzle/http/runtime/csrf.py tests/integration/test_member_admin_pg.py --fix
ruff format src/dazzle/http/runtime/auth/member_admin_routes.py src/dazzle/http/runtime/auth/member_admin_views.py src/dazzle/http/runtime/subsystems/auth.py src/dazzle/http/runtime/csrf.py tests/integration/test_member_admin_pg.py
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_member_admin_pg.py -q
git add -A
git commit -m "feat(auth): member-admin surface — roster + role/suspend/remove routes (Plan 3b)"
```

---

## Task 3: Full verification + regression

- [ ] `mypy src/dazzle` (clean). Watch: the `_gate` tuple-return typing, the `Response` union returns.
- [ ] `python -m pytest tests/ -m "not e2e" -q` — full unit slice (member_admin unit + CSRF disposition tests for the 4 new protected_paths).
- [ ] `TEST_DATABASE_URL=... python -m pytest tests/integration/test_member_admin_pg.py tests/integration/test_org_invitations_pg.py -q` — member-admin + invitation regression.
- [ ] `dazzle inspect api runtime-urls --diff` → expect "No drift" (auth routers aren't in that baseline; confirm).
- [ ] Commit any fixes.

---

## Task 4: Adversarial review checkpoint (MANDATORY — security-sensitive)

- [ ] **Dispatch an independent reviewer** with this brief:
  - **Cross-org guard (the core):** can an admin of org A manage a membership in org B? Trace `_resolve_target` — is the org ALWAYS `ctx.active_membership.tenant_id` (never request input)? Is the target's `tenant_id` compared to it on EVERY mutation (roles/suspend/reactivate/remove)? Does a not-found vs wrong-org both 404 (no existence leak)?
  - **Authorization:** is `_gate` fail-closed (empty `org_admin_roles` → 403)? `effective_roles_of` (membership-sourced)? Does a suspended admin pass (should not — `active_membership` is None for suspended)? Unauthenticated → 403?
  - **Last-admin guard:** is `would_orphan_org` checked on remove + suspend + role-change (demotion)? Is it computed from the CURRENT roster (fresh read), not a stale one? Can a TOCTOU race (two concurrent demotions) drop the org to zero admins despite the guard? Note severity.
  - **Self-management:** can an admin remove/suspend/demote themselves and lock the org (covered by last-admin) or themselves out mid-session? Is that intended?
  - **CSRF:** are all 4 mutation paths in `protected_paths` (exact match)? The membership_id rides in the query — does that weaken anything (the origin gate still applies; confirm)?
  - **Silent failure:** do the store mutations' `None`/`False` returns get checked, or could a no-op be reported as success? Does `update_membership_roles` returning None (missing) after the guard passed indicate a race — handled?
  - **Injection / XSS:** roster email/roles rendered via Fragment (auto-escaped)? The `roles` free-text split — bounded?

- [ ] **Fix CRITICAL/HIGH inline; re-run. Commit hardening.**

---

## Task 5: CHANGELOG + ship

- [ ] CHANGELOG `### Added`: `GET /auth/members` + the 4 mutation routes, admin-gated + cross-org-guarded + last-admin orphan guard. `### Agent Guidance`: member-admin requires `[auth] org_admin_roles`; mutations only touch the admin's active org; the last admin can't be removed/suspended/demoted.
- [ ] `/bump patch`, then `/ship`.

---

## Self-Review

**1. Spec coverage (§7 Tier 1 member-admin):** roster → `GET /auth/members` ✓. invite → reuses 3a `POST /auth/invite` ✓. change roles / suspend / reactivate / remove → the 4 routes over 2a mutations ✓. Authz parameterized by personas → `org_admin_roles` ✓. Deferred (acknowledged): in-app org switcher (shell chrome) + runtime org creation (later slices); `multi_org:` flag + `archetype: profile` (3c).

**2. Placeholder scan:** every step has full code. The two soft spots (Fragment `Button.visibility`/`Badge.variant` valid values) are flagged to verify-then-write against the primitive, not guessed.

**3. Type consistency:** `active_admins`/`would_orphan_org` signatures match between `member_admin.py`, the routes, and the tests (roster = `list[(id, roles, status)]`; `new_roles: list[str] | None`). `_gate` returns `(store, ctx, org_id)`; `_resolve_target` returns a `MembershipRecord | None`. The view's `members` dict keys (`membership_id`/`email`/`roles`/`status`/`is_last_admin`) match what `members_page` builds and `_member_block` reads. Mutations use the 2a store methods with `actor_id=` (audit attribution).

**Open risks flagged for execution:** (a) the last-admin TOCTOU race (Task 4 — likely accept as low-severity given the rarity + the org-recovery path, or note it); (b) Fragment primitive value validation (Task 2 NOTE); (c) `_back_to_members` HX-Redirect vs 303 — tests accept either status.
```
