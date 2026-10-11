# Auth Plan 3c.ii — Member Profile Resolution Route

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 3c `archetype: profile` usable at runtime: a framework `GET /me/profile` (view) + `POST /me/profile` (upsert) that get-or-creates **the current member's** profile — keyed by `(active_membership.tenant_id, current_user.id)` — consuming the RLS fence, create-time `tenant_id` injection, and the profile schema end-to-end.

**Architecture:** A new auth route finds the app's profile entity (`is_profile`) + its `Repository` (exposed on `app.state.repositories`). Before touching the RLS-fenced profile table it binds the tenant GUC from the active membership via the existing `_bind_rls_tenant_id(ctx)` (so the query is fenced to the caller's org and a create's `tenant_id` is auto-injected). The profile is the member's own: read by `filters={"identity_id": current_user.id}` (RLS already fences to the org; identity_id narrows to the member), upsert sets `identity_id = current_user.id` server-side (never client input). Editable fields are the profile entity's author-declared **scalar** fields (str/int/bool/enum) — `id`/`tenant_id`/`identity_id`/auto fields are framework-managed and never client-editable.

**Tech Stack:** Python 3.12, FastAPI (`APIRouter`), the runtime `Repository` (async), typed Fragment UI, the RLS GUC binding (`tenant_isolation` contextvars), pytest (`e2e`+`postgres`). Consumes 3c (`archetype: profile`, `is_profile`), Plan 1d (create-time injection + membership-first GUC), Plan 1a–1b (session/active membership).

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §7 (Tier 1 — per-member profile). Slice **3c.ii** (3c `archetype: profile` shipped v0.81.43). The `tenancy: multi_org:` flag is deferred (YAGNI until a consumer needs it). File upload (`avatar: file`) is out of scope — scalar profile fields only.

**Decision (confirmed):** profile-resolution route (not the `multi_org:` flag).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/subsystems/auth.py` (**modify**) | Expose `ctx.app.state.repositories = ctx.repositories`; mount the profile route. |
| `src/dazzle/http/runtime/auth/profile_routes.py` (**create**) | `create_profile_routes()`: `GET /me/profile` + `POST /me/profile`. Finds the profile entity + repo, binds RLS, get-or-creates the current member's profile over scalar fields. |
| `src/dazzle/http/runtime/auth/profile_views.py` (**create**) | `build_my_profile_view(...)` — a form of the editable scalar fields, prefilled with the current profile. |
| `src/dazzle/http/runtime/csrf.py` (**modify**) | `protected_paths += /me/profile`. |
| `tests/integration/test_profile_resolution_pg.py` (**create**) | Real-PG: GET empty → form; POST creates (tenant_id auto-injected, identity_id = caller); POST again updates (no duplicate); a second member in the same org gets their own profile (identity-scoped); cross-tenant isolation (RLS). |

---

## Task 1: Expose repositories + a profile-entity finder

**Files:**
- Modify: `src/dazzle/http/runtime/subsystems/auth.py`
- Create: `src/dazzle/http/runtime/auth/profile_routes.py` (the finder helper first)
- Test: `tests/integration/test_profile_resolution_pg.py`

- [ ] **Step 1: Expose repositories on app.state** — in `subsystems/auth.py`, near `ctx.app.state.appspec = ctx.appspec`:

```python
        # auth Plan 3c.ii: expose the entity repositories so the /me/profile
        # route can resolve the profile entity's Repository at request time.
        ctx.app.state.repositories = ctx.repositories
```

- [ ] **Step 2: Write the failing integration test** (the harness + the first assertion — GET with no profile renders an empty form)

```python
# tests/integration/test_profile_resolution_pg.py
"""Real-PG proof of the member profile-resolution route (auth Plan 3c.ii)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = "fixtures/tenant_rls"


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_meprof_{uuid.uuid4().hex[:8]}"
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


def _booted(scratch_url: str):
    """Boot fixtures/tenant_rls in-process against the scratch DB (MemberProfile present)."""
    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _probe_transport

    built = _build_asgi_app(_PROJECT_ROOT, scratch_url)
    transport = _probe_transport(httpx.ASGITransport(app=built.app))
    return built, transport


def _login_member(built, scratch_url, *, email):
    """Provision an org + an active membership for a new identity; return its session id."""
    store = built.builder.auth_store
    from dazzle.db.provision import provision_single_org

    user = store.create_user(email=email, password="pw123456", roles=["worker"])
    with psycopg.connect(scratch_url) as conn:
        org_id = provision_single_org(built.builder._appspec if False else _appspec(), "Acme", conn=conn)  # noqa
    # NOTE: adapt provisioning to the harness; the goal is one active membership
    # for `user` in an org. Simplest: create_organization + create_membership +
    # create_session + set_session_active_membership, then set the cookie.
    ...
```

**IMPORTANT — adapt the harness:** the `_booted`/`_login_member` scaffold above is a sketch. Before writing, read `tests/integration/test_membership_rls_activation_pg.py` (it boots `fixtures/tenant_rls`, provisions an org + membership as a non-superuser, and binds RLS) and `tests/integration/test_member_admin_pg.py` (`_admin_client` mints a session cookie). Reuse the SIMPLEST working approach: `create_organization` + `create_membership` + `create_session(user).id` + `set_session_active_membership`, then `client.cookies.set("dazzle_session", sid)`. The route must run against the booted app (so `app.state.repositories` + RLS binding are real). The first concrete test:

```python
def test_get_my_profile_empty_renders_form(scratch_url: str) -> None:
    # Boot the app, provision a member, GET /me/profile → 200 + the display_name field.
    ...  # (concrete after the harness is adapted)
```

- [ ] **Step 3: Add the profile-entity finder** to `profile_routes.py`:

```python
# src/dazzle/http/runtime/auth/profile_routes.py
"""Member profile-resolution route (auth Plan 3c.ii).

`GET /me/profile`  — the current member's profile (a form, prefilled).
`POST /me/profile` — upsert the current member's profile (scalar fields).

The profile is found via the app's ``is_profile`` entity + its Repository
(``app.state.repositories``). The RLS GUC is bound from the active membership
(``_bind_rls_tenant_id``) before touching the fenced profile table, so the query
is fenced to the caller's org and a create's ``tenant_id`` is auto-injected
(Plan 1d). The profile is the member's own — read by ``identity_id`` and written
with ``identity_id = current_user.id`` (never client input).
"""

from typing import Any

# Fields the framework manages — never client-editable on a profile.
_MANAGED = {"id", "tenant_id", "identity_id", "created_at", "updated_at"}


def _find_profile_entity(appspec: Any) -> Any | None:
    for e in getattr(getattr(appspec, "domain", None), "entities", []):
        if getattr(e, "is_profile", False):
            return e
    return None


def _editable_scalar_fields(entity: Any) -> list[Any]:
    """Author-declared scalar fields a member may edit (exclude managed + non-scalar)."""
    out = []
    for f in entity.fields:
        if f.name in _MANAGED:
            continue
        kind = getattr(f.type, "kind", None)
        kind_val = getattr(kind, "value", kind)
        if kind_val in ("str", "text", "int", "bool", "decimal", "enum", "date", "datetime"):
            out.append(f)
    return out
```

- [ ] **Step 4 onward** — see Tasks 2–3 for the routes + views; run the empty-form test after Task 2.

- [ ] **Commit** (after Tasks 1–3 land together, since the test needs the routes):

```bash
git add src/dazzle/http/runtime/subsystems/auth.py src/dazzle/http/runtime/auth/profile_routes.py ...
git commit -m "feat(auth): expose repositories + profile-entity finder (Plan 3c.ii)"
```

---

## Task 2: The routes (GET view + POST upsert) + RLS binding

**Files:**
- Modify: `src/dazzle/http/runtime/auth/profile_routes.py`
- Create: `src/dazzle/http/runtime/auth/profile_views.py`
- Modify: `src/dazzle/http/runtime/csrf.py` (`protected_paths += "/me/profile"`)
- Modify: `src/dazzle/http/runtime/subsystems/auth.py` (mount)

- [ ] **Step 1: Add `/me/profile` to CSRF `protected_paths`** (after the 3b member paths):

```python
            "/me/profile",
```

- [ ] **Step 2: Views** — `profile_views.py` (reuse the 3a/3b Fragment primitives; render a Field per editable scalar, prefilled):

```python
# src/dazzle/http/runtime/auth/profile_views.py
"""Typed-Fragment view for the member's own profile (auth Plan 3c.ii)."""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import URL, Field, FormStack, Heading, Link, Page, Stack, Submit, Text

_CSS = ("/static/dist/dazzle.min.css",)
_JS = ("/static/dist/dazzle.min.js",)

# Map IR/back field kinds → Fragment Field input kinds (scalars only).
_KIND = {
    "str": "text", "text": "textarea", "int": "number", "decimal": "number",
    "bool": "checkbox", "date": "date", "datetime": "datetime-local", "enum": "text",
}


def build_my_profile_view(
    *, product_name: str, org_name: str, fields: list[dict[str, Any]], current: dict[str, Any]
) -> Page:
    """`fields`: [{name, label, kind}]; `current`: the existing profile values (or {})."""
    form_fields = tuple(
        Field(
            name=f["name"],
            label=f["label"],
            kind=_KIND.get(f["kind"], "text"),
            initial_value=str(current.get(f["name"], "") or ""),
        )
        for f in fields
    )
    return Page(
        title=f"Your profile — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                Heading(body=f"Your profile in {org_name}", level=1),
                Text(body="Update your member profile.", tone="muted"),
                FormStack(
                    action=URL("/me/profile"),
                    method="POST",
                    fields=form_fields,
                    submit=Submit(label="Save profile", variant="primary"),
                ),
            )
        ),
        css_links=_CSS,
        js_scripts=_JS,
    )
```

(If `FormStack` requires ≥1 field and a profile has zero editable scalars, render a Text "no editable fields" instead — guard `if not form_fields`.)

- [ ] **Step 3: The routes** — append to `profile_routes.py`:

```python
def create_profile_routes() -> "APIRouter":  # noqa: F821
    from fastapi import APIRouter, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, Response

    from dazzle.http.runtime.auth.cookie_name import read_session_id

    router = APIRouter(tags=["auth"])

    def _product_name(request: Request) -> str:
        sitespec = getattr(request.app.state, "sitespec", None) or {}
        brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
        return str(brand.get("product_name", "Dazzle"))

    def _ctx_and_repo(request: Request):
        """(store, ctx, profile_entity, repo) when the caller can have a profile, else None."""
        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        entity = _find_profile_entity(getattr(request.app.state, "appspec", None))
        repos = getattr(request.app.state, "repositories", None) or {}
        if entity is None or entity.name not in repos:
            return None
        return store, ctx, entity, repos[entity.name]

    async def _current_profile(repo: Any, identity_id: str) -> dict[str, Any] | None:
        """The caller's profile row (RLS fences to the org; identity_id narrows)."""
        result = await repo.list(filters={"identity_id": identity_id}, page_size=1)
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            return None
        row = items[0]
        return row if isinstance(row, dict) else row.model_dump()

    @router.get("/me/profile", response_class=HTMLResponse, include_in_schema=False)
    async def my_profile(request: Request) -> HTMLResponse:
        from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id
        from dazzle.http.runtime.auth.profile_views import build_my_profile_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        gated = _ctx_and_repo(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, ctx, entity, repo = gated
        _bind_rls_tenant_id(ctx)  # bind dazzle.tenant_id from the active membership
        current = await _current_profile(repo, str(ctx.user.id)) or {}
        fields = [
            {"name": f.name, "label": getattr(f, "label", None) or f.name, "kind": _kind_of(f)}
            for f in _editable_scalar_fields(entity)
        ]
        org = store.get_organization(ctx.active_membership.tenant_id)
        page = build_my_profile_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else ctx.active_membership.tenant_id,
            fields=fields,
            current=current,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.post("/me/profile", include_in_schema=False)
    async def upsert_my_profile(request: Request) -> Response:
        from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id

        gated = _ctx_and_repo(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        _store, ctx, entity, repo = gated
        _bind_rls_tenant_id(ctx)
        form = await request.form()
        editable = {f.name for f in _editable_scalar_fields(entity)}
        data = {k: v for k, v in form.items() if k in editable}
        identity_id = str(ctx.user.id)
        existing = await _current_profile(repo, identity_id)
        if existing is not None:
            await repo.update(existing["id"], data)
        else:
            import uuid as _uuid

            data["id"] = str(_uuid.uuid4())
            data["identity_id"] = identity_id  # server-set; tenant_id auto-injected (Plan 1d)
            await repo.create(data)
        return RedirectResponse(url="/me/profile", status_code=303)

    return router


def _kind_of(field: Any) -> str:
    kind = getattr(field.type, "kind", None)
    return str(getattr(kind, "value", kind))
```

**NOTES:** (a) `_MANAGED` excludes `identity_id` from `editable`, so a client cannot set it via the form — the POST sets it server-side only on create. (b) On UPDATE, `identity_id`/`tenant_id` are not in `data` (managed), so they can't be moved. (c) ADR-0014: no `from __future__ import annotations` in this route file. (d) the `-> Response` union on the POST (HTMLResponse | RedirectResponse) — add `response_model=None` if FastAPI complains (see 3a).

- [ ] **Step 4: Mount** — in `subsystems/auth.py`, after the 3b member-admin mount:

```python
        from dazzle.http.runtime.auth.profile_routes import create_profile_routes

        ctx.app.include_router(create_profile_routes())
```

---

## Task 3: Real-PG integration tests (the consumption proof)

**Files:**
- `tests/integration/test_profile_resolution_pg.py`

Adapt the harness (read the two sibling tests named above), then assert:

- [ ] **GET empty → form**: a freshly-provisioned member GETs `/me/profile` → 200, body contains the `display_name` field, no row yet.
- [ ] **POST creates**: POST `display_name=Alice` → 303; the profile row exists with `display_name=Alice`, `identity_id = caller`, and `tenant_id = active org` (auto-injected — assert via direct SQL as a non-superuser or the seeded org id).
- [ ] **POST again updates (no duplicate)**: POST `display_name=Alicia` → the SAME row updates (`count(*) where identity_id = caller == 1`), `display_name=Alicia`.
- [ ] **identity-scoped**: a SECOND member in the same org has NO profile after the first member created theirs (GET → empty), and creating theirs yields a distinct row (two rows in the org, one per identity).
- [ ] **client cannot set identity_id/tenant_id**: POST with extra `identity_id=<other>`/`tenant_id=<other>` form fields → ignored (the created/updated row keeps the caller's identity + the bound tenant).
- [ ] **Run**: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_profile_resolution_pg.py -q`
- [ ] **Commit** the routes + views + mount + CSRF + tests together.

---

## Task 4: Verification + adversarial review + ship

- [ ] **Verify:** `mypy src/dazzle`; `python -m pytest tests/ -m "not e2e" -q` (CSRF disposition for `/me/profile`; no api-surface drift — auth routers aren't in the runtime-urls baseline); the profile-resolution + tenant_rls regression suites.
- [ ] **Adversarial review** (security-sensitive — RLS-fenced cross-tenant/cross-member access):
  - Can a member read/write ANOTHER member's profile (identity_id is server-set on write; read filters by caller's identity — confirm no path takes identity_id from input)?
  - Is the RLS GUC actually bound before every repo op (GET + POST), so a missing bind can't leak/cross-tenant-write (fail-closed: unbound GUC → create-injection NOT-NULL-fails, query fences to nothing)?
  - Can a client smuggle `tenant_id`/`identity_id`/`id` via extra form fields into create/update (the `_MANAGED`/`editable` filter — confirm both create and update drop them)?
  - Upsert race: two concurrent POSTs for a member with no profile → both create → the tenant-scoped `UNIQUE(tenant_id, identity_id)` rejects the second (clean integrity error, not a duplicate) — confirm it surfaces sanely.
  - CSRF: `/me/profile` POST in `protected_paths`; same-origin admitted by the origin gate.
  - An app with NO profile entity → `/me/profile` 403/404 cleanly (no crash).
- [ ] **Fix findings; CHANGELOG; `/bump patch`; `/ship`.**

---

## Self-Review

**1. Spec coverage (§7 per-member profile):** runtime access to `archetype: profile` → `GET/POST /me/profile` get-or-create ✓. Keyed by `(active tenant, current_user.id)` → RLS bind + identity_id filter/set ✓. Consumes RLS fence + create-injection + profile schema ✓. Deferred (acknowledged): `tenancy: multi_org:` flag (YAGNI), `avatar: file` (scalar fields only), an app-shell nav link to the profile.

**2. Placeholder scan:** the route/view code is concrete; the test harness is explicitly a "read the two sibling tests and adapt" task (the boot/login scaffold differs per harness) — resolve at execution, don't guess.

**3. Type consistency:** `_find_profile_entity`/`_editable_scalar_fields`/`_kind_of`/`_current_profile` signatures match their call sites; `_ctx_and_repo` returns `(store, ctx, entity, repo)`; the view's `fields=[{name,label,kind}]` + `current={}` match what the route builds; `repo.list(filters=)['items']`, `repo.update(id, data)`, `repo.create(data)` match the Repository API.

**Open risks for execution:** (a) the RLS-bind-before-repo-op is THE correctness invariant — the adversarial review must confirm it on both GET and POST; (b) `repo.create` returning the model with the auto-injected tenant_id (Plan 1d) — the test asserts tenant_id landed; (c) harness adaptation (boot + session cookie) is the main execution unknown — mirror `test_member_admin_pg.py` + `test_membership_rls_activation_pg.py`.
```
