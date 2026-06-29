"""
Page routes for server-rendered Dazzle pages.

Entry point: src/dazzle/http/runtime/app_factory.py:create_app() mounts
this router alongside site_routes.py and experience_routes.py.

Creates FastAPI routes that render full HTML pages using Jinja2 templates.
Each workspace+surface combination gets a GET route that:
1. Calls the template compiler to get a PageContext
2. Fetches data from the backend service
3. Renders the Jinja2 template
4. Returns an HTMLResponse
"""

import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from dazzle.core import ir
from dazzle.core.access import AccessOperationKind, AccessRuntimeContext
from dazzle.core.condition_eval import evaluate_condition
from dazzle.core.ir import SurfaceMode
from dazzle.core.ir.integrations import MappingTriggerType
from dazzle.core.strings import to_api_plural
from dazzle.page import app_paths
from dazzle.page.converters.nav_builder import (
    NavGroup,
    NavLink,
    NavModel,
    build_all_persona_navs,
    build_anon_nav,
)
from dazzle.rbac.matrix import generate_access_matrix
from dazzle.render.access_evaluator import evaluate_permission
from dazzle.render.access_messages import _forbidden_detail
from dazzle.render.display_names import _inject_display_names

logger = logging.getLogger(__name__)

# =============================================================================
# Helpers (module-level, no closure state)
# =============================================================================


def _collect_request_params(request: Any) -> dict[str, str]:
    """#1129: merge ``request.path_params`` + ``request.query_params``
    into a flat ``{name: str}`` dict for ``CustomRenderCtx.params``.

    Path params win on key collision because they're more specific
    (the route declared them; the query string is opportunistic).
    Both attributes are documented stable on
    ``starlette.requests.Request``; ``hasattr`` guards so test
    fixtures that pass a bare ``MagicMock`` (no attribute set)
    don't crash here. We accept any mapping shape — production
    callers pass starlette's ``QueryParams`` / ``ImmutableMultiDict``,
    tests pass plain dicts — and require ``.items()``. Anything
    that has the attribute but isn't iterable is a contract
    violation the caller will see on the next access.
    """
    out: dict[str, str] = {}
    qp = getattr(request, "query_params", None)
    if qp is not None and hasattr(qp, "items"):
        out.update({str(k): str(v) for k, v in qp.items()})
    pp = getattr(request, "path_params", None)
    if pp is not None and hasattr(pp, "items"):
        out.update({str(k): str(v) for k, v in pp.items()})
    return out


async def _resolve_auth_context(get_auth_context: Callable[..., Any] | None, request: Any) -> Any:
    """Call ``get_auth_context`` and await the result if it's a coroutine (#1128).

    Page routes are FastAPI handlers (always async), but the
    ``get_auth_context`` seam was originally declared sync-only.
    Projects on async auth stacks (async DB session, async permission
    lookup, FastAPI's idiomatic ``Depends``-style flow) hit silent
    ``AttributeError: 'coroutine' object has no attribute
    'is_authenticated'`` on every page load because the returned
    coroutine was assigned to ``auth_ctx`` and treated as the
    resolved value.

    This helper accepts either signature: sync callables return
    their value unchanged; async callables are awaited.
    """
    if get_auth_context is None:
        return None
    result = get_auth_context(request)
    if inspect.iscoroutine(result):
        result = await result
    # #1428: bind the per-request RLS GUCs (dazzle.tenant_id / dazzle.user_<attr>)
    # on the page in-process path, exactly as the REST auth dependency does
    # (dependencies.get_optional_user → _bind_rls_tenant_id). #1422 removed the
    # page→REST self-fetch hop that previously ran that dependency; without this
    # bind, a shared_schema/RLS app's leased connection denies every row to
    # in-process page reads/lists/mutations → RecordNotFound → 404. The helper is
    # guarded on is_authenticated and fail-closed (an unresolvable attr stays
    # unbound, so the fence denies). Idempotent; per-task contextvars die with the
    # request task.
    if result is not None:
        from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id

        _bind_rls_tenant_id(result)
    return result


def _inject_integration_actions(appspec: ir.AppSpec, page_contexts: dict[str, Any]) -> None:
    """Populate integration_actions on detail contexts from appspec integrations."""
    from dazzle.render.context import IntegrationActionContext

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
    deps: "_PageRouterConfig",
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
    deps: "_PageRouterConfig",
    surface_name: str | None,
    operation: str,
    auth_ctx: Any,
) -> bool:
    """Check if user can perform a mutation (create/update/delete) on the entity."""
    if not surface_name or not deps.entity_cedar_specs or auth_ctx is None:
        return True  # No access control configured

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
    _decision = evaluate_permission(
        _cedar_spec,
        _op,
        None,
        _runtime_ctx,
        entity_name=_entity_name or "",
    )
    return bool(_decision.allowed)


def _suppress_inaccessible_cta(step: Any, prc: "_PageRequestContext", appspec: Any) -> Any:
    """Strip a guide step's CTA when it points at a create/edit surface the
    current persona can't mutate (#1292 runtime backstop).

    Returns the step unchanged when the CTA is fine (read-only target,
    unknown surface, or the persona can mutate). When suppressed, returns a
    copy with ``cta_target``/``cta_label`` cleared so the step still renders
    (and completes) but offers no dead navigation. Defence in depth behind
    the validate-time guide-CTA access check in ``guide_concordance``.
    """
    cta = getattr(step, "cta_target", None)
    if not cta or not str(cta).startswith("surface."):
        return step
    surface_name = cta.removeprefix("surface.").split(".")[0]
    surface = next((s for s in appspec.surfaces if s.name == surface_name), None)
    if surface is None:
        return step
    mode_raw = getattr(surface, "mode", None)
    mode_str = str(getattr(mode_raw, "value", mode_raw) or "").lower()
    if "create" in mode_str:
        operation = "create"
    elif "edit" in mode_str or "update" in mode_str:
        operation = "update"
    else:
        return step  # read / list / detail CTA — not gated
    if _user_can_mutate(prc.deps, surface_name, operation, prc.auth_ctx):
        return step
    logger.info(
        "onboarding.inject:cta-suppressed step=%s cta_target=%s op=%s "
        "(persona cannot %s the target entity — #1292 backstop)",
        getattr(step, "name", "?"),
        surface_name,
        operation,
        operation,
    )
    return step.model_copy(update={"cta_target": None, "cta_label": None})


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
    deps: "_PageRouterConfig",
    auth_ctx: Any,
) -> list[Any]:
    """Remove nav items whose entity denies the user's role for LIST (#583)."""
    if auth_ctx is None or not auth_ctx.is_authenticated:
        return nav_items

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
        _decision = evaluate_permission(
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
class _PageRouterConfig:
    """Per-router configuration built once at startup, threaded through
    every page handler. The cross-layer callable-injection fields that
    historically lived here (`evaluate_permission`, `inject_display_names`,
    #679 workaround) were removed in #1094 — those helpers now live in
    `dazzle.render` and are imported directly at the call site.
    """

    appspec: ir.AppSpec
    theme_css: str
    get_auth_context: Callable[..., Any] | None
    app_prefix: str
    page_contexts: dict[str, Any] = field(default_factory=dict)
    access_configs: dict[str, Any] = field(default_factory=dict)
    entity_cedar_specs: dict[str, Any] = field(default_factory=dict)
    # #1422: the per-entity scope/permit inputs the page layer needs to read
    # entity data IN-PROCESS via `access.gated` instead of self-fetching its own
    # REST endpoint. `entity_services` are the runtime CRUDService instances
    # (threaded from the builder); `entity_fk_graph`/`entity_admin_personas` are
    # derived from the appspec (same values the REST RouteGenerator receives).
    entity_services: dict[str, Any] = field(default_factory=dict)
    entity_auto_includes: dict[str, Any] = field(default_factory=dict)
    entity_fk_graph: Any = None
    entity_admin_personas: list[str] = field(default_factory=list)
    # Legacy pre-Cedar visibility specs (`entity.metadata["access"]`) the REST list
    # route applies via build_visibility_filter — threaded so the in-process page
    # list (gated_list) applies the same. Empty for Cedar-only apps. (#1422)
    entity_access_specs: dict[str, Any] = field(default_factory=dict)
    surface_entity: dict[str, str] = field(default_factory=dict)
    surface_mode: dict[str, str] = field(default_factory=dict)
    surface_workspace: dict[str, str] = field(default_factory=dict)
    # Route path → entity name — for filtering sidebar nav items by entity permit (#583)
    route_entity: dict[str, str] = field(default_factory=dict)
    # #1324 slice 3b: precomputed per-persona navs (keyed by persona id) +
    # the anon-visitor nav, built once at boot from the RBAC matrix. Every
    # page render sets `ctx.nav_model` from these so the sidebar can no
    # longer drift between the workspace-page and entity-page paths.
    persona_navs: dict[str, NavModel] = field(default_factory=dict)
    anon_nav: NavModel | None = None


# =============================================================================
# Per-request context for _page_handler helpers
# =============================================================================


@dataclass
class _PageRequestContext:
    """Shared state built once per request, passed to each handler helper."""

    deps: _PageRouterConfig
    ctx: Any
    request: Any  # FastAPI Request
    auth_ctx: Any  # AuthContext | None
    surface_name: str | None
    cookies: dict[str, str] | None
    path_id: Any  # str | None
    ctx_overrides: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# _page_handler helper functions
# =============================================================================


def _reconcile_nav_route(appspec: ir.AppSpec, app_prefix: str, link: NavLink) -> str:
    """#1324 slice 3b: map a NavLink's placeholder route to the real runtime route.

    ``nav_builder`` emits route placeholders (``/workspaces/<name>`` and
    ``/list/<Entity>``) deliberately, deferring app_prefix/slug reconciliation
    to the renderer (see ``nav_builder._route_for``). The runtime registers
    workspace pages at ``<app_prefix>/workspaces/<name>`` and entity-list pages
    at ``<app_prefix>/<entity-slug>`` (slug = ``name.lower().replace("_","-")``,
    matching ``route_entity`` construction below). Reconcile by the link's
    ``entity`` target so active-state highlighting (current_route == href) works
    and the hrefs point at live routes. Falls back to the placeholder route if
    the target can't be classified."""
    target = link.entity or ""
    if target:
        for ws in getattr(appspec, "workspaces", []) or []:
            if ws.name == target:
                return f"{app_prefix}/workspaces/{ws.name}"
        return app_paths.list_path(app_prefix, app_paths.entity_slug(target))
    return link.route


def _reconcile_nav_model(appspec: ir.AppSpec, app_prefix: str, model: NavModel) -> NavModel:
    """Rebuild a NavModel with runtime-reconciled link routes (#1324 slice 3b)."""
    new_groups = tuple(
        NavGroup(
            label=g.label,
            icon=g.icon,
            collapsed=g.collapsed,
            links=tuple(
                NavLink(
                    label=link.label,
                    route=_reconcile_nav_route(appspec, app_prefix, link),
                    icon=link.icon,
                    entity=link.entity,
                    # #1324 FR-4: preserve the render-time visibility condition
                    # through reconciliation. Dropping it here would silently
                    # disable conditional nav (the FR-4 analogue of the slice-3b
                    # route bug — see _resolve_nav_model docstring).
                    when=link.when,
                )
                for link in g.links
            ),
            when=g.when,
        )
        for g in model.groups
    )
    return NavModel(groups=new_groups, auto_discovered=model.auto_discovered)


def _resolve_nav_model(
    deps: _PageRouterConfig, roles: list[str] | None, *, authenticated: bool
) -> NavModel | None:
    """#1324: pick the precomputed NavModel for the current request.

    The fallback semantics distinguish unauthenticated from authenticated-but-
    no-persona-match (the #1324 slice-3b regression fixed here):

    - **Unauthenticated** (no session) → the anon nav. This is the only case
      where anon reach is correct; an unauthenticated request must never see
      the full nav.
    - **Authenticated, a role matches a persona** → that persona's NavModel.
    - **Authenticated, NO role matches a persona** → ``None``. The caller
      leaves the legacy ``nav_items``/``nav_groups`` path to build the sidebar.
      This is the critical case: ``admin``/``super_admin`` are role NAMES, not
      entries in ``appspec.personas``, so ``persona_navs`` has no key for them.
      Slice 3b wrongly returned the anon nav here, collapsing the admin platform
      workspace's curated ``nav_groups`` to the anonymous-visitor nav. Falling
      through to the legacy path renders the workspace's own curated nav.
    - **anon nav not precomputed** (older config) → ``None`` (legacy path).
    """
    for role in roles or []:
        nav = deps.persona_navs.get(role.removeprefix("role_"))
        if nav is not None:
            return nav
    if not authenticated:
        # Genuinely-unauthenticated request: the anon-safe subset (never the
        # full nav). Returns None when no anon nav was precomputed.
        return deps.anon_nav
    # Authenticated but no role matched a persona (e.g. admin/super_admin):
    # fall through to the legacy curated nav rather than the anon subset.
    return None


@dataclass(frozen=True)
class _ChromeAssets:
    """The app-shell asset tuples `dispatch_render_page` needs, resolved from
    `request.app.state` (#1392 item 2 — shared by page handlers + the route-override
    response-contract chrome-wrap so an override's chrome === a page's chrome)."""

    css_links: tuple[str, ...]
    js_scripts: tuple[str, ...]
    theme: str | None
    font_preconnect: tuple[str, ...]
    favicon: str


def _resolve_chrome_assets(app_state: Any) -> _ChromeAssets:
    """Resolve the chrome asset tuples from `app.state` (verbatim extraction of the
    block previously inline in the page handlers)."""
    return _ChromeAssets(
        css_links=tuple(
            getattr(app_state, "fragment_chrome_css_links", None)
            or ("/static/dist/dazzle.min.css",)
        ),
        js_scripts=tuple(
            getattr(app_state, "fragment_chrome_js_scripts", None)
            or ("/static/dist/dazzle.min.js",)
        ),
        theme=getattr(app_state, "fragment_chrome_theme", None),
        font_preconnect=tuple(getattr(app_state, "fragment_chrome_font_preconnect", None) or ()),
        favicon=getattr(app_state, "fragment_chrome_favicon", "/static/assets/dazzle-favicon.svg"),
    )


async def build_app_page_context(
    request: Any, *, deps: _PageRouterConfig | None = None, current_route: str
) -> tuple[Any, _ChromeAssets]:
    """Build a reusable app-shell `PageContext` + chrome assets for an arbitrary route
    (#1392 item 2). Used by the route-override response-contract wrapper to chrome a
    `# dazzle:returns fragment` handler with the same shell + assets a page gets.

    Resolves auth/persona from the request (mirroring `_page_handler`), picks the
    precomputed `NavModel` via `_resolve_nav_model`, and stamps `current_route`.
    `nav_items`/`nav_groups` are left empty — the modern sidebar is driven by `nav_model`.

    When `deps is None` (the route-override path, which has no page-router deps), the
    appspec is read from `request.app.state.appspec` and `nav_model` is None — the
    override renders in the app **shell frame** (topbar + chrome), the item-2 guarantee.
    A fully persona-populated sidebar for overrides (needs the precomputed navs threaded
    from `create_page_routes`) is a deliberate v1 follow-on.
    """
    from dazzle.render.context import PageContext

    is_authenticated = False
    user_roles: list[str] = []
    get_auth_context = deps.get_auth_context if deps is not None else None
    if get_auth_context is not None:
        auth_ctx = await _resolve_auth_context(get_auth_context, request)
        if auth_ctx and auth_ctx.is_authenticated:
            is_authenticated = True
            user_roles = list(getattr(auth_ctx.user, "roles", None) or [])

    nav_model = (
        _resolve_nav_model(deps, user_roles, authenticated=is_authenticated)
        if deps is not None and get_auth_context is not None
        else None
    )
    appspec = (
        deps.appspec
        if deps is not None
        else getattr(getattr(getattr(request, "app", None), "state", None), "appspec", None)
    )
    _app_title = str(getattr(appspec, "app_title", None) or getattr(appspec, "name", None) or "App")
    page_ctx = PageContext(
        page_title=_app_title,
        app_name=_app_title,
        nav_items=[],
        nav_groups=[],
        current_route=current_route,
        nav_model=nav_model,
        user_roles=list(user_roles),
        tenant_config=getattr(getattr(request, "state", None), "tenant_config", {}) or {},
    )
    return page_ctx, _resolve_chrome_assets(request.app.state)


def _apply_anon_nav(prc: _PageRequestContext) -> None:
    """#1127: swap the sidebar to the anon-safe variants.

    Compile-time builds two parallel nav lists per page: ``nav_items``
    (everything) and ``nav_items_anon`` (only items from workspaces
    that declared no persona gate). This helper switches to the anon
    variants whenever the request has no auth, no user, or no role
    that matches any persona — closing the leak where anon visitors
    were seeing more workspaces than authenticated users.
    """
    prc.ctx.nav_items = list(prc.ctx.nav_items_anon)
    prc.ctx.nav_groups = list(prc.ctx.nav_groups_anon)


async def _inject_auth_context(prc: _PageRequestContext) -> None:
    """Resolve auth context from request and inject into page context.

    Anon nav contract (#1127): when no auth context is configured, the
    request has no user, or the user matches no compiled persona, the
    sidebar collapses to ``nav_items_anon`` — items whose underlying
    workspace declared no persona gate. Workspaces with
    ``access: persona(...)`` are never exposed in the anon sidebar.

    Async (#1128): ``get_auth_context`` may be either sync or async.
    The resolver call goes through ``_resolve_auth_context`` which
    awaits the returned coroutine when the project wires up an
    ``async def`` auth dependency (FastAPI-idiomatic). Pre-async
    sync callables continue to work unchanged.
    """
    # #1324 FR-4: expose per-tenant config to render-time nav ``when`` eval.
    # Set unconditionally (independent of auth wiring) so ``tenant_config.<key>``
    # references resolve on every render path. ``{}`` when the app has no
    # tenancy or the request carries no tenant state (defensive — not all apps
    # run behind TenantMiddleware).
    prc.ctx.tenant_config = getattr(getattr(prc.request, "state", None), "tenant_config", {}) or {}

    if prc.deps.get_auth_context is None:
        # No auth wiring at all — the app has opted out of access
        # control. Persona gates have no enforcement layer in this
        # mode, so leave the compile-time nav as declared rather
        # than collapsing the sidebar to nothing. The anon-leak path
        # closed by #1127 is the production shape: auth IS configured,
        # but the request has no session yet (handled below).
        #
        # #1324 slice 3b: leave ``nav_model`` unset here so the sidebar seam
        # falls back to the legacy full declared nav. This branch is the
        # "developer opted out of access control" mode — there are no persona
        # gates to enforce and no session to resolve a persona from, so
        # collapsing to the anon nav (a strict subset) would wrongly hide
        # workspaces. The anon nav is for the production shape (auth IS
        # configured, request has no session) handled in the else-branch below.
        return
    try:
        prc.auth_ctx = await _resolve_auth_context(prc.deps.get_auth_context, prc.request)
        prc.ctx.is_authenticated = bool(prc.auth_ctx and prc.auth_ctx.is_authenticated)
        if prc.auth_ctx and prc.auth_ctx.user:
            prc.ctx.user_email = prc.auth_ctx.user.email or ""
            prc.ctx.user_name = prc.auth_ctx.user.username or ""
            prc.ctx.user_preferences = prc.auth_ctx.preferences or {}
            # Persona-aware nav filtering: match user roles against
            # per-persona nav variants compiled from workspace access.
            roles = getattr(prc.auth_ctx.user, "roles", None) or []
            prc.ctx.user_roles = list(roles)
            # #1324: the sidebar now renders from the precomputed per-persona
            # NavModel. This branch is the AUTHENTICATED path (auth_ctx.user is
            # set), so pass authenticated=True: a role matching a persona picks
            # that persona's nav; a role matching NONE (e.g. role_admin, which
            # is a role name not a persona) returns None so the legacy curated
            # nav_groups below render — NOT the anon nav (the slice-3b regression).
            prc.ctx.nav_model = _resolve_nav_model(prc.deps, list(roles), authenticated=True)
            matched_persona = False
            if prc.ctx.nav_by_persona and roles:
                for role in roles:
                    # Roles use "role_" prefix; persona IDs don't
                    persona_nav = prc.ctx.nav_by_persona.get(role.removeprefix("role_"))
                    if persona_nav is not None:
                        prc.ctx.nav_items = persona_nav
                        matched_persona = True
                        break

            # v0.61.5 (#863): mirror the per-persona resolution for nav_groups
            # so entity-list pages show the same collapsible groups workspace
            # pages show, filtered to the user's persona.
            if getattr(prc.ctx, "nav_groups_by_persona", None) and roles:
                for role in roles:
                    persona_groups = prc.ctx.nav_groups_by_persona.get(role.removeprefix("role_"))
                    if persona_groups is not None:
                        prc.ctx.nav_groups = persona_groups
                        break

            # #1127: authenticated but no persona match → anon-safe view.
            # An authed user with a role the app doesn't recognise has
            # the same nav reach as an anon visitor; without this they'd
            # see the unfiltered flat nav and leak persona-gated entries.
            if prc.ctx.nav_by_persona and not matched_persona:
                _apply_anon_nav(prc)

            # Filter out nav items for entities the user cannot LIST (#583).
            # This catches entities that appear in an allowed workspace but
            # whose permit: rules deny the user's role.
            if prc.ctx.nav_items and prc.deps.entity_cedar_specs and prc.deps.route_entity:
                prc.ctx.nav_items = _filter_nav_by_entity_access(
                    prc.ctx.nav_items, prc.deps, prc.auth_ctx
                )

            # Deduplicate flat nav_items against nav_groups children (#874).
            # Workspace pages already filter via _build_visible_nav, but
            # entity-list pages render ctx.nav_items + ctx.nav_groups raw.
            # Drop any flat item whose route also appears as a nav_group
            # child so users don't see "Recommendations" twice (once flat,
            # once under "Insights").
            if prc.ctx.nav_items and prc.ctx.nav_groups:
                prc.ctx.nav_items = _dedupe_nav_items_against_groups(
                    prc.ctx.nav_items, prc.ctx.nav_groups
                )
        else:
            # #1127: auth wiring present but request is anon (no user or
            # not authenticated) — apply the anon-safe nav.
            _apply_anon_nav(prc)
            # #1324 slice 3b: drive the sidebar from the precomputed anon nav.
            prc.ctx.nav_model = prc.deps.anon_nav
    except Exception:
        logger.warning("Failed to resolve auth context for page", exc_info=True)
        # Fail closed: an exception while resolving auth must not leave
        # the full unfiltered nav exposed (#1127).
        _apply_anon_nav(prc)
        # #1324 slice 3b: fail closed for the NavModel path too.
        prc.ctx.nav_model = prc.deps.anon_nav


def _inject_onboarding_step(prc: _PageRequestContext) -> None:
    """Resolve + render the active guide step for the current user/surface (v0.71.3).

    No-op when any of 11 branches fail — see the ``onboarding.inject:``
    tagged log lines below for the full list and what each one means
    in production (#1118). Every skip path emits one INFO line tagged
    ``onboarding.inject:<reason>`` so production-log grep can answer
    "why isn't my guide rendering?" without source-level debugging.

    On success, sets ``prc.ctx.active_guide_html`` to the rendered
    fragment. ``template_renderer._render_typed_body`` prepends it
    to the surface body.
    """
    # #1293: the page ctx is captured once per route in
    # ``_make_page_handler``'s closure and shared across every request to
    # that route. ``active_guide_html`` is the one ctx field that's
    # conditionally set (only on the happy path below) but never reset — so
    # an overlay rendered for one persona (e.g. an engineer's "Register
    # Device" empty-state CTA → ``/device_create``) persisted on the shared
    # ctx and bled into the *next* persona's render, including a tester who
    # can't create Devices. That tripped ``rbac:Device:{tester,manager}:create``
    # under ``--managed`` (which renders multiple personas in one server
    # lifetime) while single-persona local repros passed. Reset every request
    # — the same discipline ``_apply_anon_nav`` uses for ``nav_items`` — so
    # only the matching persona's overlay (re)populates it below.
    prc.ctx.active_guide_html = ""

    appspec = prc.deps.appspec
    surface_name = prc.ctx.view_name or ""

    if not getattr(appspec, "guides", None):
        # AppSpec has no guides — the most common skip path. INFO
        # noise here would dominate logs on apps without guides; keep
        # at DEBUG.
        logger.debug("onboarding.inject:no-guides surface=%s", surface_name)
        return

    if prc.auth_ctx is None or not prc.auth_ctx.is_authenticated:
        logger.info(
            "onboarding.inject:not-authenticated surface=%s auth_ctx=%s",
            surface_name,
            "None" if prc.auth_ctx is None else "unauthenticated",
        )
        return
    user = getattr(prc.auth_ctx, "user", None)
    if user is None:
        logger.info("onboarding.inject:no-user surface=%s", surface_name)
        return
    user_id = getattr(user, "id", None)
    if user_id is None:
        logger.info("onboarding.inject:no-user-id surface=%s", surface_name)
        return

    repo = getattr(prc.request.app.state, "onboarding_state", None)
    if repo is None:
        # The most likely "wired in dev, missing in prod" path —
        # AuthSubsystem.startup only attaches the repo when
        # ctx.appspec has guides AND ctx.database_url is set. INFO so
        # an operator can grep for this exact tag to confirm.
        logger.info(
            "onboarding.inject:no-repo surface=%s user_id=%s "
            "(app.state.onboarding_state is None — check that "
            "AuthSubsystem.startup ran with guides + database_url)",
            surface_name,
            user_id,
        )
        return

    # Pick the persona to match against the audience predicate. Roles
    # are stored as ``role_<persona>`` strings (see _inject_auth_context
    # above); strip the prefix and pick the first one — guides target
    # one persona at a time and the user's primary role is the first
    # entry by convention.
    user_persona = ""
    roles = list(getattr(user, "roles", None) or [])
    if roles:
        user_persona = roles[0].removeprefix("role_")

    if not surface_name:
        logger.info(
            "onboarding.inject:no-surface-name user_id=%s persona=%s "
            "(prc.ctx.view_name is empty — usually a route that "
            "doesn't correspond to a DSL surface)",
            user_id,
            user_persona,
        )
        return

    try:
        from dazzle.render.onboarding import (
            UnknownStepKindError,
            has_builder,
            render_step,
            resolve_active_step,
        )
    except ImportError as exc:
        # Onboarding package missing — defensive; shouldn't happen
        # since it ships with the framework. Don't crash the page.
        logger.warning(
            "onboarding.inject:import-error surface=%s user_id=%s exc=%r",
            surface_name,
            user_id,
            exc,
        )
        return

    try:
        result = resolve_active_step(
            user_id=str(user_id),
            user_persona=user_persona,
            surface_name=surface_name,
            app=appspec,
            repo=repo,
        )
    except Exception as exc:
        # Repository or resolver errors are non-fatal — log and skip
        # the overlay. The user still sees their page. Bumped from
        # DEBUG to INFO in #1118 so production can see when this
        # silently catches.
        logger.info(
            "onboarding.inject:resolve-failed surface=%s user_id=%s persona=%s exc=%r",
            surface_name,
            user_id,
            user_persona,
            exc,
            exc_info=True,
        )
        return

    if result is None:
        logger.info(
            "onboarding.inject:no-active-step surface=%s user_id=%s persona=%s "
            "(resolver returned None — audience predicate didn't match, "
            "all steps already completed/dismissed, or no guide targets "
            "this surface)",
            surface_name,
            user_id,
            user_persona,
        )
        return
    guide, step = result

    kind = step.kind.value if hasattr(step.kind, "value") else str(step.kind)
    if not has_builder(kind):
        # Kind shipped in a future Dazzle release but the runtime
        # doesn't have a builder for it yet. Skip silently — the
        # user still sees their page.
        logger.info(
            "onboarding.inject:no-builder surface=%s guide=%s step=%s kind=%s",
            surface_name,
            guide.name,
            step.name,
            kind,
        )
        return
    # Runtime backstop (#1292): drop a CTA pointing at a create/edit surface
    # this persona can't mutate, so onboarding never dangles an affordance
    # that 403s. Defence in depth behind the validate-time guide-CTA access
    # check — a validate-passing app never trips this.
    step = _suppress_inaccessible_cta(step, prc, appspec)
    try:
        prc.ctx.active_guide_html = render_step(step, guide_name=guide.name)
    except UnknownStepKindError:
        # Race: has_builder said yes but render_step raised. Defensive.
        logger.warning(
            "onboarding.inject:render-failed surface=%s guide=%s step=%s "
            "kind=%s (has_builder=True but render_step raised)",
            surface_name,
            guide.name,
            step.name,
            kind,
        )
        return

    logger.info(
        "onboarding.inject:rendered surface=%s guide=%s step=%s kind=%s user_id=%s",
        surface_name,
        guide.name,
        step.name,
        kind,
        user_id,
    )


def _dedupe_nav_items_against_groups(
    nav_items: list[Any], nav_groups: list[dict[str, Any]]
) -> list[Any]:
    """Drop flat nav items whose route also appears as a nav_group child.

    Entity-list pages render ``ctx.nav_items`` and ``ctx.nav_groups``
    side-by-side (#863). When the same route exists in both — e.g. an
    entity that's auto-discovered as a flat item AND placed in a
    nav_group — users see it twice. Workspace pages already do this
    filter via ``_build_visible_nav``; this helper is the entity-page
    parallel (#874).
    """
    grouped_routes = {
        child.get("route")
        for group in nav_groups
        for child in group.get("children", [])
        if child.get("route")
    }
    if not grouped_routes:
        return nav_items
    return [item for item in nav_items if getattr(item, "route", None) not in grouped_routes]


# Compile-time nav-visibility mirror in
# src/dazzle/page/converters/template_compiler.py — keep both in sync when
# changing access-check semantics.
def _check_surface_access(prc: _PageRequestContext) -> Response | None:
    """Enforce surface-level access control. Returns a Response to abort, or None."""
    from dazzle.render.surface_access import (
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
    if _cedar_spec is None:
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
    _decision = evaluate_permission(
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


async def _read_entity_in_process(
    prc: _PageRequestContext, entity_name: str, path_id: Any
) -> dict[str, Any]:
    """Read one entity row IN-PROCESS with scope + permit applied (#1422).

    Replaces the page layer's HTTP self-fetch of its own REST detail endpoint.
    Returns the record as the same JSON-shaped dict the REST route produced
    (``jsonable_encoder`` over a ``response_model=None`` handler return), or
    ``{"error": "not_found"}`` when the row is missing / scope- / permit-denied
    — so callers' existing ``"error" in item`` → 404 handling is preserved.

    All scope/permit inputs come from the page router config (``prc.deps``), wired
    at ``create_page_routes`` time (boot-path-independent). Cedar entities go
    through ``gated_read``; entities with no cedar spec do a plain read, matching
    the REST ``_core`` path (no permit eval).
    """
    from fastapi.encoders import jsonable_encoder

    from dazzle.http.runtime.access.gated import (
        RecordNotFound,
        access_context_from,
        gated_read,
    )

    service = prc.deps.entity_services.get(entity_name)
    if service is None:
        return {"error": "not_found"}
    cedar = prc.deps.entity_cedar_specs.get(entity_name)
    auto_include = prc.deps.entity_auto_includes.get(entity_name)
    try:
        if cedar is not None:
            access = access_context_from(
                auth_context=prc.auth_ctx,
                entity_name=entity_name,
                cedar_access_spec=cedar,
                fk_graph=prc.deps.entity_fk_graph,
                admin_personas=prc.deps.entity_admin_personas,
            )
            item = await gated_read(service, access, path_id, include=auto_include)
        else:
            item = await service.execute(operation="read", id=path_id, include=auto_include)
    except RecordNotFound:
        return {"error": "not_found"}
    if item is None:
        return {"error": "not_found"}
    encoded = jsonable_encoder(item)
    return encoded if isinstance(encoded, dict) else {"error": "not_found"}


async def _list_entity_in_process(
    prc: _PageRequestContext,
    entity_name: str,
    *,
    page: int,
    page_size: int,
    sort: str | None = None,
    direction: str = "asc",
    search: str | None = None,
    filters: dict[str, Any] | None = None,
    as_of_raw: str | None = None,
    include_closed: bool = False,
) -> dict[str, Any]:
    """List entity rows IN-PROCESS with scope + permit applied (#1422).

    Replaces the page layer's HTTP self-fetch of its own REST list endpoint. Calls
    `gated_list` (the same enforcement the REST list route applies) and returns the
    REST-shaped `{items,total,page,page_size}` dict (`jsonable_encoder` over the
    result, so `items` are plain dicts as the table renderer expects). A
    permit-denied / scope-empty / missing-service list yields an empty page.
    """
    from fastapi.encoders import jsonable_encoder

    from dazzle.http.runtime.access.gated import (
        AccessForbidden,
        InvalidTemporalParam,
        access_context_from,
        gated_list,
    )

    _empty = {"items": [], "total": 0, "page": page, "page_size": page_size}
    service = prc.deps.entity_services.get(entity_name)
    if service is None:
        return _empty
    access = access_context_from(
        auth_context=prc.auth_ctx,
        entity_name=entity_name,
        cedar_access_spec=prc.deps.entity_cedar_specs.get(entity_name),
        fk_graph=prc.deps.entity_fk_graph,
        admin_personas=prc.deps.entity_admin_personas,
    )
    sort_list = [f"-{sort}" if direction == "desc" else sort] if sort else None
    try:
        result = await gated_list(
            service,
            access,
            page=page,
            page_size=page_size,
            sort_list=sort_list,
            search=search,
            user_filters=filters or None,
            auto_include=prc.deps.entity_auto_includes.get(entity_name),
            access_spec=prc.deps.entity_access_specs.get(entity_name),
            temporal_as_of_raw=as_of_raw,
            temporal_include_closed=include_closed,
        )
    except (AccessForbidden, InvalidTemporalParam):
        return _empty
    encoded = jsonable_encoder(result)
    return encoded if isinstance(encoded, dict) else _empty


async def _handle_detail(prc: _PageRequestContext) -> None:
    """Fetch and prepare detail page data for the per-request context."""
    req_detail = prc.ctx.detail.model_copy(deep=True)

    # Fetch item data IN-PROCESS (#1422) — no self-fetch. Same scope+permit the
    # REST detail route applies (`gated_read` IS that enforcement, relocated),
    # serialized via `jsonable_encoder` to match the REST `response_model=None`
    # JSON shape the downstream FK-display / when_expr code expects.
    req_detail.item = await _read_entity_in_process(prc, prc.ctx.detail.entity_name, prc.path_id)
    # Resolve FK dicts -> display strings so detail fields show names not UUIDs (#663)
    if req_detail.item and "error" not in req_detail.item:
        req_detail.item = _inject_display_names(req_detail.item)

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
        from dazzle.page.utils.expression_eval import evaluate_when_expr

        for _field in req_detail.fields:
            if _field.when_expr:
                _field.visible = evaluate_when_expr(_field.when_expr, req_detail.item)

    # Evaluate role-based visible conditions (#487)
    if prc.ctx.user_roles is not None:
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

        async def _fetch_related_tab(tab: Any, _id: str) -> None:
            # IN-PROCESS related-list read (#1422) — no self-fetch. Filter the
            # related entity by its FK to this record (+ polymorphic type field).
            _filters: dict[str, Any] = {tab.filter_field: _id}
            if tab.filter_type_field and tab.filter_type_value:
                _filters[tab.filter_type_field] = tab.filter_type_value
            data = await _list_entity_in_process(
                prc, tab.entity_name, page=1, page_size=50, filters=_filters
            )
            tab.rows = data.get("items", [])
            tab.total = data.get("total", len(tab.rows))

        all_tabs = [tab for _group in req_detail.related_groups for tab in _group.tabs]
        await asyncio.gather(*[_fetch_related_tab(tab, str(prc.path_id)) for tab in all_tabs])

    prc.ctx_overrides["detail"] = req_detail


async def _handle_edit_form(prc: _PageRequestContext) -> None:
    """Fetch and prepare edit form data for the per-request context."""
    req_form = prc.ctx.form.model_copy(deep=True)

    # Fetch existing data IN-PROCESS (#1422) — no self-fetch; same scope+permit
    # as the REST detail route, via the shared in-process reader.
    form_data = await _read_entity_in_process(prc, prc.ctx.form.entity_name, prc.path_id)
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
        # IN-PROCESS list read (#1422) — no self-fetch. Same scope+permit the REST
        # list route applies (gated_list), via the shared in-process lister.
        _t_filters = {
            k[7:-1]: v for k, v in api_params.items() if k.startswith("filter[") and k.endswith("]")
        }
        try:
            data = await _list_entity_in_process(
                prc,
                req_table.entity_name,
                page=int(api_params.get("page", "1") or 1),
                page_size=int(api_params.get("page_size", "20") or 20),
                sort=api_params.get("sort"),
                direction=api_params.get("dir", "asc"),
                search=api_params.get("search"),
                filters=_t_filters or None,
            )
            items = data.get("items", [])
            if items and isinstance(items[0], dict):
                req_table.rows = items
            req_table.total = data.get("total", len(items))
        except Exception:
            logger.warning(
                "Failed to list %s in-process",
                getattr(req_table, "entity_name", "?"),
                exc_info=True,
            )
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


def _build_dispatch_ctx(
    render_ctx: Any,
    surface: ir.SurfaceSpec | None = None,
    *,
    services: Any = None,
) -> dict[str, Any]:
    """Translate the per-request PageContext into the flat ctx dict shape
    that the renderer registry adapters consume.

    Plan 3 covered LIST; Plan 8 added VIEW. For LIST we extract the
    ``table`` context; for VIEW we extract the ``detail`` context's
    sections+fields into a flat ``fields`` list. For other modes the
    dispatch branch is not selected (see ``_render_response``).
    """
    table = getattr(render_ctx, "table", None)
    if table is not None:
        columns_out: list[dict[str, Any]] = []
        for col in getattr(table, "columns", []) or []:
            columns_out.append(
                {
                    "key": getattr(col, "key", ""),
                    "label": getattr(col, "label", "") or getattr(col, "key", ""),
                    "type": getattr(col, "type", "text"),
                    "sortable": getattr(col, "sortable", False),
                    "filterable": getattr(col, "filterable", False),
                    "hidden": getattr(col, "hidden", False),
                    # ADR-0049 Task 5: the canonical ListFilterBar needs the
                    # per-column filter kind + ref wiring, or text/ref filters
                    # degrade to empty selects. (filter_type "text"/"select"/
                    # "ref"; ref_* drive dzFilterRefSelect.)
                    "filter_type": getattr(col, "filter_type", "text") or "text",
                    "filter_ref_entity": getattr(col, "filter_ref_entity", "") or "",
                    "filter_ref_api": getattr(col, "filter_ref_api", "") or "",
                    # Issue #1029 phase 5: filter options for select-typed
                    # filterable columns. Each option is {"value", "label"}.
                    "filter_options": [
                        (str(o.get("value", "")), str(o.get("label", o.get("value", ""))))
                        for o in (getattr(col, "filter_options", []) or [])
                    ],
                }
            )
        return {
            "items": list(getattr(table, "rows", []) or []),
            "columns": columns_out,
            "endpoint": getattr(table, "api_endpoint", "") or "",
            "total": int(getattr(table, "total", 0) or 0),
            "page": int(getattr(table, "page", 1) or 1),
            "page_size": int(getattr(table, "page_size", 20) or 20),
            # Issue #1205: region_name must match the workspace region
            # container id (`region-<surface.name>`), not the table_id.
            # Pre-fix the FilterBar emitted `hx-target="#region-dt-<id>"`
            # while the actual container was `#region-<surface.name>` —
            # one-prefix mismatch fired htmx:targetError on every filter
            # change. Prefer surface.name; fall back to table_id only if
            # surface has no name (defensive — shouldn't happen).
            "region_name": getattr(surface, "name", "") or getattr(table, "table_id", "") or "",
            "empty_message": getattr(table, "empty_message", "") or "No items found.",
            # Issue #1029 phase 4: typed empty-state variants (#807).
            # Adapter picks the right one based on `empty_kind`.
            "empty_collection": getattr(table, "empty_collection", "") or "",
            "empty_filtered": getattr(table, "empty_filtered", "") or "",
            "empty_forbidden": getattr(table, "empty_forbidden", "") or "",
            "empty_kind": getattr(table, "empty_kind", "") or "collection",
            # CI-fix: thread create_url through so the Fragment list
            # adapter can emit a Create link required by the UX
            # contract checker (rbac:<Entity>:<persona>:create).
            "create_url": getattr(table, "create_url", "") or "",
            # #1487: the entity's declared display title for the "New <Entity>"
            # create CTA (so it reads "New Curriculum Plan", not the raw class
            # name). Empty → adapter humanises entity_name.
            "entity_title": getattr(table, "entity_title", "") or "",
            # Issue #1029 phase 1: detail_url_template threads through
            # so the adapter can wrap each <tr> in an hx-get drill-down
            # to the detail surface. Template usually contains "{id}"
            # which the adapter substitutes per row.
            "detail_url_template": getattr(table, "detail_url_template", "") or "",
            # Issue #1029 phase 5: search + filter state.
            "search_enabled": bool(getattr(table, "search_enabled", False)),
            "search_fields": list(getattr(table, "search_fields", []) or []),
            "filter_values": dict(getattr(table, "filter_values", {}) or {}),
            # Issue #1029 phase 6: active sort state for SortHeader
            # current-direction wiring.
            "sort_field": str(getattr(table, "sort_field", "") or ""),
            "sort_dir": str(getattr(table, "sort_dir", "asc") or "asc"),
            # Issue #1029 phase 7: bulk-actions flag + per-row ids.
            "bulk_actions": bool(getattr(table, "bulk_actions", False)),
            # ADR-0049 Task 5: fields the canonical substrate list reads that
            # the legacy renderer read straight off TableContext. Without these
            # the flip silently regresses inline-edit, live-refresh, infinite
            # scroll, and search-first lists.
            "inline_editable": list(getattr(table, "inline_editable", []) or []),
            "refresh_interval": getattr(table, "refresh_interval", None),
            "pagination_mode": str(getattr(table, "pagination_mode", "pages") or "pages"),
            "search_first": bool(getattr(table, "search_first", False)),
        }

    form = getattr(render_ctx, "form", None)
    if form is not None:
        fields_out: list[dict[str, Any]] = []
        initial_values = getattr(form, "initial_values", {}) or {}
        for field in getattr(form, "fields", []) or []:
            fname = getattr(field, "name", "")
            kind = getattr(field, "type", None) or "str"
            raw_value = initial_values.get(fname, "")
            entry = {
                "name": fname,
                "label": getattr(field, "label", "") or fname,
                "kind": str(kind).lower(),
                "required": bool(getattr(field, "required", False)),
                "value": raw_value or "",
                "placeholder": getattr(field, "placeholder", "") or "",
            }
            options = getattr(field, "options", None)
            if options:
                # Each option dict has {"value": ..., "label": ...}
                entry["options"] = [
                    (str(o.get("value", "")), str(o.get("label", o.get("value", ""))))
                    for o in options
                ]
            # Plan 14: thread ref_api into Fragment dispatch ctx so the
            # adapter's REF branch can produce a RefPicker primitive.
            ref_api = str(getattr(field, "ref_api", "") or "")
            if ref_api:
                entry["ref_api"] = ref_api
            initial_label_value = str(getattr(field, "initial_label", "") or "")
            if initial_label_value:
                entry["initial_label"] = initial_label_value
            # Issue #1027: ref-typed fields in EDIT mode receive an
            # eagerly-expanded related-record dict from the loader,
            # not the bare FK UUID. Coerce to the FK scalar and lift
            # a sensible display value into `initial_label` so the
            # dropdown reads something while the lazy fetch resolves.
            if ref_api and isinstance(raw_value, dict):
                entry["value"] = str(raw_value.get("id", "") or "")
                if not entry.get("initial_label"):
                    for label_key in (
                        "__display__",
                        "name",
                        "title",
                        "label",
                        "email",
                        "code",
                    ):
                        if raw_value.get(label_key):
                            entry["initial_label"] = str(raw_value[label_key])
                            break
            fields_out.append(entry)
        is_edit = str(getattr(form, "mode", "create")).lower() == "edit"
        # Issue #1031: thread `form.sections` into the ctx alongside the
        # flat fields. The adapter prefers sections when populated;
        # falls back to the flat list for single-section / no-section
        # forms (backwards-compat — won't grow a redundant heading on
        # forms declaring just `section main`).
        form_sections = getattr(form, "sections", []) or []
        sections_out: list[dict[str, Any]] = []
        if len(form_sections) >= 2:
            field_index = {entry["name"]: entry for entry in fields_out}
            for section in form_sections:
                section_fields = []
                for sf in getattr(section, "fields", []) or []:
                    sf_name = getattr(sf, "name", "")
                    matched = field_index.get(sf_name)
                    if matched is not None:
                        section_fields.append(matched)
                sections_out.append(
                    {
                        "name": getattr(section, "name", ""),
                        "title": getattr(section, "title", "") or getattr(section, "name", ""),
                        "fields": section_fields,
                        "note": getattr(section, "note", "") or "",
                    }
                )
        ctx_out: dict[str, Any] = {
            "fields": fields_out,
            "action": getattr(form, "action_url", "") or "",
            "method": str(getattr(form, "method", "POST") or "POST").upper(),
            "submit_label": "Save" if is_edit else "Create",
        }
        if sections_out:
            ctx_out["sections"] = sections_out
        return ctx_out

    detail = getattr(render_ctx, "detail", None)
    if detail is not None:
        # Issue #1028: DetailContext is a flat list of FieldContext + a
        # parallel `item: dict` of values keyed by field.name. The
        # pre-fix nested loop iterated `detail.sections` (which doesn't
        # exist) and read `f.value` (also doesn't exist) — yielding
        # zero fields with empty values, so the fragment adapter
        # always rendered EmptyState. Match the legacy template's
        # `detail.item.get(field.name, "")` value source.
        item = getattr(detail, "item", {}) or {}
        # Re-bind: `fields_out` was also used by the form branch above; the
        # detail branch is a distinct code path with the same conceptual
        # output, so we shadow it deliberately.
        detail_fields_out: list[dict[str, Any]] = []
        for f in getattr(detail, "fields", []) or []:
            field_name = getattr(f, "name", "") or getattr(f, "key", "")
            value = item.get(field_name, "") if isinstance(item, dict) else ""
            detail_fields_out.append(
                {
                    "key": field_name,
                    "label": getattr(f, "label", "") or field_name,
                    "value": "" if value is None else value,
                    "kind": getattr(f, "type", "text") or "text",
                }
            )
        # #1217 Phase 3e: when a section has subtype_panel and the row's
        # kind matches a branch, append the per-subtype surface's section
        # elements as additional fields. The renderer stays section-ignorant
        # — it iterates ctx["fields"] and renders each.
        app_spec = getattr(services, "app_spec", None) if services is not None else None
        if (
            app_spec is not None
            and surface is not None
            and getattr(surface, "sections", None)
            and isinstance(item, dict)
        ):
            from dazzle.render.subtype_panel import resolve_subtype_panel_surface

            row_kind = item.get("kind")
            seen_keys = {f["key"] for f in detail_fields_out}
            for section in surface.sections:
                if getattr(section, "subtype_panel", None) is None:
                    continue
                resolved = resolve_subtype_panel_surface(section, row_kind, app_spec)
                if resolved is None:
                    continue
                # Append each element of the resolved surface's sections
                # as a field entry. The per-subtype surface's section
                # convention is one or more sections each carrying its
                # own elements list.
                for resolved_section in getattr(resolved, "sections", []) or []:
                    for element in getattr(resolved_section, "elements", []) or []:
                        field_name = getattr(element, "field_name", "") or ""
                        if not field_name or field_name in seen_keys:
                            continue
                        value = item.get(field_name, "")
                        detail_fields_out.append(
                            {
                                "key": field_name,
                                "label": getattr(element, "label", "") or field_name,
                                "value": "" if value is None else value,
                                "kind": "text",
                            }
                        )
                        seen_keys.add(field_name)
        fields_out = detail_fields_out
        # ADR-0049 Phase 2 Task 3a: thread the FETCHED related groups
        # (`detail.related_groups` — RelatedGroupContext w/ tabs + rows), not
        # the surface IR config. The substrate previously only got the config
        # (name/title/display), so it could only render a Skeleton placeholder;
        # the real related-record content needs the fetched tabs/columns/rows.
        related_groups_out: list[dict[str, Any]] = []
        for rg in getattr(detail, "related_groups", []) or []:
            tabs_out: list[dict[str, Any]] = []
            for tab in getattr(rg, "tabs", []) or []:
                if not bool(getattr(tab, "visible", True)):
                    continue
                cols_out = [
                    {
                        "key": getattr(c, "key", ""),
                        "label": getattr(c, "label", "") or getattr(c, "key", ""),
                        "type": getattr(c, "type", "text") or "text",
                        "currency_code": getattr(c, "currency_code", "") or "",
                    }
                    for c in (getattr(tab, "columns", []) or [])
                ]
                tabs_out.append(
                    {
                        "tab_id": getattr(tab, "tab_id", "") or "",
                        "label": getattr(tab, "label", "") or "",
                        "entity_name": getattr(tab, "entity_name", "") or "",
                        "columns": cols_out,
                        "rows": list(getattr(tab, "rows", []) or []),
                        "total": int(getattr(tab, "total", 0) or 0),
                        "detail_url_template": getattr(tab, "detail_url_template", "") or "",
                        "create_url": getattr(tab, "create_url", "") or "",
                        "filter_field": getattr(tab, "filter_field", "") or "",
                        "filter_type_field": getattr(tab, "filter_type_field", "") or "",
                        "filter_type_value": getattr(tab, "filter_type_value", "") or "",
                    }
                )
            related_groups_out.append(
                {
                    "group_id": getattr(rg, "group_id", "") or "",
                    "label": getattr(rg, "label", "") or "",
                    "display": str(getattr(rg, "display", "table") or "table"),
                    "is_auto": bool(getattr(rg, "is_auto", False)),
                    "tabs": tabs_out,
                }
            )
        # Issue #1030: thread action-bearing fields from DetailContext
        # so the adapter can render Edit / Delete / Back / state-machine
        # transitions / integration / external-link action buttons.
        # Pre-fix the detail branch only forwarded fields + related
        # groups, so the legacy Toolbar contract (entity_action buttons
        # in the surface header) had no Fragment-side equivalent.
        transitions_out = [
            {
                "to_state": getattr(t, "to_state", "") or "",
                "label": getattr(t, "label", "") or "",
                "api_url": getattr(t, "api_url", "") or "",
            }
            for t in (getattr(detail, "transitions", []) or [])
        ]
        integration_actions_out = [
            {
                "label": getattr(a, "label", "") or "",
                "api_url": getattr(a, "api_url", "") or "",
                # ADR-0049 Phase 2: thread the names for the action anchor
                # `data-dazzle-action="{entity}.integration.{name}.{mapping}"`.
                "integration_name": getattr(a, "integration_name", "") or "",
                "mapping_name": getattr(a, "mapping_name", "") or "",
            }
            for a in (getattr(detail, "integration_actions", []) or [])
        ]
        external_links_out = [
            {
                "label": getattr(a, "label", "") or "",
                "url": getattr(a, "url", "") or "",
                "new_tab": bool(getattr(a, "new_tab", True)),
                # ADR-0049 Phase 2: the action anchor needs the link name.
                "name": getattr(a, "name", "") or "",
            }
            for a in (getattr(detail, "external_link_actions", []) or [])
        ]
        return {
            "fields": fields_out,
            "region_name": getattr(detail, "entity_name", "") + "_detail",
            "related_groups": related_groups_out,
            "edit_url": getattr(detail, "edit_url", None) or "",
            "delete_url": getattr(detail, "delete_url", None) or "",
            "back_url": getattr(detail, "back_url", "/") or "/",
            "entity_name": getattr(detail, "entity_name", "") or "",
            "transitions": transitions_out,
            "status_field": getattr(detail, "status_field", "status") or "status",
            "integration_actions": integration_actions_out,
            "external_link_actions": external_links_out,
            # ADR-0049 Phase 2 Task 3a: the parent record id for related-group
            # create hrefs (`?{filter_field}={item_id}`).
            "item_id": str(item.get("id", "") or "") if isinstance(item, dict) else "",
            # Task 3b: opt-in audit-history region (#956).
            "show_history": bool(getattr(detail, "show_history", False)),
            # #1297: hand VIEW-mode custom renderers the original
            # DetailContext so a per-entity detail viewer can *delegate*
            # to the generic detail rendering — the modern replacement
            # for the (removed, ADR-0023) Jinja `components/detail_view.html`
            # `{% else %}{% include "dz://…" %}` fall-through. A renderer
            # registered via `render: <name>` on a VIEW surface renders its
            # bespoke chrome, then optionally appends/wraps the standard
            # view via `render_detail_view(ctx["detail_context"])`. Lazy by
            # construction: the generic HTML is only produced if the
            # renderer asks for it, so the override case costs nothing.
            "detail_context": detail,
        }

    return {}


def _maybe_dispatch_inner_html(prc: _PageRequestContext, render_ctx: Any) -> str | None:
    """If the surface declares an explicit ``render:`` clause, route the
    inner-HTML render through the renderer registry. Returns the inner
    HTML, or None for the legacy direct-template path.

    Default-deny: any failure to resolve the surface, services, or table
    context falls back to the legacy path. This keeps the change radius
    contained — only surfaces with an explicit ``render:`` clause AND a
    well-formed table context can opt in.
    """
    surface_name = prc.surface_name
    if not surface_name:
        return None
    appspec = prc.deps.appspec
    surface = appspec.get_surface(surface_name) if appspec is not None else None
    if surface is None:
        return None
    # ADR-0049 Phase 1 (the flip): `mode: list` surfaces dispatch to the typed
    # substrate even when `render is None` (the fleet default) — the substrate
    # is now the universal list render path. VIEW / CREATE / EDIT with an unset
    # `render` stay on the legacy direct-template path until their own phases.
    # CUSTOM is dispatched by the branch below only when `render` is set.
    if surface.render is None and surface.mode != SurfaceMode.LIST:
        return None

    # Services live on the FastAPI app state. Fall back to legacy path
    # if they aren't present (e.g. test fixtures with no app shell).
    services = getattr(getattr(prc.request, "app", None), "state", None)
    services = getattr(services, "services", None) if services is not None else None
    if services is None:
        return None

    # Plans 3+8 wire LIST and VIEW through dispatch. If the surface
    # has render: set but neither table nor detail context (e.g. CREATE/
    # EDIT), the framework fragment adapter would raise
    # NotImplementedError — fall back to legacy. Plan 9 will extend this
    # when form modes land.
    #
    # `mode: custom` is the carve-out (#1119): the project-registered
    # renderer is intentionally invoked with a sparse ctx — that's the
    # whole point of custom mode. Pre-#1119, the guard below treated
    # the empty ctx as "no dispatch needed" and silently fell back to
    # legacy rendering, so a registered custom renderer for a
    # mode: custom surface was never actually called. The early-return
    # for CUSTOM mode below dispatches unconditionally and lets the
    # renderer fetch its own data via `services`.
    from dazzle.render.dispatch import dispatch_render
    from dazzle.render.fragment.errors import FragmentError

    # The legacy direct-template path composes overlay + body via
    # `_render_typed_body`. The dispatch path bypasses that composer,
    # so we have to apply the same overlay prepend here. Otherwise the
    # guide overlay (set by `_inject_onboarding_step` onto
    # `render_ctx.active_guide_html`) is rendered but never reaches
    # `<body>` — #1118. The composition shape matches
    # `template_renderer._render_typed_body` exactly so the overlay
    # behaviour is identical across both paths.
    overlay = getattr(render_ctx, "active_guide_html", "") or ""

    def _compose(inner: str) -> str:
        return overlay + inner if overlay else inner

    if surface.mode == SurfaceMode.CUSTOM:
        # #1129: hand custom-mode renderers a typed CustomRenderCtx
        # instead of the empty dict the previous build path produced.
        # Existing renderers that take ``ctx: dict`` keep working —
        # CustomRenderCtx is a sibling shape, not a replacement, so
        # isinstance-aware renderers can opt into the typed form
        # without breaking the registered Protocol contract.
        from dazzle.render.context import CustomRenderCtx

        custom_ctx = CustomRenderCtx(
            request=prc.request,
            params=_collect_request_params(prc.request),
            services=services,
            auth_ctx=prc.auth_ctx,
            surface_name=surface.name,
            workspace_name=getattr(surface, "workspace", None),
        )
        try:
            return _compose(dispatch_render(surface, ctx=custom_ctx, services=services))
        except FragmentError as e:
            logger.warning(
                "dispatch_render failed for custom-mode surface %r (render=%r); "
                "falling back to legacy path: %s",
                surface.name,
                surface.render,
                e,
            )
            return None

    has_table = getattr(render_ctx, "table", None) is not None
    has_detail = getattr(render_ctx, "detail", None) is not None
    has_form = getattr(render_ctx, "form", None) is not None
    if not (has_table or has_detail or has_form):
        return None

    ctx_dict = _build_dispatch_ctx(render_ctx, surface, services=services)
    try:
        return _compose(dispatch_render(surface, ctx=ctx_dict, services=services))
    except FragmentError as e:
        logger.warning(
            "dispatch_render failed for surface %r (render=%r); falling back to legacy path: %s",
            surface.name,
            surface.render,
            e,
        )
        return None


def _render_response(prc: _PageRequestContext) -> Response:
    """Build the final HTML response, handling HTMX fragment/drawer/full modes."""
    from dazzle.http.runtime.htmx import HtmxDetails, is_peek_request
    from dazzle.page.runtime.template_renderer import render_page

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

    # Plan 3 Task 4: surfaces with an explicit ``render:`` clause
    # route through the renderer registry. ``inner_html`` is None for
    # every surface without ``render:`` set (the overwhelming majority),
    # which preserves the legacy direct-template path unchanged.
    inner_html = _maybe_dispatch_inner_html(prc, render_ctx)

    # #1494 (2c): row-peek fetch (`?peek=1`) — the list-row chevron loads this
    # entity's detail *body* into an inline panel. Return content-only (no app
    # chrome) and, unlike the generic htmx-partial path below, fire NO
    # dz:titleUpdate trigger — expanding a row must not retitle the page.
    if is_peek_request(prc.request):
        html = render_page(render_ctx, content_only=True, inner_html=inner_html)
        return HTMLResponse(content=html)  # nosemgrep

    # Fragment targeting: nav links target #main-content directly,
    # so return only the content template (no layout wrapper).
    if htmx.wants_fragment:
        html = render_page(render_ctx, content_only=True, inner_html=inner_html)
        headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": render_ctx.page_title})}
        return HTMLResponse(content=html, headers=headers)  # nosemgrep

    # Drawer targeting: workspace action clicks load detail into
    # a slide-over drawer -- return content-only + open trigger.
    if htmx.wants_drawer:
        html = render_page(render_ctx, content_only=True, inner_html=inner_html)
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

    # Phase 4 app-shell migration (v0.67.44): typed-Fragment is the
    # only path. The `app.state.fragment_chrome` flag is no longer
    # consulted here — the typed AppShell primitive renders the
    # sidebar / topbar / body chrome that the legacy
    # `layouts/app_shell.html` template used to provide.
    #
    # Two render modes:
    # - Full document: wrap inner_html in a typed Page primitive
    #   (DOCTYPE / <html> / <head> / <body>) via dispatch_render_page.
    # - htmx partial: return inner_html directly. The client extracts
    #   <body> content; for an already-rendered Fragment surface body,
    #   that's exactly what to send.
    #
    # The wants_fragment / wants_drawer paths above already short-
    # circuit via render_page(content_only=True, inner_html=...) so
    # they need no branching here.
    if inner_html is None:
        # Pre-typed-migration fallback: surfaces that haven't been
        # converted to the typed substrate still render through the
        # Jinja content template inside the typed Page chrome. Such
        # callers pass `inner_html=None` so render_page handles the
        # content render in `content_only` mode, then we wrap the
        # result in the typed Page.
        rendered_inner = render_page(render_ctx, content_only=True)
    else:
        rendered_inner = inner_html

    if is_partial:
        html = rendered_inner
    else:
        from dazzle.render.dispatch import dispatch_render_page

        # Assets and theme read from app.state. The `fragment_chrome_*`
        # state-attribute names are kept for backward compat with
        # downstream apps that already wire them — they're per-
        # deployment branding overrides, not a "use Jinja vs. typed"
        # toggle anymore.
        _assets = _resolve_chrome_assets(prc.request.app.state)
        html = dispatch_render_page(
            render_ctx,
            rendered_inner,
            css_links=_assets.css_links,
            js_scripts=_assets.js_scripts,
            theme=_assets.theme,
            font_preconnect=_assets.font_preconnect,
            favicon=_assets.favicon,
        )
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
    deps: _PageRouterConfig,
    route_path: str,
    ctx: Any,
    view_name: str | None,
    request: Request,
) -> Response:
    """Handle a page route: fetch data, enforce access, render HTML."""
    # Set current route for nav highlighting
    ctx.current_route = route_path

    surface_name = view_name or getattr(ctx, "view_name", None)
    cookies = dict(request.cookies) if request.cookies else None
    path_id = request.path_params.get("id")

    prc = _PageRequestContext(
        deps=deps,
        ctx=ctx,
        request=request,
        auth_ctx=None,
        surface_name=surface_name,
        cookies=cookies,
        path_id=path_id,
    )

    # Phase 1: Auth + access control
    await _inject_auth_context(prc)
    # v0.71.3 — resolve any active onboarding step + render its HTML.
    # No-op for anonymous users / projects without guides / unsupported
    # step kinds. The rendered overlay is prepended to the body by
    # template_renderer._render_typed_body.
    _inject_onboarding_step(prc)

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
    deps: _PageRouterConfig, route_path: str, ctx: Any, view_name: str | None = None
) -> Any:
    """Create a closure handler for a specific page route.

    Issue #1034: `functools.partial` strips type annotations from
    `inspect.signature`, so FastAPI sees `request` as an un-annotated
    parameter, defaults it to `Query(...)`, then on pydantic >= 2.13
    fails to build a TypeAdapter for the `Request` forward-ref. Wrap
    in an `async def` closure that preserves the annotation."""

    async def handler(request: Request) -> Response:
        return await _page_handler(deps, route_path, ctx, view_name, request)

    return handler


def _make_workspace_handler(
    *,
    deps: _PageRouterConfig,
    ws_ctx: Any,
    ws_route: str,
    ws_allowed_personas: list[str],
    ws_nav_items: list[dict[str, Any]],
    ws_entity_items: list[dict[str, Any]],
    ws_nav_groups: list[dict[str, Any]],
    ws_app_name: str,
    primary_action_candidates: list[dict[str, str]],
    authored_actions: list[dict[str, str]],
) -> Any:
    """Closure factory for `/app/workspaces/{name}` routes — same
    rationale as `_make_page_handler` (issue #1034). Pre-fix this
    used `functools.partial(_workspace_handler, ...)` which stripped
    the `request: Request` annotation; FastAPI then 422'd every
    workspace landing on pydantic 2.13.3."""

    async def handler(request: Request) -> Response:
        return await _workspace_handler(
            deps,
            ws_ctx,
            ws_route,
            ws_allowed_personas,
            ws_nav_items,
            ws_entity_items,
            ws_nav_groups,
            ws_app_name,
            primary_action_candidates,
            authored_actions,
            request,
        )

    return handler


def _build_workspace_primary_action_candidates(
    workspace: ir.WorkspaceSpec,
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
            entity_slug = app_paths.entity_slug(src)
            list_surface = list_surfaces_by_entity.get(src)
            label_source = (
                getattr(list_surface, "title", "") if list_surface else ""
            ) or src.replace("_", " ").title()
            actions.append(
                {
                    "entity": src,
                    "surface": create_surface.name,
                    "label": f"New {label_source}",
                    "route": app_paths.create_path(app_prefix, entity_slug),
                }
            )
    return actions


def _resolve_workspace_authored_actions(
    workspace: ir.WorkspaceSpec,
    *,
    app_prefix: str,
    surfaces_by_name: dict[str, Any],
) -> list[dict[str, str]]:
    """Resolve a workspace's authored `primary_actions:` to `{label, route}` (#1324 FR-5).

    Each authored action references a declared surface or workspace by name
    (already validated at lint time). The route is a plain GET nav target:

    * ``target_kind == "workspace"`` → ``f"{app_prefix}/workspaces/{target}"``
    * ``target_kind == "surface"``   → the surface's canonical route, computed
      with the SAME ``route_map`` as ``template_compiler.compile_appspec_to_templates``
      so heading CTAs and the rest of the app agree on surface URLs.

    There is NO per-action persona gating in v1: the workspace page's own
    access already gates visibility, so the caller appends these unconditionally
    AFTER the (permission-filtered) inferred create-CTAs. Unresolvable targets
    (which lint would already have errored on) are skipped defensively.
    """
    resolved: list[dict[str, str]] = []
    for action in getattr(workspace, "primary_actions", []) or []:
        if action.target_kind == "workspace":
            resolved.append(
                {
                    "label": action.label,
                    "route": f"{app_prefix}/workspaces/{action.target}",
                }
            )
            continue
        # target_kind == "surface": mirror the canonical surface route map.
        surface = surfaces_by_name.get(action.target)
        if surface is None:
            continue  # lint already errors on unknown targets; skip defensively
        entity_name = surface.entity_ref or "item"
        entity_slug = app_paths.entity_slug(entity_name)
        route_map = {
            SurfaceMode.LIST: app_paths.list_path(app_prefix, entity_slug),
            SurfaceMode.CREATE: app_paths.create_path(app_prefix, entity_slug),
            SurfaceMode.EDIT: app_paths.edit_path(app_prefix, entity_slug),
            SurfaceMode.VIEW: app_paths.detail_path(app_prefix, entity_slug),
        }
        route = route_map.get(surface.mode, f"{app_prefix}/{surface.name}")
        resolved.append({"label": action.label, "route": route})
    return resolved


async def _workspace_handler(
    deps: _PageRouterConfig,
    ws_context: Any,
    ws_route: str,
    ws_allowed_personas: list[str],
    ws_nav_items: list[dict[str, Any]],
    ws_entity_items: list[dict[str, Any]],
    ws_groups: list[dict[str, Any]],
    ws_app_name: str,
    primary_action_candidates: list[dict[str, str]],
    authored_actions: list[dict[str, str]],
    request: Request,
) -> Response:
    """Handle a workspace page route."""

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
            # #1128: await coroutine when get_auth_context is async.
            auth_ctx = await _resolve_auth_context(deps.get_auth_context, request)
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
            logger.warning("Failed to resolve auth for workspace nav", exc_info=True)

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

    from dazzle.http.runtime.htmx import HtmxDetails

    htmx = HtmxDetails.from_request(request)

    effective_route = ws_route
    if htmx.current_url:
        from urllib.parse import urlparse

        effective_route = urlparse(htmx.current_url).path

    # Apply per-user workspace layout preferences (order, visibility, widths)
    from dazzle.page.runtime.workspace_renderer import apply_layout_preferences, build_catalog

    render_ws_ctx = apply_layout_preferences(ws_context, user_preferences)
    catalog = build_catalog(ws_context)

    # #948 server-render migration: cards come from the workspace IR
    # directly (server-rendered HTML in `_content.html`), so the JSON
    # data island and `cards_for_json` projection are gone. The
    # template iterates `workspace.regions` and emits each card with
    # `data-card-*` attributes the JS reads on demand. `catalog` is
    # passed straight through — picker template iterates it
    # server-side AND serialises it to a `data-card-catalog` JSON blob
    # the JS reads on `addCard()`.
    fold_count = getattr(render_ws_ctx, "fold_count", 0) or 0

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

    # #1324 FR-5: APPEND authored heading CTAs AFTER the inferred create-CTAs.
    # No per-action persona gating in v1 — the workspace page's own access
    # (enforced above) gates visibility, so authored actions show to anyone
    # who can see the workspace. Targets are pre-resolved to {label, route}
    # at registration time (already validated at lint time).
    primary_actions.extend(authored_actions)

    # Phase 4 app-shell migration (v0.67.44): the workspace page
    # renders unconditionally through the typed-Fragment substrate.
    # The `fragment_chrome` flag is no longer consulted; the typed
    # AppShell primitive provides the sidebar / topbar / body chrome.
    #
    # Known regression accepted per the Phase 4 plan: persona
    # affordances that lived in the legacy Jinja navbar
    # (`user_email`, `user_name`, `user_preferences`) are not yet
    # surfaced in the typed AppShell. They can be re-added as typed
    # primitives once the persona-dropdown design lands. This is an
    # explicit "adapt to the new system" trade-off, not a parity gap.
    _ = (user_email, user_name, user_preferences, is_authenticated)

    from dazzle.page.runtime.workspace_renderer import (
        render_workspace_content_typed,
    )
    from dazzle.render.context import NavItemContext, PageContext
    from dazzle.render.dispatch import dispatch_render_page

    # #1204: edit-mode chrome (Remove-card × button on every dashboard card,
    # `data-grid-editable` on the grid container) is now opt-in. v1 gate is
    # the existing `is_superuser` check resolved above; non-superusers see
    # the dashboard without the leak that two qa-trial personas flagged as
    # workspace noise (ops_dashboard cycle 120, contact_manager cycle 151).
    workspace_inner = render_workspace_content_typed(
        workspace=render_ws_ctx,
        catalog=catalog,
        fold_count=fold_count,
        primary_actions=primary_actions,
        can_edit_layout=is_superuser,
    )

    # Fragment targeting: return only the workspace content.
    if htmx.wants_fragment:
        headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": ws_title})}
        return HTMLResponse(content=workspace_inner, headers=headers)  # nosemgrep

    # #1324: render the sidebar from the precomputed per-persona (or anon)
    # NavModel — the same source the entity-page path uses — so the two paths
    # can no longer drift. Only when auth is wired: with no auth context
    # (developer opted out of access control) there's no persona/session to
    # resolve, so leave nav_model unset and fall back to the legacy full
    # declared nav, mirroring _inject_auth_context's no-auth branch.
    #
    # ``is_authenticated`` is the resolved auth state (True only when the
    # request carried a valid session; user_roles is populated only then).
    # Passing it through is what fixes the slice-3b admin regression: an
    # authenticated admin (role_admin, which matches no persona) now resolves to
    # None and falls through to the workspace's curated nav_groups, while a
    # genuinely-anonymous request (no session) still gets the anon nav.
    _nav_model = (
        _resolve_nav_model(deps, user_roles, authenticated=is_authenticated)
        if deps.get_auth_context is not None
        else None
    )
    page_ctx = PageContext(
        page_title=ws_title,
        app_name=ws_app_name,
        nav_items=[NavItemContext(label=n["label"], route=n["route"]) for n in visible_nav],
        nav_groups=ws_groups,
        current_route=effective_route,
        nav_model=_nav_model,
        # #1324 FR-4: roles + per-tenant config for render-time nav ``when``
        # eval. ``user_roles`` carries the ``role_``-prefixed names (the sidebar
        # filter strips the prefix, matching the entity-page path). ``{}`` for
        # tenant_config when the app has no tenancy / no tenant state.
        user_roles=list(user_roles),
        tenant_config=getattr(getattr(request, "state", None), "tenant_config", {}) or {},
    )
    _assets = _resolve_chrome_assets(request.app.state)
    html = dispatch_render_page(
        page_ctx,
        workspace_inner,
        css_links=_assets.css_links,
        js_scripts=_assets.js_scripts,
        theme=_assets.theme,
        font_preconnect=_assets.font_preconnect,
        favicon=_assets.favicon,
    )
    return HTMLResponse(content=html)  # nosemgrep


def _make_root_redirect_handler(
    deps: _PageRouterConfig,
    persona_ws_routes: dict[str, str],
    fallback_ws_route: str,
) -> Any:
    """Closure factory for `/` — same rationale as `_make_page_handler` /
    `_make_workspace_handler` (issue #1034, follow-up #1112).
    `partial(_root_redirect, deps, ...)` strips the `request: Request`
    annotation, FastAPI sees an unannotated `request` parameter, pydantic
    builds an invalid `TypeAdapter[Annotated[Request, Query(...)]]` and
    poisons the shared adapter cache, cascading 422s to every other route."""

    async def handler(request: Request) -> Response:
        return await _root_redirect(deps, persona_ws_routes, fallback_ws_route, request)

    return handler


async def _root_redirect(
    deps: _PageRouterConfig,
    persona_ws_routes: dict[str, str],
    fallback_ws_route: str,
    request: Request,
) -> Response:
    """Redirect app root to the appropriate workspace for the user's persona."""
    if deps.get_auth_context is not None:
        try:
            # #1128: await coroutine when get_auth_context is async.
            auth_ctx = await _resolve_auth_context(deps.get_auth_context, request)
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


# Sibling route factories: create_site_page_routes / create_auth_page_routes
# live in src/dazzle/http/runtime/site_routes.py.
def create_page_routes(
    appspec: ir.AppSpec,
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
    *,
    convert_entity_fn: Callable[..., Any] | None = None,
    claimed_paths: set[tuple[str, str]] | None = None,
    entity_services: dict[str, Any] | None = None,
    entity_auto_includes: dict[str, Any] | None = None,
) -> APIRouter:
    """
    Create FastAPI page routes from an AppSpec.

    Each surface becomes a page route that renders server-side HTML.

    Args:
        appspec: Complete application specification.
        theme_css: Pre-compiled theme CSS to inject.
        get_auth_context: Optional callable(request) -> AuthContext for user info.
        app_prefix: URL prefix for page routes (e.g. "/app").
            Callers mounting under a prefix MUST pass this explicitly
            so that nav items, href attributes, and hx-get URLs are
            generated with the correct prefix.
        claimed_paths: ``(method, registration_path)`` pairs already
            mounted on the app — e.g. project overrides at
            ``/app/workspaces/<name>`` or CRUD lists at ``/<plural>``.
            Workspace handlers and plural-redirects whose target is in
            this set are skipped so the framework's auto-route doesn't
            shadow the explicit override (#1140). Paths here are the
            REGISTRATION paths (stripped of ``app_prefix``).

    Returns:
        FastAPI router with page routes.
    """
    claimed_paths = claimed_paths or set()

    from dazzle.page.converters.template_compiler import compile_appspec_to_templates
    from dazzle.render.surface_access import SurfaceAccessConfig

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
        _slug = app_paths.entity_slug(_entity.name)
        route_entity[app_paths.list_path(app_prefix, _slug)] = _entity.name

    # #1324 slice 3b: precompute the per-persona + anon NavModels once at boot.
    # The RBAC matrix is a pure function of the appspec; the runtime did not
    # previously materialise it, so we build it here and feed the nav builder.
    _nav_matrix = generate_access_matrix(appspec)
    persona_navs = {
        pid: _reconcile_nav_model(appspec, app_prefix, nav)
        for pid, nav in build_all_persona_navs(appspec, _nav_matrix).items()
    }
    anon_nav = _reconcile_nav_model(appspec, app_prefix, build_anon_nav(appspec, _nav_matrix))

    # #1422: scope/permit inputs for in-process reads. fk_graph + admin_personas
    # are pure functions of the appspec (the same values server.py's RouteGenerator
    # derives — fk_graph=getattr(appspec,"fk_graph",None), admin_personas from
    # tenancy); the runtime service map is threaded in from the builder.
    _entity_fk_graph = getattr(appspec, "fk_graph", None)
    _tenancy = getattr(appspec, "tenancy", None)
    _entity_admin_personas = (
        list(_tenancy.admin_personas) if _tenancy is not None and _tenancy.admin_personas else []
    )
    # Legacy visibility specs — same shape the REST RouteGenerator derives
    # (`{entity.name: entity.metadata["access"]}` for entities that declare one).
    _entity_access_specs: dict[str, Any] = {}
    for _e in appspec.domain.entities:
        _md = getattr(_e, "metadata", None)
        if _md and "access" in _md:
            _entity_access_specs[_e.name] = _md["access"]

    deps = _PageRouterConfig(
        appspec=appspec,
        theme_css=theme_css,
        get_auth_context=get_auth_context,
        app_prefix=app_prefix,
        page_contexts=page_contexts,
        access_configs=access_configs,
        entity_cedar_specs=entity_cedar_specs,
        entity_services=entity_services or {},
        entity_auto_includes=entity_auto_includes or {},
        entity_fk_graph=_entity_fk_graph,
        entity_admin_personas=_entity_admin_personas,
        entity_access_specs=_entity_access_specs,
        surface_entity=surface_entity,
        surface_mode=surface_mode,
        surface_workspace=surface_workspace,
        route_entity=route_entity,
        persona_navs=persona_navs,
        anon_nav=anon_nav,
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
    _registered_reg_paths = {
        (app_prefix and route_path[len(app_prefix) :]) or route_path
        for route_path, _ in sorted_routes
    }
    for _entity in appspec.domain.entities:
        # #990 — skip platform-domain entities (AuditEntry, JobRun,
        # AIJob, FeedbackReport, etc.). They're framework-internal
        # observability tables; surfacing /app/<plural> redirect
        # routes for them clutters OpenAPI and suggests user-
        # navigable pages that 404 anyway. Admin nav exposes them
        # via the dedicated admin workspace under /_admin/.
        if getattr(_entity, "domain", "") == "platform":
            continue
        singular_slug = app_paths.entity_slug(_entity.name)
        plural_slug = to_api_plural(_entity.name).replace("_", "-")
        if singular_slug == plural_slug:
            continue
        plural_reg_path = f"/{plural_slug}"
        if plural_reg_path in _registered_reg_paths:
            # Something real already lives here — don't shadow it.
            continue
        # #1140: also skip when the CRUD list (registered earlier by
        # route_generator) already serves the plural path. Pre-fix, an
        # entity whose canonical API path IS the plural (e.g.
        # AssessmentEvent → /assessmentevents) triggered the redirect
        # to register on top of the list endpoint, causing a real
        # conflict that resolved as redirect-to-self at request time.
        if ("GET", plural_reg_path) in claimed_paths:
            continue
        # #1004 — only register the plural redirect when the singular
        # canonical target exists. When an entity has no surfaces, the
        # singular page never gets registered, so a `/users` redirect
        # to `/user` would 301 → 404. Drop the redirect in that case;
        # there's nothing useful to point at.
        singular_reg_path = f"/{singular_slug}"
        if singular_reg_path not in _registered_reg_paths:
            continue

        redirect_target = app_paths.list_path(app_prefix, singular_slug)

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
        from dazzle.page.converters.workspace_converter import workspace_allowed_personas
        from dazzle.page.runtime.workspace_renderer import build_workspace_context

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

        # Per-workspace nav: workspace links + entity surfaces from regions.
        # When the author declared at least one nav_group, skip auto-discovery
        # of region sources entirely — nav_group is an explicit signal that
        # the author has curated the entity nav by hand and doesn't want
        # admin-shaped junctions (e.g. ClassEnrolment, QuestionTopic) leaking
        # in via region source: lines (#873). Zero-config workspaces (no
        # nav_groups) keep auto-discovery as before.
        ws_entity_nav: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            entity_items: list[dict[str, Any]] = []
            grouped = ws_grouped_entities.get(ws.name, set())
            if grouped:
                ws_entity_nav[ws.name] = entity_items
                continue
            seen_entities: set[str] = set()
            for region in ws.regions:
                # Collect all source entities (single + multi-source)
                region_sources: list[str] = []
                if region.source:
                    region_sources.append(region.source)
                region_sources.extend(getattr(region, "sources", []) or [])
                for src in region_sources:
                    if src not in seen_entities:
                        seen_entities.add(src)
                        list_surface = _list_surfaces_by_entity.get(src)
                        if list_surface:
                            entity_slug = app_paths.entity_slug(src)
                            entity_items.append(
                                {
                                    "label": list_surface.title or src.replace("_", " ").title(),
                                    "route": app_paths.list_path(app_prefix, entity_slug),
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

        # #1324 FR-5: pre-resolve each workspace's AUTHORED heading CTAs to
        # {label, route}. These APPEND AFTER the inferred create-CTAs above
        # (which are permission-filtered per request); authored actions carry
        # no per-action persona gating in v1, so they're surfaced
        # unconditionally to anyone who can see the workspace.
        _surfaces_by_name: dict[str, Any] = {s.name: s for s in surfaces}
        ws_authored_actions: dict[str, list[dict[str, str]]] = {
            ws.name: _resolve_workspace_authored_actions(
                ws,
                app_prefix=app_prefix,
                surfaces_by_name=_surfaces_by_name,
            )
            for ws in workspaces
        }

        ws_app_name = appspec.title or appspec.name.replace("_", " ").title()

        # Build nav groups per workspace from nav_group declarations (v0.38.0).
        # Children are gated on list-surface existence (#1005) — mirrors
        # template_compiler.py. The auto-injected platform-admin Management
        # group references User/Tenant which have no admin list surface, so
        # those children would 404; same applies to any author-declared
        # nav_group pointing at a surfaceless entity.
        ws_nav_group_map: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            groups: list[dict[str, Any]] = []
            for ng in getattr(ws, "nav_groups", []) or []:
                children: list[dict[str, Any]] = []
                for item in ng.items:
                    if item.entity not in _list_surfaces_by_entity:
                        continue
                    surface = _list_surfaces_by_entity[item.entity]
                    children.append(
                        {
                            "label": (surface.title or item.entity.replace("_", " ").title()),
                            "route": app_paths.list_path(
                                app_prefix, app_paths.entity_slug(item.entity)
                            ),
                            "icon": item.icon,
                        }
                    )
                if not children:
                    continue
                groups.append(
                    {
                        "label": ng.label,
                        "icon": ng.icon,
                        "collapsed": ng.collapsed,
                        "children": children,
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
            _ws_authored = ws_authored_actions.get(workspace.name, [])

            # Issue #1034: closure factory instead of `functools.partial`
            # so FastAPI sees the `Request` annotation on the handler.
            # `partial` strips annotations from `inspect.signature`,
            # which on pydantic >= 2.13 causes a 422 (FastAPI defaults
            # the un-annotated `request` to Query(...) and the
            # forward-ref TypeAdapter build fails). The closure binds
            # the per-workspace state and exposes a clean
            # `(request: Request)` signature.
            # #1140: project overrides at /app/workspaces/<name> beat
            # the framework's auto-handler in FastAPI's first-match
            # dispatch — so the auto-route is dead weight that just
            # pollutes /openapi.json and the conflict log. Skip it
            # when the override is already mounted.
            _ws_reg_path = f"/workspaces/{workspace.name}"
            if ("GET", _ws_reg_path) in claimed_paths:
                logger.info(
                    "Skipping framework auto-workspace-route GET %s — project override "
                    "already mounted (#1140).",
                    _ws_route,
                )
                continue
            handler = _make_workspace_handler(
                deps=deps,
                ws_ctx=ws_ctx,
                ws_route=_ws_route,
                ws_allowed_personas=_ws_allowed,
                ws_nav_items=ws_nav_items,
                ws_entity_items=_ws_entity_items,
                ws_nav_groups=_ws_nav_groups,
                ws_app_name=ws_app_name,
                primary_action_candidates=_ws_primary,
                authored_actions=_ws_authored,
            )
            router.get(_ws_reg_path, response_class=HTMLResponse)(handler)

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
            from dazzle.page.converters.workspace_converter import (
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
                _make_root_redirect_handler(deps, _persona_ws_routes, _fallback_ws_route)
            )

    return router
