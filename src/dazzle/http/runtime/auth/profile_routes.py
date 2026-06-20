"""Member profile-resolution route (auth Plan 3c.ii).

``GET /me/profile``  — the current member's profile (a form, prefilled).
``POST /me/profile`` — upsert the current member's profile (scalar fields).

The profile is found via the app's ``is_profile`` entity + its Repository
(``app.state.repositories``). The RLS GUC is bound from the active membership
(``_bind_rls_tenant_id``) before touching the fenced profile table, so a create's
``tenant_id`` is auto-injected (Plan 1d) and RLS fences as defence-in-depth. The
read is scoped explicitly to ``(identity_id, tenant_id)`` — the caller's own
profile in their active org. ``identity_id`` is set server-side on create (never
client input); ``id``/``tenant_id``/``identity_id``/auto fields are framework-
managed and never client-editable.
"""

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.http.runtime.auth.cookie_name import read_session_id

# Fields the framework manages — never client-editable on a profile.
_MANAGED = {"id", "tenant_id", "identity_id", "created_at", "updated_at"}
# Editable kinds whose form value is a plain string that survives the repo's
# str-passthrough write unchanged. Typed scalars (int/bool/decimal/date/datetime)
# would need form→type coercion before the INSERT (the repo does not coerce a
# str), so they are NOT editable here yet — a documented follow-on. Limiting the
# set is fail-safe: a typed profile field simply isn't rendered/written rather
# than 500-ing on save.
_SCALAR_KINDS = {"str", "text", "enum"}


def _find_profile_entity(appspec: Any) -> Any | None:
    for e in getattr(getattr(appspec, "domain", None), "entities", []) or []:
        if getattr(e, "is_profile", False):
            return e
    return None


def _kind_of(field: Any) -> str:
    kind = getattr(field.type, "kind", None)
    return str(getattr(kind, "value", kind))


def _editable_scalar_fields(entity: Any) -> list[Any]:
    """Author-declared scalar fields a member may edit (exclude managed + non-scalar)."""
    return [f for f in entity.fields if f.name not in _MANAGED and _kind_of(f) in _SCALAR_KINDS]


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def create_profile_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    def _ctx_and_repo(request: Request) -> tuple[Any, Any, Any, Any] | None:
        """(store, ctx, entity, repo) when the caller can have a profile, else None."""
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

    async def _current_profile(
        repo: Any, *, identity_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """The caller's profile row in their active org (explicit scope + RLS fence)."""
        result = await repo.list(
            filters={"identity_id": identity_id, "tenant_id": tenant_id}, page_size=1
        )
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
        tenant_id = ctx.active_membership.tenant_id
        current = (
            await _current_profile(repo, identity_id=str(ctx.user.id), tenant_id=tenant_id) or {}
        )
        fields = [
            {"name": f.name, "label": getattr(f, "label", None) or f.name, "kind": _kind_of(f)}
            for f in _editable_scalar_fields(entity)
        ]
        org = store.get_organization(tenant_id)
        page = build_my_profile_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else tenant_id,
            fields=fields,
            current=current,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.post("/me/profile", include_in_schema=False, response_model=None)
    async def upsert_my_profile(request: Request) -> Response:
        from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id

        gated = _ctx_and_repo(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        _store, ctx, entity, repo = gated
        _bind_rls_tenant_id(ctx)
        tenant_id = ctx.active_membership.tenant_id
        identity_id = str(ctx.user.id)
        form = await request.form()
        editable = {f.name for f in _editable_scalar_fields(entity)}
        # Only author-declared editable scalars — a client cannot smuggle
        # id/tenant_id/identity_id (they're never in `editable`).
        data = {k: str(v) for k, v in form.items() if k in editable}

        existing = await _current_profile(repo, identity_id=identity_id, tenant_id=tenant_id)
        if existing is not None:
            await repo.update(existing["id"], data)
        else:
            data["id"] = str(uuid4())
            data["identity_id"] = identity_id  # server-set; tenant_id auto-injected (Plan 1d)
            await repo.create(data)
        return RedirectResponse(url="/me/profile", status_code=303)

    return router
