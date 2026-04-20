"""
Page routes for server-rendered Dazzle pages.

Creates FastAPI routes that render full HTML pages using Jinja2 templates.
Each workspace+surface combination gets a GET route that:
1. Calls the template compiler to get a PageContext
2. Fetches data from the backend service
3. Renders the Jinja2 template
4. Returns an HTMLResponse
"""

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from dazzle.core import ir
from dazzle.core.access import AccessOperationKind, AccessRuntimeContext
from dazzle.core.manifest import resolve_api_url

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# =============================================================================
# Helpers (module-level, no closure state)
# =============================================================================


def _sync_fetch(url: str, cookies: dict[str, str] | None = None, timeout: int = 5) -> bytes:
    """Synchronous HTTP GET — runs in a thread to avoid blocking the event loop."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    req = urllib.request.Request(url)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
        data: bytes = resp.read()
        return data


async def _fetch_url(url: str, cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """Async-safe HTTP GET that returns parsed JSON.

    Uses asyncio.to_thread so the blocking urllib call doesn't stall
    the event loop — critical when the backend runs in the same process.
    """
    raw = await asyncio.to_thread(_sync_fetch, url, cookies)
    result: dict[str, Any] = json.loads(raw)
    return result


def _resolve_backend_url(request: Any, fallback: str) -> str:
    """Derive the backend URL for internal API calls.

    Resolution order (first non-empty wins):

    1. ``DAZZLE_BACKEND_URL`` env var — explicit override for split-service
       deployments where the frontend can't discover the backend from its
       own request (e.g. frontend on Cloudflare, backend on AWS).
    2. ``PORT`` env var — single-dyno platforms (Heroku, Railway) where the
       port is dynamic.  Stays on localhost to avoid SSL/router overhead.
    3. ``request.base_url`` — same-origin setups where the page request
       already hit the correct host:port.
    4. ``fallback`` — hardcoded default (``http://127.0.0.1:8000``), used
       during local development.
    """
    explicit = os.environ.get("DAZZLE_BACKEND_URL", "").rstrip("/")
    if explicit:
        return explicit
    port = os.environ.get("PORT")
    if port:
        return f"http://127.0.0.1:{port}"
    try:
        base = str(request.base_url).rstrip("/")
        if base:
            return base
    except Exception:
        logger.warning("Failed to extract base_url from request", exc_info=True)
    return fallback


async def _fetch_json(
    backend_url: str,
    api_pattern: str | None,
    path_id: Any,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch a single entity record from the backend API.

    Args:
        backend_url: Base URL of the backend (e.g. "http://127.0.0.1:8000").
        api_pattern: URL pattern with ``{id}`` placeholder (e.g. "/contacts/{id}").
        path_id: The entity ID to substitute.
        cookies: Optional cookies to forward (e.g. session cookie for auth).

    Returns:
        Parsed JSON dict, or a fallback dict with ``error`` key on failure.
    """
    if not api_pattern or "{id}" not in api_pattern:
        return {"id": str(path_id), "error": "No API pattern"}
    url = f"{backend_url}{api_pattern.replace('{id}', str(path_id))}"
    try:
        return await _fetch_url(url, cookies)
    except Exception:
        logger.warning("Failed to fetch entity data from %s", url, exc_info=True)
        return {"id": str(path_id), "error": "Failed to load"}


def _inject_integration_actions(appspec: ir.AppSpec, page_contexts: dict[str, Any]) -> None:
    """Populate integration_actions on detail contexts from appspec integrations."""
    from dazzle.core.ir.integrations import MappingTriggerType
    from dazzle.core.strings import to_api_plural
    from dazzle_ui.runtime.template_context import IntegrationActionContext

    # Build entity_name -> list of manual trigger actions
    manual_actions: dict[str, list[IntegrationActionContext]] = {}
    for integration in appspec.integrations:
        for mapping in integration.mappings:
            for trigger in mapping.triggers:
                if trigger.trigger_type == MappingTriggerType.MANUAL:
                    entity = mapping.entity_ref
                    label = trigger.label or mapping.name.replace("_", " ").title()
                    slug = to_api_plural(entity)
                    action = IntegrationActionContext(
                        label=label,
                        integration_name=integration.name,
                        mapping_name=mapping.name,
                        api_url=f"/{slug}/{{id}}/integrations/{integration.name}/{mapping.name}",
                    )
                    manual_actions.setdefault(entity, []).append(action)

    if not manual_actions:
        return

    # Inject into detail contexts
    for ctx in page_contexts.values():
        if ctx.detail and ctx.detail.entity_name in manual_actions:
            ctx.detail = ctx.detail.model_copy(
                update={"integration_actions": manual_actions[ctx.detail.entity_name]}
            )


def _is_field_cond(cond: Any) -> bool:
    """Return True if condition needs record data to evaluate."""
    if cond is None:
        return False
    kind = getattr(cond, "kind", None)
    if kind == "role_check":
        return False
    if kind in ("comparison", "grant_check"):
        return True
    if kind == "logical":
        return _is_field_cond(getattr(cond, "logical_left", None)) or _is_field_cond(
            getattr(cond, "logical_right", None)
        )
    return False


def _should_suppress_mutations(
    deps: "_PageDeps",
    surface_name: str | None,
    auth_ctx: Any,
    user_roles: list[str],
) -> bool:
    """Check if all mutations should be suppressed (workspace read_only)."""
    # Check workspace persona variant read_only directive
    if surface_name and deps.surface_workspace.get(surface_name):
        ws_name = deps.surface_workspace[surface_name]
        for ws in deps.appspec.workspaces:
            if ws.name == ws_name and ws.ux and ws.ux.persona_variants:
                normalized = [r.removeprefix("role_") for r in user_roles]
                for variant in ws.ux.persona_variants:
                    if variant.persona in normalized and variant.read_only:
                        return True
    return False


def _user_can_mutate(
    deps: "_PageDeps",
    surface_name: str | None,
    operation: str,
    auth_ctx: Any,
) -> bool:
    """Check if user can perform a mutation (create/update/delete) on the entity."""
    if not surface_name or not deps.entity_cedar_specs or auth_ctx is None:
        return True  # No access control configured

    if deps.evaluate_permission is None:
        return True  # No evaluator available

    _entity_name = deps.surface_entity.get(surface_name)
    _cedar_spec = deps.entity_cedar_specs.get(_entity_name) if _entity_name else None
    if _cedar_spec is None:
        return True  # No access rules for this entity

    op_map = {
        "create": AccessOperationKind.CREATE,
        "update": AccessOperationKind.UPDATE,
        "delete": AccessOperationKind.DELETE,
    }
    _op = op_map.get(operation)
    if _op is None:
        return True

    # Only evaluate when rules are pure role checks (no field conditions)
    _op_rules = [r for r in _cedar_spec.permissions if r.operation == _op]
    _has_scopes = bool(getattr(_cedar_spec, "scopes", None))
    _has_field_conditions = (
        False if _has_scopes else any(_is_field_cond(r.condition) for r in _op_rules)
    )
    if not _op_rules or _has_field_conditions:
        return True  # No rules or needs record context — allow UI button

    _user = auth_ctx.user if auth_ctx.is_authenticated else None
    _raw_roles = list(getattr(_user, "roles", [])) if _user else []
    _runtime_ctx = AccessRuntimeContext(
        user_id=str(_user.id) if _user else None,
        roles=[r.removeprefix("role_") for r in _raw_roles],
        is_superuser=getattr(_user, "is_superuser", False) if _user else False,
    )
    _decision = deps.evaluate_permission(
        _cedar_spec,
        _op,
        None,
        _runtime_ctx,
        entity_name=_entity_name or "",
    )
    return bool(_decision.allowed)


def _apply_persona_overrides(req_table: Any, user_roles: list[str]) -> None:
    """Apply per-persona PersonaVariant overrides to a per-request table copy.

    Walks ``user_roles`` (with the ``role_`` prefix stripped) in order
    and applies the first matching persona's overrides from the compile-
    time dicts on ``req_table``. Each overridable field has its own dict
    on the TableContext:

    - ``persona_empty_messages: dict[str, str]`` — cycle 240 pilot
    - ``persona_hide: dict[str, list[str]]`` — cycle 243 extension

    The compile-dict-then-resolve-per-request pattern generalises to
    every PersonaVariant field (``purpose``, ``show``, ``action_primary``,
    ``read_only``, ``defaults``, ``focus``). Adding a new field is a
    3-step extension:

    1. Add the dict to ``TableContext`` in ``template_context.py``.
    2. Populate it in ``_compile_list_surface`` from ``ux.persona_variants``.
    3. Apply its resolution semantics inside this helper.

    The first two steps are mechanical; only the resolution semantics
    are field-specific (hide → set ``column.hidden=True``,
    ``empty_message`` → swap the base string, ``read_only`` → suppress
    mutation affordances, etc.).

    Mutates ``req_table`` in place. Safe to call with empty dicts or
    empty user_roles — it's a no-op in both cases. Designed to be
    idempotent and testable in isolation.
    """
    if not user_roles:
        return

    persona_empty = getattr(req_table, "persona_empty_messages", None) or {}
    persona_hide = getattr(req_table, "persona_hide", None) or {}
    persona_read_only = getattr(req_table, "persona_read_only", None) or set()

    if not persona_empty and not persona_hide and not persona_read_only:
        return

    for role in user_roles:
        normalised = role.removeprefix("role_")

        matched = False

        # Empty-message override (cycle 240)
        if normalised in persona_empty:
            req_table.empty_message = persona_empty[normalised]
            matched = True

        # Column hide override (cycle 243). Hide every column whose key
        # is in the persona's hide list. Stacks on top of cycle 240's
        # condition-eval column hiding — both set ``hidden=True`` on
        # the per-request copy, and the DataTable template already
        # honours it.
        if normalised in persona_hide:
            hide_set = set(persona_hide[normalised])
            if hide_set:
                for col in req_table.columns:
                    if col.key in hide_set:
                        col.hidden = True
            matched = True

        # Read-only persona declaration (cycle 244). Suppresses every
        # mutation affordance on the table: Create button, bulk-action
        # bar, and inline-edit. Distinct from ``_should_suppress_mutations``
        # which gates on ``permit:`` rules — this is an explicit DSL
        # persona-variant declaration and takes precedence.
        if normalised in persona_read_only:
            req_table.create_url = None
            req_table.bulk_actions = False
            req_table.inline_editable = []
            matched = True

        # First matching persona wins for all override fields. Stops
        # the loop early so later roles can't silently clobber earlier
        # ones — the user's primary persona (typically first in the
        # user_roles list) takes precedence.
        if matched:
            return


def _apply_persona_form_overrides(req_form: Any, user_roles: list[str]) -> bool:
    """Apply per-persona PersonaVariant overrides to a per-request form copy.

    Cycle 245 — form-surface parallel to ``_apply_persona_overrides``.
    Walks ``user_roles`` (with the ``role_`` prefix stripped) in order
    and applies the first matching persona's overrides from the
    compile-time dicts on ``req_form``:

    - ``persona_hide: dict[str, list[str]]`` — field hide list per persona
    - ``persona_read_only: set[str]`` — persona ids that cannot mutate

    Hide semantics: fields whose ``name`` is in the persona's hide list
    are removed from ``req_form.fields``, ``req_form.sections[*].fields``,
    and ``req_form.initial_values``. Removing from initial_values as
    well prevents any pre-filled value from landing in the POST body
    (defensive against hidden-field injection — the hidden fields
    genuinely don't exist for this persona).

    Read-only semantics: if the persona is in ``persona_read_only``,
    the helper returns ``True`` to signal the caller should abort
    form rendering entirely (typically by raising 403 or redirecting
    to the read-only detail view). The helper does NOT mutate the
    form in this case — the caller decides what to do.

    Returns ``True`` if the persona is read-only (caller should
    abort), ``False`` otherwise.

    Closes gap doc #2 axis 4 (persona-unaware-affordances, create-form
    field visibility) for the list-to-form half. The list-column half
    was closed in cycle 243.
    """
    if not user_roles:
        return False

    persona_hide = getattr(req_form, "persona_hide", None) or {}
    persona_read_only = getattr(req_form, "persona_read_only", None) or set()

    if not persona_hide and not persona_read_only:
        return False

    for role in user_roles:
        normalised = role.removeprefix("role_")

        matched = False

        # Read-only persona declaration. Signal caller to abort.
        if normalised in persona_read_only:
            return True

        # Field hide override. Remove matching fields from the flat
        # list, every section's field list, and initial_values.
        if normalised in persona_hide:
            hide_set = set(persona_hide[normalised])
            if hide_set:
                req_form.fields = [f for f in req_form.fields if f.name not in hide_set]
                for section in req_form.sections or []:
                    section.fields = [f for f in section.fields if f.name not in hide_set]
                if req_form.initial_values:
                    for key in list(req_form.initial_values.keys()):
                        if key in hide_set:
                            del req_form.initial_values[key]
            matched = True

        if matched:
            return False

    return False


def _filter_nav_by_entity_access(
    nav_items: list[Any],
    deps: "_PageDeps",
    auth_ctx: Any,
) -> list[Any]:
    """Remove nav items whose entity denies the user's role for LIST (#583)."""
    if auth_ctx is None or not auth_ctx.is_authenticated:
        return nav_items

    if deps.evaluate_permission is None:
        return nav_items  # No evaluator available

    _user = auth_ctx.user
    _raw_roles = list(getattr(_user, "roles", [])) if _user else []
    _runtime_ctx = AccessRuntimeContext(
        user_id=str(_user.id) if _user else None,
        roles=[r.removeprefix("role_") for r in _raw_roles],
        is_superuser=getattr(_user, "is_superuser", False) if _user else False,
    )
    if _runtime_ctx.is_superuser:
        return nav_items

    filtered: list[Any] = []
    for item in nav_items:
        entity_name = deps.route_entity.get(item.route)
        if entity_name is None:
            # Not an entity route (e.g. workspace link) — keep it
            filtered.append(item)
            continue
        cedar_spec = deps.entity_cedar_specs.get(entity_name)
        if cedar_spec is None:
            # No access rules — keep it
            filtered.append(item)
            continue
        _op_rules = [r for r in cedar_spec.permissions if r.operation == AccessOperationKind.LIST]
        _has_scopes = bool(getattr(cedar_spec, "scopes", None))
        _has_field_conditions = (
            False if _has_scopes else any(_is_field_cond(r.condition) for r in _op_rules)
        )
        if not _op_rules or _has_field_conditions:
            # No rules or needs record context — keep the item visible
            filtered.append(item)
            continue
        _decision = deps.evaluate_permission(
            cedar_spec,
            AccessOperationKind.LIST,
            None,
            _runtime_ctx,
            entity_name=entity_name,
        )
        if _decision.allowed:
            filtered.append(item)
    return filtered


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _PageDeps:
    appspec: ir.AppSpec
    backend_url: str
    theme_css: str
    get_auth_context: Callable[..., Any] | None
    app_prefix: str
    page_contexts: dict[str, Any] = field(default_factory=dict)
    access_configs: dict[str, Any] = field(default_factory=dict)
    entity_cedar_specs: dict[str, Any] = field(default_factory=dict)
    surface_entity: dict[str, str] = field(default_factory=dict)
    surface_mode: dict[str, str] = field(default_factory=dict)
    surface_workspace: dict[str, str] = field(default_factory=dict)
    # Route path → entity name — for filtering sidebar nav items by entity permit (#583)
    route_entity: dict[str, str] = field(default_factory=dict)
    # Callables injected from dazzle_back — breaks circular import (#679)
    evaluate_permission: Callable[..., Any] | None = None
    inject_display_names: Callable[..., Any] | None = None


# =============================================================================
# Per-request context for _page_handler helpers
# =============================================================================


@dataclass
class _PageRequestContext:
    """Shared state built once per request, passed to each handler helper."""

    deps: _PageDeps
    ctx: Any
    request: Any  # FastAPI Request
    auth_ctx: Any  # AuthContext | None
    surface_name: str | None
    effective_backend_url: str
    cookies: dict[str, str] | None
    path_id: Any  # str | None
    ctx_overrides: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# _page_handler helper functions
# =============================================================================


def _inject_auth_context(prc: _PageRequestContext) -> None:
    """Resolve auth context from request and inject into page context."""
    if prc.deps.get_auth_context is None:
        return
    try:
        prc.auth_ctx = prc.deps.get_auth_context(prc.request)
        prc.ctx.is_authenticated = bool(prc.auth_ctx and prc.auth_ctx.is_authenticated)
        if prc.auth_ctx and prc.auth_ctx.user:
            prc.ctx.user_email = prc.auth_ctx.user.email or ""
            prc.ctx.user_name = prc.auth_ctx.user.username or ""
            prc.ctx.user_preferences = prc.auth_ctx.preferences or {}
            # Persona-aware nav filtering: match user roles against
            # per-persona nav variants compiled from workspace access.
            roles = getattr(prc.auth_ctx.user, "roles", None) or []
            prc.ctx.user_roles = list(roles)
            if prc.ctx.nav_by_persona and roles:
                for role in roles:
                    # Roles use "role_" prefix; persona IDs don't
                    persona_nav = prc.ctx.nav_by_persona.get(role.removeprefix("role_"))
                    if persona_nav is not None:
                        prc.ctx.nav_items = persona_nav
                        break

            # Filter out nav items for entities the user cannot LIST (#583).
            # This catches entities that appear in an allowed workspace but
            # whose permit: rules deny the user's role.
            if prc.ctx.nav_items and prc.deps.entity_cedar_specs and prc.deps.route_entity:
                prc.ctx.nav_items = _filter_nav_by_entity_access(
                    prc.ctx.nav_items, prc.deps, prc.auth_ctx
                )
    except Exception:
        logger.debug("Failed to resolve auth context for page", exc_info=True)


def _check_surface_access(prc: _PageRequestContext) -> Response | None:
    """Enforce surface-level access control. Returns a Response to abort, or None."""
    from dazzle_ui.runtime.surface_access import (
        SurfaceAccessDenied,
        check_surface_access,
    )

    if not prc.surface_name or prc.surface_name not in prc.deps.access_configs:
        return None

    ac = prc.deps.access_configs[prc.surface_name]
    user = None
    user_personas: list[str] | None = None
    if prc.auth_ctx and prc.auth_ctx.is_authenticated and prc.auth_ctx.user:
        user = {"id": getattr(prc.auth_ctx.user, "id", None)}
        _raw = list(getattr(prc.auth_ctx.user, "roles", []))
        user_personas = [r.removeprefix("role_") for r in _raw]
    try:
        check_surface_access(ac, user, user_personas=user_personas, is_api_request=False)
    except SurfaceAccessDenied as e:
        if e.is_auth_required and e.redirect_url:
            return RedirectResponse(url=e.redirect_url, status_code=302)
        return JSONResponse(
            status_code=403,
            content={"detail": e.reason},
        )
    return None


def _check_entity_cedar_access(prc: _PageRequestContext) -> Response | None:
    """Enforce entity-level Cedar access rules on page routes (#527).

    Mirrors the LIST gate in route_generator.py: only enforce when all
    permission rules for the operation are pure role checks (no field
    conditions). Field-condition rules need a record to evaluate -- those
    are handled at query time by the API layer's row filters.

    Returns a Response to abort, or None to continue.
    """
    if not prc.surface_name or not prc.deps.entity_cedar_specs or prc.auth_ctx is None:
        return None

    _entity_name = prc.deps.surface_entity.get(prc.surface_name)
    _cedar_spec = prc.deps.entity_cedar_specs.get(_entity_name) if _entity_name else None
    if _cedar_spec is None or prc.deps.evaluate_permission is None:
        return None

    # Determine operation: list surfaces use LIST, create surfaces
    # use CREATE, others use READ.
    _mode = prc.deps.surface_mode.get(prc.surface_name, "list")
    if _mode == "list":
        _op = AccessOperationKind.LIST
    elif _mode == "create":
        _op = AccessOperationKind.CREATE
    else:
        _op = AccessOperationKind.READ

    # Only gate when all rules for this operation are pure role checks.
    # When scopes are present, permit rules are guaranteed role-only
    # (scope: blocks hold all field-condition logic), so always fire
    # the gate. When scopes are absent (backward compat), skip if any
    # rule carries a field condition -- those require a record to evaluate
    # and are handled at query time by the API layer's row filters.
    _op_rules = [r for r in _cedar_spec.permissions if r.operation == _op]
    _has_scopes = bool(getattr(_cedar_spec, "scopes", None))

    _has_field_conditions = (
        False if _has_scopes else any(_is_field_cond(r.condition) for r in _op_rules)
    )
    if not _op_rules or _has_field_conditions:
        return None

    # Build AccessRuntimeContext from auth context
    _user = prc.auth_ctx.user if prc.auth_ctx.is_authenticated else None
    _raw_roles = list(getattr(_user, "roles", [])) if _user else []
    _runtime_ctx = AccessRuntimeContext(
        user_id=str(_user.id) if _user else None,
        roles=[r.removeprefix("role_") for r in _raw_roles],
        is_superuser=getattr(_user, "is_superuser", False) if _user else False,
    )
    _decision = prc.deps.evaluate_permission(
        _cedar_spec,
        _op,
        None,
        _runtime_ctx,
        entity_name=_entity_name or "",
    )
    if not _decision.allowed:
        # Raise an HTTPException with a structured detail so the
        # global exception handler renders the enhanced HTML 403
        # page with role disclosure (#808). Previously this path
        # returned a bare JSONResponse, stranding browser users
        # with a raw JSON body on what should be an HTML route.
        from fastapi import HTTPException

        from dazzle_back.runtime.route_generator import _forbidden_detail

        raise HTTPException(
            status_code=403,
            detail=_forbidden_detail(
                entity_name=_entity_name or "",
                operation=_op,
                cedar_access_spec=_cedar_spec,
                current_roles=list(_runtime_ctx.roles),
            ),
        )
    return None


async def _handle_detail(prc: _PageRequestContext) -> None:
    """Fetch and prepare detail page data for the per-request context."""
    req_detail = prc.ctx.detail.model_copy(deep=True)

    # Fetch item data using the API endpoint template
    req_detail.item = await _fetch_json(
        prc.effective_backend_url,
        prc.ctx.detail.api_endpoint or prc.ctx.detail.delete_url,
        prc.path_id,
        prc.cookies,
    )
    # Resolve FK dicts -> display strings so detail fields show names not UUIDs (#663)
    if req_detail.item and "error" not in req_detail.item:
        if prc.deps.inject_display_names is not None:
            req_detail.item = prc.deps.inject_display_names(req_detail.item)

    if "error" in req_detail.item:
        logger.warning(
            "Detail page data fetch failed for %s/%s: %s",
            prc.ctx.detail.entity_name,
            prc.path_id,
            req_detail.item.get("error"),
        )
        raise HTTPException(status_code=404, detail="Not found")

    # Evaluate when_expr for conditional field visibility (#363)
    if req_detail.item and "error" not in req_detail.item:
        from dazzle_ui.utils.expression_eval import evaluate_when_expr

        for _field in req_detail.fields:
            if _field.when_expr:
                _field.visible = evaluate_when_expr(_field.when_expr, req_detail.item)

    # Evaluate role-based visible conditions (#487)
    if prc.ctx.user_roles is not None:
        from dazzle_ui.utils.condition_eval import evaluate_condition

        _role_ctx = {
            "user_roles": [r.removeprefix("role_") for r in prc.ctx.user_roles],
        }
        for _field in req_detail.fields:
            if _field.visible_condition:
                if not evaluate_condition(_field.visible_condition, {}, _role_ctx):
                    _field.visible = False

        # Hide related tabs whose visible_condition doesn't match (#501)
        for _group in req_detail.related_groups:
            for _tab in _group.tabs:
                if _tab.visible_condition:
                    if not evaluate_condition(_tab.visible_condition, {}, _role_ctx):
                        _tab.visible = False

    # Suppress Edit/Delete buttons when permit rules deny the operation
    # or when the workspace declares read_only for the user's persona (#550, #552).
    if prc.ctx.user_roles is not None:
        _suppress = _should_suppress_mutations(
            prc.deps, prc.surface_name, prc.auth_ctx, prc.ctx.user_roles
        )
        if _suppress:
            req_detail.edit_url = None
            req_detail.delete_url = None
            req_detail.transitions = []
            req_detail.integration_actions = []
        else:
            # Fine-grained: check UPDATE and DELETE individually
            if req_detail.edit_url and not _user_can_mutate(
                prc.deps, prc.surface_name, "update", prc.auth_ctx
            ):
                req_detail.edit_url = None
            if req_detail.delete_url and not _user_can_mutate(
                prc.deps, prc.surface_name, "delete", prc.auth_ctx
            ):
                req_detail.delete_url = None

    # Substitute {id} in the per-request copy only
    if req_detail.edit_url:
        req_detail.edit_url = req_detail.edit_url.replace("{id}", str(prc.path_id))
    if req_detail.delete_url:
        req_detail.delete_url = req_detail.delete_url.replace("{id}", str(prc.path_id))
    for _t in req_detail.transitions:
        if _t.api_url and "{id}" in _t.api_url:
            _t.api_url = _t.api_url.replace("{id}", str(prc.path_id))
    for _a in req_detail.integration_actions:
        if _a.api_url and "{id}" in _a.api_url:
            _a.api_url = _a.api_url.replace("{id}", str(prc.path_id))

    # Fetch related entity data for tabs (hub-and-spoke, #301)
    if req_detail.related_groups and prc.path_id:

        async def _fetch_related_tab(tab: Any, _id: str, _backend: str, _ck: Any) -> None:
            filter_params: dict[str, str] = {
                f"filter[{tab.filter_field}]": _id,
                "page": "1",
                "page_size": "50",
            }
            # Polymorphic FK (#321): add type discriminator filter
            if tab.filter_type_field and tab.filter_type_value:
                filter_params[f"filter[{tab.filter_type_field}]"] = tab.filter_type_value
            params = urllib.parse.urlencode(filter_params)
            url = f"{_backend}{tab.api_endpoint}?{params}"
            try:
                data = await _fetch_url(url, _ck)
                tab.rows = data.get("items", [])
                tab.total = data.get("total", len(tab.rows))
            except Exception:
                logger.warning(
                    "Failed to fetch related %s for %s",
                    tab.entity_name,
                    _id,
                    exc_info=True,
                )

        all_tabs = [tab for _group in req_detail.related_groups for tab in _group.tabs]
        await asyncio.gather(
            *[
                _fetch_related_tab(tab, str(prc.path_id), prc.effective_backend_url, prc.cookies)
                for tab in all_tabs
            ]
        )

    prc.ctx_overrides["detail"] = req_detail


async def _handle_review(prc: _PageRequestContext) -> None:
    """Fetch and prepare review page data for the per-request context."""
    req_review = prc.ctx.review.model_copy(deep=True)

    # Fetch the current item
    req_review.item = await _fetch_json(
        prc.effective_backend_url,
        f"{prc.ctx.review.api_endpoint}/{{id}}",
        prc.path_id,
        prc.cookies,
    )
    if "error" in req_review.item:
        logger.warning(
            "Review page data fetch failed for %s/%s",
            prc.ctx.review.entity_name,
            prc.path_id,
        )

    # Evaluate when_expr for conditional field visibility (#363)
    if req_review.item and "error" not in req_review.item:
        from dazzle_ui.utils.expression_eval import evaluate_when_expr

        for _field in req_review.fields:
            if _field.when_expr:
                _field.visible = evaluate_when_expr(_field.when_expr, req_review.item)

    # Evaluate role-based visible conditions (#487)
    if prc.ctx.user_roles is not None:
        from dazzle_ui.utils.condition_eval import evaluate_condition

        _role_ctx = {
            "user_roles": [r.removeprefix("role_") for r in prc.ctx.user_roles],
        }
        for _field in req_review.fields:
            if _field.visible_condition:
                if not evaluate_condition(_field.visible_condition, {}, _role_ctx):
                    _field.visible = False

    # Substitute {id} in action transition URLs
    for action in req_review.actions:
        if action.transition_url and "{id}" in action.transition_url:
            action.transition_url = action.transition_url.replace("{id}", str(prc.path_id))

    # Fetch the review queue to compute position + navigation
    # Use the same filter from request params (e.g. filter[status]=prepared)
    queue_params: dict[str, str] = {"page_size": "1000"}
    for key, val in prc.request.query_params.items():
        if key.startswith("filter[") and val:
            queue_params[key] = val
    queue_qs = urllib.parse.urlencode(queue_params)
    queue_url = f"{prc.effective_backend_url}{prc.ctx.review.api_endpoint}?{queue_qs}"
    try:
        queue_data = await _fetch_url(queue_url, prc.cookies)
        queue_items = queue_data.get("items", [])
        queue_ids = [str(item.get("id", "")) for item in queue_items]
        req_review.queue_total = len(queue_ids)

        current_id = str(prc.path_id)
        if current_id in queue_ids:
            pos = queue_ids.index(current_id)
            req_review.queue_position = pos
            # Build prev/next URLs preserving filter params
            filter_qs = urllib.parse.urlencode(
                {k: v for k, v in prc.request.query_params.items() if k.startswith("filter[")}
            )
            base = prc.ctx.review.queue_url.rstrip("/")
            suffix = f"?{filter_qs}" if filter_qs else ""
            if pos > 0:
                req_review.prev_url = f"{base}/{queue_ids[pos - 1]}{suffix}"
            if pos < len(queue_ids) - 1:
                req_review.next_url = f"{base}/{queue_ids[pos + 1]}{suffix}"
    except Exception:
        logger.warning(
            "Failed to fetch review queue for %s",
            prc.ctx.review.entity_name,
            exc_info=True,
        )

    prc.ctx_overrides["review"] = req_review


async def _handle_edit_form(prc: _PageRequestContext) -> None:
    """Fetch and prepare edit form data for the per-request context."""
    req_form = prc.ctx.form.model_copy(deep=True)

    # Fetch existing data using the *original* URL template
    form_data = await _fetch_json(
        prc.effective_backend_url, prc.ctx.form.action_url, prc.path_id, prc.cookies
    )
    if "error" not in form_data:
        req_form.initial_values = form_data
    else:
        logger.warning("Failed to fetch initial form values for %s", prc.path_id)
        raise HTTPException(status_code=404, detail="Not found")

    req_form.action_url = req_form.action_url.replace("{id}", str(prc.path_id))
    if req_form.cancel_url:
        req_form.cancel_url = req_form.cancel_url.replace("{id}", str(prc.path_id))

    # Cycle 245 -- apply per-persona PersonaVariant overrides to the
    # per-request form copy. Mirrors the cycle 243 list-surface
    # pattern. Returns True if the persona is read-only, in which
    # case we abort form rendering with a 403.
    if prc.ctx.user_roles and _apply_persona_form_overrides(req_form, prc.ctx.user_roles):
        raise HTTPException(
            status_code=403,
            detail="This surface is read-only for your role",
        )

    prc.ctx_overrides["form"] = req_form


def _handle_create_form(prc: _PageRequestContext) -> None:
    """Prepare create form data for the per-request context."""
    # Cycle 245 -- create forms previously used ctx.form directly
    # with no per-request mutation. Now they need a per-request
    # copy so PersonaVariant hide/read_only overrides can apply.
    req_form = prc.ctx.form.model_copy(deep=True)

    if prc.ctx.user_roles and _apply_persona_form_overrides(req_form, prc.ctx.user_roles):
        raise HTTPException(
            status_code=403,
            detail="This surface is read-only for your role",
        )

    prc.ctx_overrides["form"] = req_form


async def _handle_table(prc: _PageRequestContext) -> None:
    """Fetch and prepare table/list data for the per-request context."""
    # Per-request copy -- the shared ctx.table is compiled once and
    # reused across requests.  Mutations (hidden columns, rows,
    # create_url suppression) must not leak between requests (#587).
    req_table = prc.ctx.table.model_copy(deep=True)

    # Suppress Create button when user lacks CREATE permission or workspace is read_only
    if prc.ctx.user_roles is not None and req_table.create_url:
        if _should_suppress_mutations(
            prc.deps, prc.surface_name, prc.auth_ctx, prc.ctx.user_roles
        ) or not _user_can_mutate(prc.deps, prc.surface_name, "create", prc.auth_ctx):
            req_table.create_url = None

    # Suppress the bulk-action-bar "Delete X items" affordance when the
    # current persona cannot delete this entity. Closes EX-040 (cycle
    # 223 observation: bulk-action bar shown to fieldtest_hub/tester
    # on 4 entity lists despite delete being engineer-only per DSL).
    # The template_compiler sets ``bulk_actions=True`` unconditionally
    # at compile time because there is no request context then; we
    # resolve per-persona here in the per-request copy, mirroring the
    # create_url suppression above. ``_user_can_mutate`` correctly
    # distinguishes "no rules / field-conditioned rules" (allow --
    # record-level) from "role-gate denies mutation" (suppress).
    if prc.ctx.user_roles is not None and req_table.bulk_actions:
        if _should_suppress_mutations(
            prc.deps, prc.surface_name, prc.auth_ctx, prc.ctx.user_roles
        ) or not _user_can_mutate(prc.deps, prc.surface_name, "delete", prc.auth_ctx):
            req_table.bulk_actions = False

    # Apply per-persona PersonaVariant overrides to the per-request
    # table copy. Extracted to a helper in cycle 243 so the resolver
    # logic is testable without a full request context, and so new
    # PersonaVariant fields can be added in one place.
    if prc.ctx.user_roles:
        _apply_persona_overrides(req_table, prc.ctx.user_roles)

    # Evaluate role-based visible_condition on list columns (#585)
    if prc.ctx.user_roles is not None:
        from dazzle_ui.utils.condition_eval import evaluate_condition

        _role_ctx = {
            "user_roles": [r.removeprefix("role_") for r in prc.ctx.user_roles],
        }
        for _col in req_table.columns:
            if _col.visible_condition:
                if not evaluate_condition(_col.visible_condition, {}, _role_ctx):
                    _col.hidden = True

    # Forward all DataTable query params to backend API
    api_params: dict[str, str] = {}
    for key in ("page", "page_size", "sort", "dir", "search"):
        _qval = prc.request.query_params.get(key)
        if _qval:
            api_params[key] = _qval
    for key, val in prc.request.query_params.items():
        if key.startswith("filter[") and val:
            api_params[key] = val
    api_params.setdefault("page", "1")

    # search_first: skip initial fetch until user provides search/filter
    _has_search = bool(api_params.get("search"))
    _has_filter = any(k.startswith("filter[") for k in api_params)
    _skip_fetch = req_table.search_first and not _has_search and not _has_filter

    # Track fetch outcome for typed empty-state selection (#807):
    # - "loading" when the fetch itself errored (user sees the error
    #   stub + a retry affordance rather than a misleading "empty")
    # - "filtered" when the result is empty AND filters/search are
    #   active (offer a clear-filters hint)
    # - "collection" when the result is empty AND no filters are
    #   active (offer the create affordance)
    # The "forbidden" case needs a separate API envelope change (the
    # server must tell us unscoped_total > 0 before we can claim the
    # empty is due to scope) — tracked as a follow-on to #807.
    _fetch_errored = False
    if _skip_fetch:
        req_table.rows = []
        req_table.total = 0
    else:
        query_string = urllib.parse.urlencode(api_params)
        fetch_url = f"{prc.effective_backend_url}{req_table.api_endpoint}?{query_string}"

        try:
            data = await _fetch_url(fetch_url, prc.cookies)
            items = data.get("items", [])
            if items and isinstance(items[0], dict):
                req_table.rows = items
            req_table.total = data.get("total", len(items))
        except Exception:
            logger.warning("Failed to fetch list data from %s", fetch_url, exc_info=True)
            req_table.rows = []
            req_table.total = 0
            _fetch_errored = True

    # Update table context with current sort/filter state from request
    req_table.sort_field = prc.request.query_params.get("sort", req_table.default_sort_field)
    req_table.sort_dir = prc.request.query_params.get("dir", req_table.default_sort_dir)
    req_table.filter_values = {
        k[7:-1]: v
        for k, v in prc.request.query_params.items()
        if k.startswith("filter[") and k.endswith("]") and v
    }

    # Typed empty-state kind selection (#807). The template uses this
    # to pick the right copy + affordance. Only runs when the list is
    # actually empty (rows empty); a populated table doesn't show the
    # empty state at all.
    if not getattr(req_table, "rows", None):
        if _fetch_errored:
            req_table.empty_kind = "loading"
        elif _has_filter or _has_search:
            req_table.empty_kind = "filtered"
        else:
            req_table.empty_kind = "collection"

    prc.ctx_overrides["table"] = req_table


def _render_response(prc: _PageRequestContext) -> Response:
    """Build the final HTML response, handling HTMX fragment/drawer/full modes."""
    from dazzle_ui.runtime.htmx import HtmxDetails
    from dazzle_ui.runtime.template_renderer import render_page

    htmx = HtmxDetails.from_request(prc.request)

    # Boosted navigations: update nav highlighting from the actual URL
    if htmx.current_url:
        from urllib.parse import urlparse

        prc.ctx.current_route = urlparse(htmx.current_url).path

    # Page-level persona purpose override (UX-048 purpose wiring).
    # Mirrors the cycle 240 `empty_message` pattern at the PageContext
    # layer. The compiler populated `ctx.persona_purposes` from DSL
    # `for <persona>: purpose: "..."` blocks; at render time, if the
    # user's persona matches a key, swap `page_purpose`. First
    # matching role wins — matches the persona_variants precedence
    # rule in `_apply_persona_overrides`.
    persona_purposes = getattr(prc.ctx, "persona_purposes", None) or {}
    _user_roles = getattr(prc.ctx, "user_roles", None) or []
    if persona_purposes and _user_roles:
        for _role in _user_roles:
            _normalised = _role.removeprefix("role_")
            if _normalised in persona_purposes:
                prc.ctx_overrides["page_purpose"] = persona_purposes[_normalised]
                break

    # Build per-request context with table/detail/form overrides.
    # All three use deep copies to prevent cross-request mutation
    # of the shared compiled ctx (#291, #587).
    render_ctx = prc.ctx.model_copy(update=prc.ctx_overrides) if prc.ctx_overrides else prc.ctx

    # Fragment targeting: nav links target #main-content directly,
    # so return only the content template (no layout wrapper).
    if htmx.wants_fragment:
        html = render_page(render_ctx, content_only=True)
        headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": render_ctx.page_title})}
        return HTMLResponse(content=html, headers=headers)  # nosemgrep

    # Drawer targeting: workspace action clicks load detail into
    # a slide-over drawer -- return content-only + open trigger.
    if htmx.wants_drawer:
        html = render_page(render_ctx, content_only=True)
        triggers = {
            "dz:drawerOpen": {"url": str(prc.request.url)},
            "dz:titleUpdate": render_ctx.page_title,
        }
        return HTMLResponse(
            content=html,  # nosemgrep
            headers={"HX-Trigger-After-Swap": json.dumps(triggers)},
        )

    # Any HTMX request can receive body-only HTML -- the client
    # extracts <body> content anyway.  History-restore is the one
    # exception: the browser needs a full document for cache misses.
    is_partial = htmx.is_htmx and not htmx.is_history_restore
    html = render_page(render_ctx, partial=is_partial)
    response_headers: dict[str, str] = {}
    # hx-boost strips <head> from the response, so the browser's
    # <title> never updates from server content. Fire the dz:titleUpdate
    # event used by dz-a11y.js on every HTMX-boosted page render so the
    # tab title tracks the destination (#816). History-restore uses a
    # full document, where the <title> element updates natively.
    if is_partial and getattr(render_ctx, "page_title", None):
        response_headers["HX-Trigger-After-Swap"] = json.dumps(
            {"dz:titleUpdate": render_ctx.page_title}
        )
    return HTMLResponse(content=html, headers=response_headers or None)  # nosemgrep


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _page_handler(
    deps: _PageDeps,
    route_path: str,
    ctx: Any,
    view_name: str | None,
    request: Request,
) -> Response:
    """Handle a page route: fetch data, enforce access, render HTML."""
    # Set current route for nav highlighting
    ctx.current_route = route_path

    surface_name = view_name or getattr(ctx, "view_name", None)
    effective_backend_url = _resolve_backend_url(request, deps.backend_url)
    cookies = dict(request.cookies) if request.cookies else None
    path_id = request.path_params.get("id")

    prc = _PageRequestContext(
        deps=deps,
        ctx=ctx,
        request=request,
        auth_ctx=None,
        surface_name=surface_name,
        effective_backend_url=effective_backend_url,
        cookies=cookies,
        path_id=path_id,
    )

    # Phase 1: Auth + access control
    _inject_auth_context(prc)

    denied = _check_surface_access(prc)
    if denied is not None:
        return denied

    denied = _check_entity_cedar_access(prc)
    if denied is not None:
        return denied

    # Phase 2: Per-request data preparation
    # Detail page (path_id + detail context present)
    if path_id and ctx.detail:
        await _handle_detail(prc)

    # Review page (path_id + review context present)
    if path_id and ctx.review:
        await _handle_review(prc)

    # Edit form (path_id + form in edit mode)
    if path_id and ctx.form and ctx.form.mode == "edit":
        await _handle_edit_form(prc)
    elif ctx.form and ctx.form.mode == "create":
        _handle_create_form(prc)

    # Table / list page
    if ctx.table:
        await _handle_table(prc)

    # Phase 3: Render response
    return _render_response(prc)


def _make_page_handler(
    deps: _PageDeps, route_path: str, ctx: Any, view_name: str | None = None
) -> Any:
    """Create a partial-bound handler for a specific page route."""
    return partial(_page_handler, deps, route_path, ctx, view_name)


def _build_workspace_primary_action_candidates(
    workspace: Any,
    *,
    app_prefix: str,
    create_surfaces_by_entity: dict[str, Any],
    list_surfaces_by_entity: dict[str, Any],
) -> list[dict[str, str]]:
    """Collect "New X" primary-action candidates for a workspace header.

    Walks the workspace's regions (single and multi-source), deduplicates
    the referenced entities, and emits one candidate per entity that has a
    CREATE surface. Does NOT filter by persona permission — the caller is
    expected to apply ``_user_can_mutate`` per-request before surfacing the
    button. Closes #827 (workspace dashboards with no create CTA).

    Args:
        workspace: WorkspaceSpec IR node.
        app_prefix: Route prefix (e.g. ``/app``).
        create_surfaces_by_entity: Map entity_ref → CREATE SurfaceSpec.
        list_surfaces_by_entity: Map entity_ref → LIST SurfaceSpec (used
            for a nicer label fallback from the list surface title).

    Returns:
        List of action dicts: ``{entity, surface, label, route}``.
    """
    seen: set[str] = set()
    actions: list[dict[str, str]] = []
    for region in workspace.regions:
        region_sources: list[str] = []
        if region.source:
            region_sources.append(region.source)
        region_sources.extend(getattr(region, "sources", []) or [])
        for src in region_sources:
            if src in seen:
                continue
            seen.add(src)
            create_surface = create_surfaces_by_entity.get(src)
            if not create_surface:
                continue
            entity_slug = src.lower().replace("_", "-")
            list_surface = list_surfaces_by_entity.get(src)
            label_source = (
                getattr(list_surface, "title", "") if list_surface else ""
            ) or src.replace("_", " ").title()
            actions.append(
                {
                    "entity": src,
                    "surface": create_surface.name,
                    "label": f"New {label_source}",
                    "route": f"{app_prefix}/{entity_slug}/create",
                }
            )
    return actions


async def _workspace_handler(
    deps: _PageDeps,
    ws_context: Any,
    ws_route: str,
    ws_allowed_personas: list[str],
    ws_nav_items: list[dict[str, Any]],
    ws_entity_items: list[dict[str, Any]],
    ws_groups: list[dict[str, Any]],
    ws_app_name: str,
    primary_action_candidates: list[dict[str, str]],
    request: Request,
) -> Response:
    """Handle a workspace page route."""
    from dazzle_ui.runtime.template_renderer import render_fragment

    # Inject auth context if available
    # Unauthenticated default: only public workspaces are visible.
    # Entity items (entity surface links) have no access_level, so
    # they are treated as authenticated-only and hidden until login.
    # Exclude routes already covered by nav_groups to avoid duplication (#661).
    _grouped_routes = {child["route"] for g in ws_groups for child in g.get("children", [])}
    visible_nav = [
        {"label": item["label"], "route": item["route"]}
        for item in ws_nav_items + ws_entity_items
        if item["route"] not in _grouped_routes and item.get("access_level") == "public"
    ]
    is_authenticated = False
    user_email = ""
    user_name = ""
    user_roles: list[str] = []

    user_preferences: dict[str, str] = {}
    auth_ctx = None

    if deps.get_auth_context is not None:
        try:
            auth_ctx = deps.get_auth_context(request)
            if auth_ctx and auth_ctx.is_authenticated:
                is_authenticated = True
                user_email = auth_ctx.user.email if auth_ctx.user else ""
                user_name = auth_ctx.user.username if auth_ctx.user else ""
                user_roles = list(getattr(auth_ctx.user, "roles", None) or [])
                user_preferences = auth_ctx.preferences or {}
                # Filter nav by persona access.
                # Roles use "role_" prefix; persona IDs don't.
                normalized_roles = [r.removeprefix("role_") for r in user_roles]
                # Exclude entity routes that are already in nav_groups
                grouped_routes = {
                    child["route"] for g in ws_groups for child in g.get("children", [])
                }
                visible_nav = [
                    {"label": item["label"], "route": item["route"]}
                    for item in ws_nav_items + ws_entity_items
                    if item["route"] not in grouped_routes
                    and (
                        not item.get("allow_personas")
                        or any(r in item["allow_personas"] for r in normalized_roles)
                    )
                ]
        except Exception:
            logger.debug("Failed to resolve auth for workspace nav", exc_info=True)

    # Enforce workspace persona access control (superusers bypass)
    is_superuser = (
        deps.get_auth_context is not None
        and auth_ctx is not None
        and auth_ctx.user is not None
        and auth_ctx.user.is_superuser
    )
    if ws_allowed_personas and not is_superuser:
        normalized = [r.removeprefix("role_") for r in user_roles]
        if not normalized or not any(r in ws_allowed_personas for r in normalized):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access this workspace.",
            )

    from dazzle_ui.runtime.htmx import HtmxDetails

    htmx = HtmxDetails.from_request(request)

    effective_route = ws_route
    if htmx.current_url:
        from urllib.parse import urlparse

        effective_route = urlparse(htmx.current_url).path

    # Apply per-user workspace layout preferences (order, visibility, widths)
    from dazzle_ui.runtime.workspace_renderer import apply_layout_preferences, build_catalog

    render_ws_ctx = apply_layout_preferences(ws_context, user_preferences)
    catalog = build_catalog(ws_context)

    # Build v2 card list for the template data island
    cards_for_json = []
    for i, r in enumerate(render_ws_ctx.regions):
        cards_for_json.append(
            {
                "id": f"card-{i}",
                "region": r.name,
                "title": r.title or r.name.replace("_", " ").title(),
                "col_span": r.col_span,
                "row_order": i,
            }
        )

    layout_json = json.dumps(
        {
            "version": 2,
            "cards": cards_for_json,
            "catalog": catalog,
            "workspace_name": render_ws_ctx.name,
        }
    )

    ws_title = render_ws_ctx.title or render_ws_ctx.name.replace("_", " ").title()

    # Filter primary-action candidates by per-request create permission (#827).
    # The candidate list was precomputed at registration from workspace
    # regions + create-surface presence; here we check that the authenticated
    # user can actually create each entity before surfacing the button. When
    # no auth is configured, ``_user_can_mutate`` returns True and all
    # candidates pass — matching the existing permissive fallback.
    primary_actions: list[dict[str, str]] = []
    for cand in primary_action_candidates:
        surface_name = cand.get("surface", "")
        if _user_can_mutate(deps, surface_name, "create", auth_ctx):
            primary_actions.append(
                {
                    "label": cand["label"],
                    "route": cand["route"],
                }
            )

    # Fragment targeting: return only the workspace content
    if htmx.wants_fragment:
        html = render_fragment(
            "workspace/_content.html",
            workspace=render_ws_ctx,
            user_preferences=user_preferences,
            layout_json=layout_json,
            primary_actions=primary_actions,
        )
        headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": ws_title})}
        return HTMLResponse(content=html, headers=headers)  # nosemgrep

    html = render_fragment(
        "workspace/workspace.html",
        workspace=render_ws_ctx,
        nav_items=visible_nav,
        nav_groups=ws_groups,
        app_name=ws_app_name,
        page_title=ws_title,
        current_route=effective_route,
        is_authenticated=is_authenticated,
        user_email=user_email,
        user_name=user_name,
        user_preferences=user_preferences,
        layout_json=layout_json,
        primary_actions=primary_actions,
        _htmx_partial=htmx.is_htmx and not htmx.is_history_restore,
    )
    return HTMLResponse(content=html)  # nosemgrep


async def _root_redirect(
    deps: _PageDeps,
    persona_ws_routes: dict[str, str],
    fallback_ws_route: str,
    request: Request,
) -> Response:
    """Redirect app root to the appropriate workspace for the user's persona."""
    if deps.get_auth_context is not None:
        try:
            auth_ctx = deps.get_auth_context(request)
            if auth_ctx and auth_ctx.is_authenticated and auth_ctx.roles:
                for role in auth_ctx.roles:
                    route = persona_ws_routes.get(role)
                    if route:
                        return RedirectResponse(url=route, status_code=302)
        except Exception:
            logger.warning(
                "Failed to resolve user persona for workspace redirect",
                exc_info=True,
            )
    return RedirectResponse(url=fallback_ws_route, status_code=302)


# =============================================================================
# Factory
# =============================================================================


def create_page_routes(
    appspec: ir.AppSpec,
    backend_url: str | None = None,
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
    *,
    evaluate_permission_fn: Callable[..., Any] | None = None,
    convert_entity_fn: Callable[..., Any] | None = None,
    inject_display_names_fn: Callable[..., Any] | None = None,
) -> APIRouter:
    """
    Create FastAPI page routes from an AppSpec.

    Each surface becomes a page route that renders server-side HTML.

    Args:
        appspec: Complete application specification.
        backend_url: URL of the backend API for data fetching.
        theme_css: Pre-compiled theme CSS to inject.
        get_auth_context: Optional callable(request) -> AuthContext for user info.
        app_prefix: URL prefix for page routes (e.g. "/app").
            Callers mounting under a prefix MUST pass this explicitly
            so that nav items, href attributes, and hx-get URLs are
            generated with the correct prefix.

    Returns:
        FastAPI router with page routes.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed")

    if backend_url is None:
        backend_url = resolve_api_url()

    from dazzle_ui.converters.template_compiler import compile_appspec_to_templates
    from dazzle_ui.runtime.surface_access import SurfaceAccessConfig

    router = APIRouter()

    # Compile all surfaces to template contexts
    page_contexts = compile_appspec_to_templates(appspec, app_prefix=app_prefix)

    # Build route -> access config mapping from surface specs
    access_configs: dict[str, SurfaceAccessConfig] = {}
    for surface in appspec.surfaces:
        if surface.access is not None:
            access_configs[surface.name] = SurfaceAccessConfig.from_spec(surface.access)

    # Build entity_name -> EntityAccessSpec mapping for Cedar policy evaluation (#527).
    entity_cedar_specs: dict[str, Any] = {}
    if convert_entity_fn is not None:
        for _entity in appspec.domain.entities:
            if _entity.access:
                _converted = convert_entity_fn(_entity)
                if _converted.access is not None:
                    entity_cedar_specs[_entity.name] = _converted.access

    # Build surface_name -> entity_name, surface_name -> mode, and
    # surface_name -> workspace_name mappings for access control.
    surface_entity: dict[str, str] = {}
    surface_mode: dict[str, str] = {}
    surface_workspace: dict[str, str] = {}
    for _surface in appspec.surfaces:
        if _surface.entity_ref:
            surface_entity[_surface.name] = _surface.entity_ref
        surface_mode[_surface.name] = _surface.mode.value if _surface.mode else "list"
    # Map surfaces to their parent workspace via workspace regions
    for _ws in appspec.workspaces:
        for _region in getattr(_ws, "regions", []) or []:
            _source = getattr(_region, "source", None)
            if _source:
                # source can be a surface name or entity name
                for _surface in appspec.surfaces:
                    if _surface.name == _source or _surface.entity_ref == _source:
                        surface_workspace[_surface.name] = _ws.name

    # Inject integration manual trigger actions into detail contexts
    _inject_integration_actions(appspec, page_contexts)

    # Inject theme CSS into all contexts
    for ctx in page_contexts.values():
        ctx.theme_css = theme_css

    # Build route → entity name mapping for sidebar nav filtering (#583).
    # Entity list routes use the pattern /{app_prefix}/{entity-slug}.
    route_entity: dict[str, str] = {}
    for _entity in appspec.domain.entities:
        _slug = _entity.name.lower().replace("_", "-")
        route_entity[f"{app_prefix}/{_slug}"] = _entity.name

    deps = _PageDeps(
        appspec=appspec,
        backend_url=backend_url,
        theme_css=theme_css,
        get_auth_context=get_auth_context,
        app_prefix=app_prefix,
        page_contexts=page_contexts,
        access_configs=access_configs,
        entity_cedar_specs=entity_cedar_specs,
        surface_entity=surface_entity,
        surface_mode=surface_mode,
        surface_workspace=surface_workspace,
        route_entity=route_entity,
        evaluate_permission=evaluate_permission_fn,
        inject_display_names=inject_display_names_fn,
    )

    # Register routes — sort by specificity so FastAPI matches the most-specific
    # route first.  Rules: (1) more segments first, (2) static paths before
    # dynamic ones at the same depth (e.g. /item/create before /item/{id}).
    def _route_sort_key(kv: tuple[str, Any]) -> tuple[int, int]:
        path = kv[0]
        return (-path.count("/"), 0 if "{" not in path else 1)

    sorted_routes = sorted(page_contexts.items(), key=_route_sort_key)
    for route_path, ctx in sorted_routes:
        # Route paths include app_prefix for URL generation (nav highlighting,
        # cross-references).  Strip it for registration since the router is
        # mounted with the same prefix — otherwise routes get double-prefixed.
        reg_path = route_path
        if app_prefix and reg_path.startswith(app_prefix):
            reg_path = reg_path[len(app_prefix) :] or "/"

        handler = _make_page_handler(
            deps, route_path, ctx, view_name=getattr(ctx, "view_name", None)
        )
        router.get(reg_path, response_class=HTMLResponse)(handler)

    # #815: users type plural URLs (/app/tickets, /app/contacts) even when
    # Dazzle's canonical slug is singular (/app/ticket, /app/contact).
    # Register a 301 redirect from the plural form to the singular canonical
    # path for each entity so external links, bookmarks, and typed-URL
    # navigation all land somewhere sensible. Workspaces live under
    # /app/workspaces/<name> which never collides with /app/<plural>, so no
    # guard is needed beyond skipping entities whose singular and plural
    # slugs are identical (rare — e.g. "Series").
    from dazzle.core.strings import to_api_plural as _to_api_plural

    _registered_reg_paths = {
        (app_prefix and route_path[len(app_prefix) :]) or route_path
        for route_path, _ in sorted_routes
    }
    for _entity in appspec.domain.entities:
        singular_slug = _entity.name.lower().replace("_", "-")
        plural_slug = _to_api_plural(_entity.name).replace("_", "-")
        if singular_slug == plural_slug:
            continue
        plural_reg_path = f"/{plural_slug}"
        if plural_reg_path in _registered_reg_paths:
            # Something real already lives here — don't shadow it.
            continue

        redirect_target = f"{app_prefix}/{singular_slug}"

        def _plural_redirect(target: str = redirect_target) -> RedirectResponse:
            return RedirectResponse(url=target, status_code=301)

        router.get(plural_reg_path)(_plural_redirect)

    # Register workspace routes — workspaces use their own template, not the
    # surface page template, so they get separate handlers.
    workspaces = getattr(appspec, "workspaces", []) or []
    if workspaces:
        # Build nav items for workspace pages: workspace links + entity surface links.
        # Entity surfaces are derived from workspace regions' source entities.
        # Delegate workspace-access resolution to the shared helper so sidebar
        # nav visibility matches the enforcement path AND template_compiler's
        # nav_by_persona. EX-028 (cycle 221) + cycle 226 root-cause: the v0.55.34
        # #775 fix unified template_compiler.py and _workspace_handler access
        # enforcement via workspace_allowed_personas, but this second
        # ws_nav_items builder was never migrated. It pulled allow_personas
        # directly from raw ws_access, which returned [] for workspaces with no
        # explicit DSL access declaration — and the downstream filter at
        # line 860 treats an empty list as "no restriction", so implicitly-gated
        # workspaces leaked into every persona's sidebar. Calling the helper
        # here restores single-source-of-truth.
        from dazzle_ui.converters.workspace_converter import workspace_allowed_personas
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        _personas_list = list(getattr(appspec, "personas", []) or [])
        ws_nav_items: list[dict[str, Any]] = []
        for ws in workspaces:
            ws_access = getattr(ws, "access", None)
            _allowed = workspace_allowed_personas(ws, _personas_list)
            # None means "no filter" (visible to every authenticated user);
            # preserve the existing convention that empty list in the item
            # dict means "no restriction" by flattening None → [].
            _allow_for_item = [] if _allowed is None else list(_allowed)
            ws_nav_items.append(
                {
                    "label": ws.title or ws.name.replace("_", " ").title(),
                    "route": f"{app_prefix}/workspaces/{ws.name}",
                    "allow_personas": _allow_for_item,
                    "access_level": ws_access.level if ws_access else "authenticated",
                }
            )

        # Add entity surface links from each workspace's regions
        surfaces = getattr(appspec, "surfaces", []) or []
        _list_surfaces_by_entity: dict[str, Any] = {}
        _create_surfaces_by_entity: dict[str, Any] = {}
        for surface in surfaces:
            if surface.mode.value == "list" and surface.entity_ref:
                _list_surfaces_by_entity.setdefault(surface.entity_ref, surface)
            elif surface.mode.value == "create" and surface.entity_ref:
                _create_surfaces_by_entity.setdefault(surface.entity_ref, surface)

        # Collect entities claimed by nav_groups per workspace (for #430 dedup)
        ws_grouped_entities: dict[str, set[str]] = {}
        for ws in workspaces:
            grouped: set[str] = set()
            for ng in getattr(ws, "nav_groups", []) or []:
                for item in ng.items:
                    grouped.add(item.entity)
            ws_grouped_entities[ws.name] = grouped

        # Per-workspace nav: workspace links + entity surfaces from regions
        ws_entity_nav: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            entity_items: list[dict[str, Any]] = []
            seen_entities: set[str] = set()
            grouped = ws_grouped_entities.get(ws.name, set())
            for region in ws.regions:
                # Collect all source entities (single + multi-source)
                region_sources: list[str] = []
                if region.source:
                    region_sources.append(region.source)
                region_sources.extend(getattr(region, "sources", []) or [])
                for src in region_sources:
                    if src not in seen_entities and src not in grouped:
                        seen_entities.add(src)
                        list_surface = _list_surfaces_by_entity.get(src)
                        if list_surface:
                            entity_slug = src.lower().replace("_", "-")
                            entity_items.append(
                                {
                                    "label": list_surface.title or src.replace("_", " ").title(),
                                    "route": f"{app_prefix}/{entity_slug}",
                                    "allow_personas": [],
                                }
                            )
            ws_entity_nav[ws.name] = entity_items

        # Per-workspace primary actions: "Create X" buttons derived from
        # regions that reference an entity with a CREATE surface. Closes #827
        # — prior behaviour rendered workspace header with title only, leaving
        # users who landed on a Task Board dashboard with no way to create a
        # Task from that view. Filter by persona-create permission happens
        # per-request in ``_workspace_handler``; this build step just collects
        # the candidate set from the workspace's region sources.
        ws_primary_actions: dict[str, list[dict[str, str]]] = {
            ws.name: _build_workspace_primary_action_candidates(
                ws,
                app_prefix=app_prefix,
                create_surfaces_by_entity=_create_surfaces_by_entity,
                list_surfaces_by_entity=_list_surfaces_by_entity,
            )
            for ws in workspaces
        }

        ws_app_name = appspec.title or appspec.name.replace("_", " ").title()

        # Build nav groups per workspace from nav_group declarations (v0.38.0)
        ws_nav_group_map: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            groups: list[dict[str, Any]] = []
            for ng in getattr(ws, "nav_groups", []) or []:
                groups.append(
                    {
                        "label": ng.label,
                        "icon": ng.icon,
                        "collapsed": ng.collapsed,
                        "children": [
                            {
                                "label": (
                                    _list_surfaces_by_entity[item.entity].title
                                    if item.entity in _list_surfaces_by_entity
                                    and _list_surfaces_by_entity[item.entity].title
                                    else item.entity.replace("_", " ").title()
                                ),
                                "route": f"{app_prefix}/{item.entity.lower().replace('_', '-')}",
                                "icon": item.icon,
                            }
                            for item in ng.items
                        ],
                    }
                )
            ws_nav_group_map[ws.name] = groups

        # workspace_allowed_personas is already imported above (ws_nav_items
        # build). Both call sites now consult the same helper, so sidebar,
        # enforcement, and template_compiler nav_by_persona all agree.

        for workspace in workspaces:
            ws_ctx = build_workspace_context(workspace, appspec)
            _ws_route = f"{app_prefix}/workspaces/{workspace.name}"
            _allowed = workspace_allowed_personas(workspace, list(appspec.personas))
            # The _workspace_handler interprets an empty _ws_allowed list as
            # "no restriction" (backward compat), so we flatten None and
            # non-empty lists into either "empty list = no restriction" or
            # "non-empty list = restrict to these personas".
            _ws_allowed = [] if _allowed is None else list(_allowed)
            _ws_entity_items = ws_entity_nav.get(workspace.name, [])
            _ws_nav_groups = ws_nav_group_map.get(workspace.name, [])
            _ws_primary = ws_primary_actions.get(workspace.name, [])

            handler = partial(
                _workspace_handler,
                deps,
                ws_ctx,
                _ws_route,
                _ws_allowed,
                ws_nav_items,
                _ws_entity_items,
                _ws_nav_groups,
                ws_app_name,
                _ws_primary,
            )
            router.get(f"/workspaces/{workspace.name}", response_class=HTMLResponse)(handler)

        # When workspaces exist and "/" is not already registered as a page,
        # add a redirect so users landing at the app root reach a real page.
        #
        # Delegate per-persona resolution to _resolve_persona_route — the
        # same helper the ux-cycle uses for post-login redirect computation
        # — so personas without an explicit default_workspace still get a
        # sensible target (first workspace with access.allow_personas match,
        # then first AUTHENTICATED workspace, then first workspace as a
        # last resort). Before cycle 227 this block only populated entries
        # for personas that declared `default_workspace` in the DSL;
        # everyone else fell through to a raw `workspaces[0]` fallback,
        # which for most apps is the privileged/admin workspace — causing
        # non-admin personas to hit 403 on login and the recovery path
        # (EX-035 dead-end loop). Cycle 225 fixed the upstream parser bug;
        # this cycle fixes the downstream structural fragility.
        if "/" not in page_contexts:
            from dazzle_ui.converters.workspace_converter import (
                resolve_persona_workspace_route,
            )

            # Build persona -> workspace route mapping for EVERY persona
            # using the workspace-only resolver. It always returns a
            # /app/workspaces/<name> route when the app has at least one
            # workspace, so every declared persona gets a deterministic
            # target. We deliberately use the workspace-only variant
            # rather than compute_persona_default_routes: the latter
            # honours persona.default_route (e.g. "/admin") which may be
            # DSL-declared but not actually registered as a FastAPI
            # route — hitting /app as admin would then redirect to a
            # 404. The workspace-only resolver stays inside the
            # guaranteed-registered /app/workspaces/<name> namespace.
            _persona_ws_routes: dict[str, str] = {}
            for _persona in appspec.personas:
                _route = resolve_persona_workspace_route(_persona, list(workspaces))
                if _route:
                    _persona_ws_routes[_persona.id] = _route

            # Fallback for users with no persona match at all (e.g. a
            # role-less admin-bypass route). Preserves the existing
            # post-resolution safety net — unchanged from the prior
            # implementation so there is still a redirect target even if
            # the auth context has no known role.
            _fallback_ws_route = f"{app_prefix}/workspaces/{workspaces[0].name}"

            router.get("/", response_class=HTMLResponse)(
                partial(_root_redirect, deps, _persona_ws_routes, _fallback_ws_route)
            )

    return router
