"""App factory functions extracted from server.py.

Convenience functions for creating and running Dazzle backend applications,
including the production ASGI factory for deployment.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.environment import pin_production_env
from dazzle.core.ir import AppSpec
from dazzle.core.manifest import resolve_database_url
from dazzle.core.renderer_registry import known_renderer_names
from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig
from dazzle.http.runtime.tenant.cache import TenantCache
from dazzle.log_setup import ensure_dazzle_logging_configured
from dazzle.page.converters.workspace_converter import compute_persona_default_routes
from dazzle.tenant.cache_registry import _register_cache, _register_slug_field

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.core.ir import EntitySpec, SurfaceSpec, ViewSpec
    from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig

logger = logging.getLogger(__name__)

# #1290: convention-based project hook for injecting ASGI middleware (and any
# other post-build setup) into the FastAPI app. Projects place a module at
# ``pipeline/serve/app_init.py`` exposing ``register_middleware(app)`` — the
# framework imports and invokes it after ``builder.build()`` and after
# ``assemble_post_build_routes``. A missing module is a no-op (most projects
# don't need this); any other error from the hook is logged and re-raised so
# silent failures can't ship a half-configured app.
_PROJECT_INIT_MODULE = "pipeline.serve.app_init"
_PROJECT_INIT_HOOK = "register_middleware"
# #1401: optional page-render auth bridge. An app that wires UI auth through its
# own ASGI entrypoint (not the framework auth middleware) can expose a
# ``page_auth_context(request) -> AuthContext | None`` callable on the same
# project module; when present it OVERRIDES the framework default so `dazzle
# serve` (and the `ux verify --guides` oracle that boots through it) resolve the
# same auth context the app's own server would — otherwise the page-auth gate
# sees None and the guide overlay never renders (a false negative).
_PROJECT_PAGE_AUTH_HOOK = "page_auth_context"


def _resolve_template_or_default(dotted: str | None, default: Any) -> Any:
    """Resolve a dotted `module:symbol` template path to a callable.

    Returns the framework default callable when *dotted* is None. Raises
    ImportError / AttributeError early so a missing project hook crashes
    boot rather than silently falling back at request time.
    """
    if dotted is None:
        return default
    import importlib

    module_name, _, attr = dotted.partition(":")
    # The dotted path is sourced from the validator-checked
    # `tenant_host.{not_found,expired}_template` IR field, which the
    # validator pre-resolves via `importlib.util.find_spec` at validate
    # time (Rule 5 in src/dazzle/core/validator.py). It is not user
    # input at request time.
    module = importlib.import_module(module_name)  # nosemgrep
    return getattr(module, attr)


def _stash_tenant_state_marker(app: "FastAPI", appspec: AppSpec) -> None:
    """#1289 slice 4: attach `app.state.tenant_host` with the per-app cookie /
    guard config so the auth dependency (slice 5) can find it.

    Set to None when no entity carries `tenant_host:`. Apps without tenant_host
    keep their legacy `dazzle_session` cookie naming unchanged.
    """
    from dataclasses import dataclass

    tenant_entities = [
        e for e in appspec.domain.entities if getattr(e, "tenant_host", None) is not None
    ]
    if not tenant_entities:
        app.state.tenant_host = None
        return

    # All entities sharing a domain MUST agree on super_admin_role + canonical_hosts
    # (validator rule 6). Take the first as authoritative.
    canonical_hosts: set[str] = set()
    super_admin_role = "super_admin"
    for e in tenant_entities:
        assert e.tenant_host is not None
        canonical_hosts.update(e.tenant_host.canonical_hosts)
        super_admin_role = e.tenant_host.super_admin_role

    @dataclass(frozen=True)
    class _TenantStateMarker:
        app_name: str
        canonical_hosts: frozenset[str]
        super_admin_role: str

    app.state.tenant_host = _TenantStateMarker(
        app_name=appspec.name,
        canonical_hosts=frozenset(canonical_hosts),
        super_admin_role=super_admin_role,
    )


def _mount_tenant_resolution_middleware(
    app: "FastAPI",
    appspec: AppSpec,
    builder: "DazzleBackendApp",
) -> None:
    """#1289 slice 3: mount TenantResolutionMiddleware iff any entity has tenant_host:.

    Walks the AppSpec for entities with a `tenant_host:` block, groups by
    `domain:`, and adds one middleware per domain bound to a Resolver
    whose `lookup_fn` reads from the framework's existing Repository
    layer (system-context — no per-tenant scoping applied, since we are
    *resolving* which tenant the request belongs to).
    """
    tenant_entities = [
        e for e in appspec.domain.entities if getattr(e, "tenant_host", None) is not None
    ]
    if not tenant_entities:
        return

    # #1407: idempotency guard. A custom ASGI wrapper can run both the
    # create_app_factory mount and combined_server.run_unified_server mount on
    # the *same* app, which would stack TenantResolutionMiddleware (and a second
    # TenantCache) twice. The two call sites are mutually exclusive in normal
    # use; this protects only the abnormal same-`app` reuse path. We use an
    # app.state sentinel as the primary check (works before the middleware stack
    # is materialised) plus a user_middleware class scan as belt-and-suspenders.
    if getattr(app.state, "_tenant_resolution_mounted", False):
        logger.debug("TenantResolutionMiddleware already mounted; skipping double-mount (#1407)")
        return
    _already_in_stack = any(
        getattr(getattr(mw, "cls", None), "__name__", "") == "TenantResolutionMiddleware"
        for mw in getattr(app, "user_middleware", [])
    )
    if _already_in_stack:
        logger.debug("TenantResolutionMiddleware already in stack; skipping double-mount (#1407)")
        app.state._tenant_resolution_mounted = True
        return
    app.state._tenant_resolution_mounted = True

    from collections import defaultdict

    from dazzle.http.runtime.tenant.middleware import (
        TenantHostBinding,
        TenantResolutionMiddleware,
    )
    from dazzle.http.runtime.tenant.resolver import (
        EntityProbe,
        HistoryProbe,
        Resolver,
    )
    from dazzle.http.runtime.tenant.templates import (
        render_default_404,
        render_default_410,
    )

    by_domain: dict[str, list[Any]] = defaultdict(list)
    for e in tenant_entities:
        # tenant_entities is filtered to entries with non-None tenant_host above.
        assert e.tenant_host is not None
        by_domain[e.tenant_host.domain].append(e)

    repositories = builder.repositories

    # ADR-0037 Phase 5: tenant-hierarchy ancestor walk. Build a global
    # {kind: (parent_fk_field, parent_kind)} map from the declared `parent:` edges
    # (across all tenant kinds, any domain) + a fetch-by-id over the repositories.
    # The Resolver uses these to populate ResolvedTenant.ancestor_ids so a member
    # of a root reaches its descendant hosts. Empty map → flat tenancy (no walk).
    _parent_map: dict[str, tuple[str, str]] = {}
    for e in tenant_entities:
        parent_fk = getattr(e.tenant_host, "parent", None)
        if not parent_fk:
            continue
        fld = next((f for f in e.fields if f.name == parent_fk), None)
        parent_kind = getattr(getattr(fld, "type", None), "ref_entity", None) if fld else None
        if parent_kind:
            _parent_map[e.name] = (parent_fk, str(parent_kind))

    def _make_fetch_by_id() -> Any:
        async def _fetch_by_id(entity_name: str, row_id: str) -> Any | None:
            repo = repositories.get(entity_name)
            if repo is None:
                return None
            result = await repo.list(filters={"id": row_id}, page_size=1)
            items = result.get("items") or []
            return items[0] if items else None

        return _fetch_by_id

    _fetch_by_id_fn = _make_fetch_by_id() if _parent_map else None

    for domain, entities in by_domain.items():
        ordered = sorted(entities, key=lambda e: e.tenant_host.order or 0)
        probes = [EntityProbe(e.name, e.tenant_host.slug_field) for e in ordered]
        first_th = ordered[0].tenant_host
        assert first_th is not None  # filtered above

        history_probe = HistoryProbe(first_th.history_entity) if first_th.history_entity else None

        slug_field_by_entity = {e.name: e.tenant_host.slug_field for e in ordered}

        def _make_slug_lookup(field_map: dict[str, str]) -> Any:
            # Returns the entity OBJECT row (not a dict) — the resolver reads it
            # via _row_get, which tolerates both shapes (#1396).
            async def _lookup(entity_name: str, slug: str) -> Any | None:
                repo = repositories.get(entity_name)
                if repo is None:
                    return None
                field = field_map.get(entity_name, "slug")
                result = await repo.list(filters={field: slug}, page_size=1)
                items = result.get("items") or []
                return items[0] if items else None

            return _lookup

        async def _history_lookup(entity_name: str, slug: str) -> Any | None:
            repo = repositories.get(entity_name)
            if repo is None:
                return None
            result = await repo.list(filters={"old_slug": slug}, page_size=1)
            items = result.get("items") or []
            return items[0] if items else None

        binding = TenantHostBinding(
            app_name=appspec.name,
            domain=domain,
            canonical_hosts=tuple(first_th.canonical_hosts),
            cache=TenantCache(),
            resolver=Resolver(
                probes=probes,
                history_probe=history_probe,
                lookup_fn=_make_slug_lookup(slug_field_by_entity),
                history_lookup_fn=_history_lookup if history_probe else None,
                parent_map=_parent_map,  # ADR-0037 Phase 5 (global; empty = flat)
                fetch_by_id_fn=_fetch_by_id_fn,
            ),
            not_found_renderer=_resolve_template_or_default(
                first_th.not_found_template,
                default=lambda host, _app=appspec.name: render_default_404(
                    app_name=_app, host=host
                ),
            ),
            expired_renderer=_resolve_template_or_default(
                first_th.expired_template,
                default=lambda old, new, dom, _app=appspec.name: render_default_410(
                    app_name=_app, old_slug=old, new_slug=new, domain=dom
                ),
            ),
        )
        app.add_middleware(TenantResolutionMiddleware, binding=binding)

        # #1404 Phase B: apex tenant discovery. On the apex (canonical) host, an
        # authed identity hitting the app root is routed to their org host / picker /
        # no-orgs. The membership is at the ROOT kind (ADR-0037), so resolve slugs from
        # the root entity (no `parent:`, else the lowest-order kind on this domain).
        if first_th.canonical_hosts:
            from dazzle.http.runtime.tenant.apex_middleware import ApexDiscoveryMiddleware

            _root = next((e for e in ordered if e.tenant_host.parent is None), ordered[0])
            app.add_middleware(
                ApexDiscoveryMiddleware,
                canonical_hosts=tuple(h.lower() for h in first_th.canonical_hosts),
                domain=domain,
                root_entity=_root.name,
                root_slug_field=_root.tenant_host.slug_field,
                repositories=repositories,
            )

        # #1289 slice 6: register the cache so dazzle.tenant.bust(slug) can
        # invalidate it from project code on raw-SQL renames or admin tooling.
        # Also register each entity's slug field so Repository.update can
        # auto-bust on slug renames without any project-side wiring.

        _register_cache(binding.cache)
        for table_name, slug_col in slug_field_by_entity.items():
            _register_slug_field(table_name, slug_col)

        logger.info(
            "Mounted TenantResolutionMiddleware for domain=%s (%d entit%s)",
            domain,
            len(ordered),
            "y" if len(ordered) == 1 else "ies",
        )


def _invoke_project_post_build_hook(app: "FastAPI") -> None:
    import importlib

    try:
        module = importlib.import_module(_PROJECT_INIT_MODULE)
    except ModuleNotFoundError:
        logger.debug("No project post-build hook (%s missing)", _PROJECT_INIT_MODULE)
        return

    hook = getattr(module, _PROJECT_INIT_HOOK, None)
    if hook is None:
        logger.debug(
            "Project module %s has no %s callable",
            _PROJECT_INIT_MODULE,
            _PROJECT_INIT_HOOK,
        )
        return

    logger.info("Invoking project post-build hook %s:%s", _PROJECT_INIT_MODULE, _PROJECT_INIT_HOOK)
    hook(app)


def _resolve_project_page_auth_context() -> Any | None:
    """Return the project's ``page_auth_context`` hook, or None (#1401).

    Mirrors ``_invoke_project_post_build_hook``'s discovery: a project that wires
    UI auth via a custom ASGI entrypoint exposes
    ``pipeline.serve.app_init:page_auth_context``. A missing module / missing
    callable is a no-op (the common case); a present callable overrides the
    framework's ``builder.auth_middleware.get_auth_context`` for page rendering so
    `dazzle serve` and the app's own server share one auth bridge.
    """
    import importlib

    try:
        module = importlib.import_module(_PROJECT_INIT_MODULE)
    except ModuleNotFoundError:
        return None
    hook = getattr(module, _PROJECT_PAGE_AUTH_HOOK, None)
    if hook is None:
        return None
    if not callable(hook):
        logger.warning(
            "Project %s:%s is not callable — ignoring",
            _PROJECT_INIT_MODULE,
            _PROJECT_PAGE_AUTH_HOOK,
        )
        return None
    logger.info(
        "Using project page-auth bridge %s:%s",
        _PROJECT_INIT_MODULE,
        _PROJECT_PAGE_AUTH_HOOK,
    )
    return hook


def create_app(
    appspec: AppSpec,
    database_url: str | None = None,
    enable_auth: bool = False,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> "FastAPI":
    """
    Create a FastAPI application from an AppSpec.

    This is the main entry point for creating a Dazzle backend application.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
        enable_auth: Whether to enable authentication (default: False)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable dev control plane (default: False)
        personas: List of persona configurations for dev mode
        scenarios: List of scenario configurations for dev mode

    Returns:
        FastAPI application

    Example:
        >>> from dazzle.core.linker import build_appspec
        >>> appspec = build_appspec(modules, project_root)
        >>> app = create_app(appspec, database_url="postgresql://...")
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    # #1122 — attach a default StreamHandler to `dazzle.*` loggers if
    # the project hasn't configured logging itself. Otherwise the
    # framework's INFO-level diagnostic tags (onboarding.inject:*,
    # onboarding.startup:*, etc.) silently drop on bare uvicorn boots.
    # Idempotent + conservative — does nothing if root or dazzle.*
    # already has a handler attached. See `dazzle.log_setup`.

    ensure_dazzle_logging_configured()

    builder = DazzleBackendApp(
        appspec,
        database_url=database_url,
        enable_auth=enable_auth,
        enable_files=enable_files,
        files_path=files_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        personas=personas,
        scenarios=scenarios,
    )
    return builder.build()


def run_app(
    appspec: AppSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    database_url: str | None = None,
    enable_auth: bool = False,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
    enable_dev_mode: bool = False,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> None:
    """
    Run a Dazzle backend application.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload (for development)
        database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
        enable_auth: Whether to enable authentication (default: False)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)
        enable_dev_mode: Enable dev control plane (default: False)
        personas: List of persona configurations for dev mode
        scenarios: List of scenario configurations for dev mode
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(
        appspec,
        database_url=database_url,
        enable_auth=enable_auth,
        enable_files=enable_files,
        files_path=files_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
        enable_dev_mode=enable_dev_mode,
        personas=personas,
        scenarios=scenarios,
    )
    uvicorn.run(app, host=host, port=port, reload=reload)


# =============================================================================
# View-based list projections
# =============================================================================


def _expand_money_field(fname: str) -> list[str]:
    """Expand a money field name to its database column pair."""
    return [f"{fname}_minor", f"{fname}_currency"]


def build_entity_list_projections(
    entities: "list[EntitySpec]",
    surfaces: "list[SurfaceSpec]",
    views: "list[ViewSpec]",
) -> dict[str, list[str]]:
    """Pre-plan column projections for list surfaces (query pre-planning).

    Determines the minimal SELECT field set for each entity's list endpoint
    at startup, eliminating per-request field derivation.

    Projection sources (in priority order):
    1. View-backed surfaces (``view_ref``) — explicit field list from the view
    2. Surface sections — fields declared in ``section.elements[].field_name``
    3. Fallback — no projection (SELECT * via repository default)

    Money fields are expanded to ``_minor``/``_currency`` column pairs.
    Required fields are always included (Pydantic model validation needs them).

    Returns a mapping of ``{entity_name: [column_names]}``.
    """
    views_by_name = {v.name: v for v in views}
    # Build per-entity field metadata: type kind + required status
    entity_fields_meta: dict[str, dict[str, tuple[str, bool]]] = {}
    for entity in entities:
        entity_fields_meta[entity.name] = {
            f.name: (f.type.kind, f.is_required) for f in entity.fields
        }

    projections: dict[str, list[str]] = {}
    for surface in surfaces:
        if not surface.entity_ref:
            continue
        entity_ref = surface.entity_ref

        # Already have a projection for this entity — keep the wider one
        if entity_ref in projections:
            continue

        fields_meta = entity_fields_meta.get(entity_ref, {})

        # Source 1: View-backed projection
        if surface.view_ref:
            view = views_by_name.get(surface.view_ref)
            if view and view.fields:
                view_field_names = {f.name for f in view.fields}
                columns: list[str] = []
                # Required fields not in view (Pydantic needs them)
                for fname, (fkind, freq) in fields_meta.items():
                    if freq and fname not in view_field_names and fname != "id":
                        columns.extend(_expand_money_field(fname) if fkind == "money" else [fname])
                # View's explicit fields
                for f in view.fields:
                    kind = fields_meta.get(f.name, ("scalar", False))[0]
                    columns.extend(_expand_money_field(f.name) if kind == "money" else [f.name])
                if "id" not in columns:
                    columns.insert(0, "id")
                projections[entity_ref] = columns
                continue

        # Source 2: Surface section fields (list mode)
        if surface.mode == "list" and surface.sections:
            surface_field_names: set[str] = set()
            for section in surface.sections:
                for element in section.elements:
                    surface_field_names.add(element.field_name)
            if surface_field_names:
                columns = []
                # Required fields not explicitly listed
                for fname, (fkind, freq) in fields_meta.items():
                    if freq and fname not in surface_field_names and fname != "id":
                        columns.extend(_expand_money_field(fname) if fkind == "money" else [fname])
                # Surface's declared fields
                for fname in surface_field_names:
                    kind = fields_meta.get(fname, ("scalar", False))[0]
                    columns.extend(_expand_money_field(fname) if kind == "money" else [fname])
                if "id" not in columns:
                    columns.insert(0, "id")
                projections[entity_ref] = columns

    return projections


def build_entity_search_fields(
    surfaces: "list[SurfaceSpec]",
    entities: list[Any] | None = None,
) -> dict[str, list[str]]:
    """Pre-plan search fields for each entity.

    Surface ``search_fields:`` (legacy top-level) takes precedence, followed
    by ``surface.ux.search`` (the canonical form declared inside the ``ux:``
    sub-block — closes #856). Where neither is declared on the surface,
    entity-level ``searchable`` modifiers (``FieldModifier.SEARCHABLE``)
    are used as the final fallback, so ``title: str(300) searchable``
    registers the field for search without needing a matching surface
    declaration (#782).

    Returns a mapping of ``{entity_name: [field_names]}``.
    """
    result: dict[str, list[str]] = {}
    for surface in surfaces:
        entity_ref = surface.entity_ref
        if not entity_ref or entity_ref in result:
            continue
        sf = surface.search_fields
        if sf:
            result[entity_ref] = list(sf)
            continue
        # Fallback to ux.search — mirrors build_entity_filter_fields'
        # handling of ux.filter, which has always worked correctly.
        ux = surface.ux
        if ux and ux.search:
            result[entity_ref] = list(ux.search)
    if entities:
        for entity in entities:
            if entity.name in result:
                continue
            ir_fields = getattr(entity, "searchable_fields", None)
            if ir_fields:
                result[entity.name] = [f.name for f in ir_fields]
    return result


def build_entity_filter_fields(
    surfaces: "list[SurfaceSpec]",
) -> dict[str, list[str]]:
    """Pre-plan filter fields for each entity from surface UX declarations.

    Extracts ``ux.filter`` from list-mode surfaces. When a surface
    declares filter fields, those field names are accepted as bare
    query parameters on the entity's list endpoint (e.g. ``?status=active``).

    Returns a mapping of ``{entity_name: [field_names]}``.
    """
    result: dict[str, list[str]] = {}
    for surface in surfaces:
        entity_ref = surface.entity_ref
        if not entity_ref or entity_ref in result:
            continue
        ux = surface.ux
        if ux and ux.filter:
            result[entity_ref] = list(ux.filter)
    return result


# =============================================================================
# Shared startup helpers
# =============================================================================


def build_fragment_sources(appspec: AppSpec) -> dict[str, dict[str, Any]]:
    """Extract fragment sources from DSL ``source=`` annotations on surface elements.

    Scans all surfaces for elements with ``options.source`` references like
    ``"pack_name.operation_name"`` and loads the corresponding API pack fragment.

    Returns ``{pack_name: fragment_data}``.
    """
    frag_sources: dict[str, dict[str, Any]] = {}
    try:
        from dazzle.api_kb import load_pack

        for surface in appspec.surfaces:
            for section in getattr(surface, "sections", []):
                for element in getattr(section, "elements", []):
                    src_ref = getattr(element, "options", {}).get("source")
                    if src_ref and "." in src_ref:
                        pname, opname = src_ref.rsplit(".", 1)
                        if pname not in frag_sources:
                            pack = load_pack(pname)
                            if pack:
                                try:
                                    frag_sources[pname] = pack.generate_fragment_source(opname)
                                except ValueError:
                                    pass
    except ImportError:
        pass
    return frag_sources


def build_server_config(
    appspec: AppSpec,
    *,
    database_url: str | None = None,
    enable_auth: bool = False,
    auth_config: Any = None,
    enable_files: bool = False,
    files_path: Path | None = None,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = False,
    services_dir: Path | None = None,
    enable_processes: bool = True,
    process_adapter_class: type | None = None,
    tenant_config: Any = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    sitespec_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
    fragment_sources: dict[str, dict[str, Any]] | None = None,
    storage_defs: Any = None,  # dict[str, StorageConfig] from manifest (#932)
    audit_integrity: str = "none",  # "none" | "hash_chain" (#1197, #1206)
    security_profile: str | None = None,  # "basic" | "standard" | "strict" (#1235)
) -> "ServerConfig":
    """Build a fully-populated ``ServerConfig`` from an AppSpec.

    Computes derived config (projections, search fields, auto-includes,
    process specs, schedules, fragment sources) that both
    ``create_app_factory()`` and ``run_unified_server()`` need.

    Process adapter resolution is left to the caller (env-var-driven,
    deployment-specific).
    """

    # Validate audit_integrity at the build boundary so a misconfigured
    # value (e.g. "hash-chain" hyphen typo) fails loud here rather than
    # silently shipping the default, and before AuditLogger is constructed.
    if audit_integrity not in ("none", "hash_chain"):
        raise ValueError(f"audit_integrity must be 'none' or 'hash_chain', got {audit_integrity!r}")

    # #1235: thread the DSL-declared `security_profile:` value through to
    # ServerConfig so the rate-limit decorator and CSRF policy actually
    # take effect. Caller may override (env var path in create_app_factory);
    # otherwise fall back to appspec.security.profile, then "basic".
    if security_profile is None:
        security_cfg = getattr(appspec, "security", None)
        profile_val = getattr(getattr(security_cfg, "profile", None), "value", None)
        security_profile = profile_val or "basic"
    if security_profile not in ("basic", "standard", "strict"):
        raise ValueError(
            f"security_profile must be 'basic', 'standard', or 'strict', got {security_profile!r}"
        )

    # Compute view-based list projections from DSL surfaces
    entity_list_projections = build_entity_list_projections(
        entities=appspec.domain.entities,
        surfaces=appspec.surfaces,
        views=appspec.views,
    )

    # Extract search fields: surface declarations first, then IR searchable modifiers (#782)
    entity_search_fields = build_entity_search_fields(
        surfaces=appspec.surfaces,
        entities=list(appspec.domain.entities) if appspec.domain else None,
    )

    # Extract filter fields from surface UX declarations
    entity_filter_fields = build_entity_filter_fields(surfaces=appspec.surfaces)

    # Auto-detect ref/belongs_to fields for eager loading (prevents N+1 queries).
    # Use relation names (strip _id suffix) to match relation_loader conventions.
    entity_auto_includes: dict[str, list[str]] = {}
    for entity in appspec.domain.entities:
        rel_names = [
            f.name[:-3] if f.name.endswith("_id") else f.name
            for f in entity.fields
            if f.type.kind in ("ref", "belongs_to") and f.type.ref_entity
        ]
        if rel_names:
            entity_auto_includes[entity.name] = rel_names

    # Build FK field → target entity mapping for dotted-path scope resolution (#556).
    # Maps entity_name → {fk_field: target_entity_name} e.g. {"manuscript_id": "Manuscript"}
    entity_ref_targets: dict[str, dict[str, str]] = {}
    for entity in appspec.domain.entities:
        refs = {
            f.name: f.type.ref_entity
            for f in entity.fields
            if f.type.kind in ("ref", "belongs_to") and f.type.ref_entity
        }
        if refs:
            entity_ref_targets[entity.name] = refs

    # Extract entity status fields for process trigger status transition detection
    entity_status_fields: dict[str, str] = {}
    if appspec.domain:
        for ent in appspec.domain.entities:
            sm = getattr(ent, "state_machine", None)
            if sm:
                entity_status_fields[ent.name] = getattr(sm, "status_field", "status")

    # Merge DSL-parsed processes with persisted processes
    all_processes = list(appspec.processes)
    if project_root is not None:
        try:
            from dazzle.core.process_persistence import load_processes

            persisted = load_processes(project_root)
            dsl_names = {p.name for p in all_processes}
            merged = all_processes + [p for p in persisted if p.name not in dsl_names]
            if persisted:
                logger.info(
                    "Loaded %d persisted process(es), %d total (%d from DSL)",
                    len(persisted),
                    len(merged),
                    len(all_processes),
                )
            all_processes = merged
        except Exception:
            logger.debug("Could not load persisted processes", exc_info=True)

    # Build fragment sources if not provided by caller
    if fragment_sources is None:
        fragment_sources = build_fragment_sources(appspec)

    return ServerConfig(
        database_url=database_url,
        enable_auth=enable_auth,
        auth_config=auth_config,
        auto_provision_single_org=bool(getattr(auth_config, "auto_provision_single_org", False)),
        enable_files=enable_files,
        files_path=files_path or Path(".dazzle/uploads"),
        enable_test_mode=enable_test_mode,
        services_dir=services_dir or Path("services"),
        enable_dev_mode=enable_dev_mode,
        personas=personas or [],
        scenarios=scenarios or [],
        sitespec_data=sitespec_data,
        project_root=project_root,
        enable_processes=enable_processes,
        process_adapter_class=process_adapter_class,
        entity_list_projections=entity_list_projections,
        entity_search_fields=entity_search_fields,
        entity_filter_fields=entity_filter_fields,
        entity_auto_includes=entity_auto_includes,
        entity_ref_targets=entity_ref_targets,
        process_specs=all_processes,
        schedule_specs=list(appspec.schedules),
        entity_status_fields=entity_status_fields,
        fragment_sources=fragment_sources,
        tenant_config=tenant_config,
        storage_defs=dict(storage_defs or {}),
        audit_integrity=audit_integrity,
        security_profile=security_profile,
    )


def assemble_post_build_routes(
    app: "FastAPI",
    appspec: AppSpec,
    builder: "DazzleBackendApp",
    *,
    project_root: Path | None = None,
    sitespec_data: dict[str, Any] | None = None,
    theme_css: str = "",
    bundled_css: str = "",
    dark_mode_toggle: bool = True,
) -> None:
    """Mount all post-build routes on a FastAPI app in the correct order.

    Called by both ``create_app_factory()`` and ``run_unified_server()``
    to ensure identical route assembly.

    Order:
    1. Site page routes (if sitespec)
    2. Auth page routes (if sitespec, always with ``project_root``)
    3. App page routes (``/app/*``, always with ``app_prefix="/app"``)
    4. Experience routes (``/app/experiences/*``, if experiences exist)
    5. Bundled CSS route (``/static/css/dazzle-bundle.css``, if ``bundled_css``)
    6. Island API routes (``/_dazzle/islands``, if islands exist)
    7. Schedule sync to process adapter (if adapter + schedules)
    8. 404 handler (if sitespec)
    9. Route validation via ``validate_routes()``
    """
    # Resolve auth context callable once — used by both site and app routes
    get_auth_context = None
    if builder.auth_middleware:
        get_auth_context = builder.auth_middleware.get_auth_context
    # #1401: a project that wires UI auth through its own ASGI entrypoint can
    # override the page-render auth bridge via the project hook. When present it
    # wins over the framework default so `dazzle serve` resolves the same auth
    # context the app's own server would (without it, the guide-walk oracle sees
    # auth_ctx=None and false-negatives).
    _project_auth = _resolve_project_page_auth_context()
    if _project_auth is not None:
        get_auth_context = _project_auth

    # Compute persona -> default route mapping for authenticated root redirect (#569)
    persona_routes: dict[str, str] | None = None
    if get_auth_context and appspec.personas:
        try:
            from dazzle.page.converters.workspace_converter import compute_persona_default_routes

            persona_routes = compute_persona_default_routes(
                appspec.personas, appspec.workspaces, appspec.rhythms, appspec.surfaces
            )
        except ImportError:
            pass

    # ---- 1. Site page routes ----
    if sitespec_data:
        try:
            from dazzle.http.runtime.site_routes import (
                create_auth_page_routes,
                create_site_page_routes,
            )

            # Re-use the DSL/TOML-resolved defaults from the consent-router
            # block (identical resolution keeps the site pages and /_dazzle/consent
            # endpoints in sync).
            _site_consent = appspec.analytics.consent if appspec.analytics else None
            _site_jurisdiction = (
                _site_consent.default_jurisdiction if _site_consent else None
            ) or "EU"
            _site_override = _site_consent.consent_override if _site_consent else None
            site_page_router = create_site_page_routes(
                sitespec_data=sitespec_data,
                project_root=project_root,
                get_auth_context=get_auth_context,
                persona_routes=persona_routes,
                analytics_spec=appspec.analytics,
                consent_default_jurisdiction=_site_jurisdiction,
                consent_override=_site_override,
                dark_mode_toggle=dark_mode_toggle,
            )
            app.include_router(site_page_router)
            logger.info("  Site pages: landing, /site.js, /styles/dazzle.css")

            # ---- 2. Auth page routes ----
            auth_page_router = create_auth_page_routes(
                sitespec_data,
                project_root=project_root,
                get_auth_context=get_auth_context,
            )
            app.include_router(auth_page_router)
            logger.info("  Auth pages: /login, /signup, /2fa/setup, /2fa/settings, /2fa/challenge")
        except ImportError:
            pass

    # ---- 3. App page routes (/app/*) ----
    try:
        from dazzle.http.converters.entity_converter import convert_entity
        from dazzle.http.runtime.page_routes import create_page_routes

        # evaluate_permission / _inject_display_names used to be injected
        # into the ui page_routes module via a callable-injection shim
        # (#679 workaround); since #1094 they live in dazzle.render and
        # ui imports them directly. No longer threaded through this call.
        #
        # #1140: snapshot already-registered (method, path) pairs so
        # create_page_routes can skip workspace auto-handlers and
        # plural redirects that would shadow project overrides or
        # collide with CRUD list endpoints. Paths are stripped of the
        # `/app` prefix to match the router's registration path shape.
        claimed_paths: set[tuple[str, str]] = set()
        for _route in app.routes:
            _methods = getattr(_route, "methods", None) or set()
            _path = getattr(_route, "path", None)
            if not _methods or not _path:
                continue
            _rel = _path[len("/app") :] if _path.startswith("/app") else _path
            if not _rel:
                _rel = "/"
            for _m in _methods:
                claimed_paths.add((_m, _rel))
        page_router = create_page_routes(
            appspec,
            theme_css=theme_css,
            get_auth_context=get_auth_context,
            app_prefix="/app",
            convert_entity_fn=convert_entity,
            claimed_paths=claimed_paths,
            # #1422: thread the runtime service map + auto-includes so page
            # handlers read entity data in-process (no REST self-fetch). fk_graph
            # + admin_personas are derived from the appspec inside create_page_routes.
            # #1428: page handlers look services up by ENTITY name (`MarkingResult`),
            # but `builder.services` is keyed by *service* name (`get_markingresult`,
            # …) — an entity-name lookup against it silently misses for every entity,
            # so every in-process detail read 404'd and every in-process list went
            # silently empty. Feed the entity-name-keyed view (same #1181 footgun).
            entity_services=builder.services_by_entity(),
            entity_auto_includes=builder.entity_auto_includes,
            # #1539: the command palette honours the app's auth posture
            # (same expression as the /files + document routes; the
            # builder carries the resolved flags).
            require_auth_by_default=bool(getattr(builder, "_enable_auth", False))
            and not bool(getattr(builder, "_enable_test_mode", False)),
        )
        app.include_router(page_router, prefix="/app")
        logger.info("  App pages: %s workspaces mounted at /app", len(appspec.workspaces))

        # #1422: expose the in-process create invokers on THIS served app's state
        # (app_factory builds a separate app from the builder) so the experience
        # POST creates in-process instead of self-fetching the REST endpoint.
        app.state.entity_create_invokers = getattr(builder, "create_invokers", {})

        # ---- 4. Experience routes (/app/experiences/*) ----
        if appspec.experiences:
            try:
                from dazzle.http.runtime.experience_routes import create_experience_routes

                experience_router = create_experience_routes(
                    appspec,
                    theme_css=theme_css,
                    get_auth_context=get_auth_context,
                    app_prefix="/app",
                    project_root=project_root,
                )
                app.include_router(experience_router, prefix="/app")
                logger.info(
                    "  Experiences: %s mounted at /app/experiences",
                    len(appspec.experiences),
                )
            except ImportError as e:
                logger.warning("Experience routes not available: %s", e)
    except ImportError as e:
        logger.warning("Page routes not available: %s", e)

    # ---- 5. Bundled CSS route ----
    if bundled_css:
        try:
            from starlette.responses import Response as StarletteResponse

            _css_content = bundled_css

            @app.get("/static/css/dazzle-bundle.css", include_in_schema=False)
            async def serve_bundled_css() -> StarletteResponse:
                return StarletteResponse(
                    content=_css_content,
                    media_type="text/css",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

        except ImportError:
            pass

    # ---- 6. Island API routes ----
    if getattr(appspec, "islands", None):
        try:
            from dazzle.http.runtime.island_routes import create_island_routes

            _island_auth_dep = None
            _island_opt_dep = None
            if builder.auth_store:
                from dazzle.http.runtime.auth import (
                    create_auth_dependency,
                    create_optional_auth_dependency,
                )

                _island_auth_dep = create_auth_dependency(builder.auth_store)
                _island_opt_dep = create_optional_auth_dependency(builder.auth_store)

            island_router = create_island_routes(
                islands=appspec.islands,
                services=builder.services,
                auth_dep=_island_auth_dep,
                optional_auth_dep=_island_opt_dep,
            )
            app.include_router(island_router)
            logger.info("  Islands: %s mounted at /_dazzle/islands", len(appspec.islands))
        except ImportError as e:
            logger.warning("Island routes not available: %s", e)

    # ---- 6b. Consent banner routes + default tenant resolver ----
    # (v0.61.0 Phase 2 + Phase 6)
    try:
        from dazzle.compliance.analytics import (
            get_tenant_analytics_resolver,
            make_app_wide_resolver,
            set_tenant_analytics_resolver,
        )
        from dazzle.http.runtime.consent_routes import create_consent_routes

        # Precedence: DSL `analytics.consent:` block > TOML `[analytics]` >
        # EU-safe default. Per-tenant resolution (Phase 6) replaces this
        # via set_tenant_analytics_resolver() at app startup.
        _analytics_cfg: dict[str, Any] = {}
        _raw_manifest = getattr(builder, "manifest_raw", None)
        if isinstance(_raw_manifest, dict):
            _analytics_cfg = _raw_manifest.get("analytics", {}) or {}

        _dsl_consent = appspec.analytics.consent if appspec.analytics else None
        _jurisdiction = (
            (_dsl_consent.default_jurisdiction if _dsl_consent else None)
            or _analytics_cfg.get("default_jurisdiction")
            or "EU"
        )
        _override = (_dsl_consent.consent_override if _dsl_consent else None) or _analytics_cfg.get(
            "consent_override"
        )
        _privacy_url = _analytics_cfg.get("privacy_page_url", "/privacy")
        _cookie_url = _analytics_cfg.get("cookie_policy_url")

        # Register the default app-wide resolver unless the application
        # has already installed a custom tenant resolver (via startup hook).
        if get_tenant_analytics_resolver() is None:
            set_tenant_analytics_resolver(
                make_app_wide_resolver(
                    appspec.analytics,
                    default_residency=_jurisdiction,
                    default_override=_override,
                    privacy_page_url=_privacy_url,
                    cookie_policy_url=_cookie_url,
                )
            )

        consent_router = create_consent_routes(
            default_jurisdiction=_jurisdiction,
            consent_override=_override,
            privacy_page_url=_privacy_url,
            cookie_policy_url=_cookie_url,
        )
        app.include_router(consent_router)
        logger.info(
            "  Consent banner: /_dazzle/consent, /_dazzle/consent/state, /_dazzle/consent/banner"
        )
    except ImportError as e:
        logger.warning("Consent routes not available: %s", e)

    # ---- 7. Schedule sync to process adapter ----
    if builder.process_adapter is not None and appspec.schedules:
        if hasattr(builder.process_adapter, "sync_schedules_from_appspec"):
            count = builder.process_adapter.sync_schedules_from_appspec(appspec)
            if count:
                adapter_name = type(builder.process_adapter).__name__
                logger.info("Synced %s DSL schedule(s) to %s", count, adapter_name)

    # ---- 8. Error-page handlers ----
    # Registered UNCONDITIONALLY (#1536): the styled 403/404/500 pages were
    # previously gated on a sitespec being present, so any app without a
    # marketing site served raw JSON to the browser on every denial — the
    # taste-panel judges scored those pages 1.3/10, and rightly so.
    try:
        from dazzle.http.runtime.exception_handlers import register_site_error_handlers

        register_site_error_handlers(
            app, sitespec_data or {}, project_root=project_root, appspec=appspec
        )
    except ImportError:
        pass

    # ---- 9. Route validation ----
    try:
        from dazzle.http.runtime.route_validator import validate_app_links, validate_routes

        validate_routes(app)
        # #1426: every /app drill-down link must resolve to a mounted detail route.
        # Warn by default; DAZZLE_STRICT_LINKS makes it a hard boot failure.
        validate_app_links(app, appspec)
    except ImportError:
        pass


# =============================================================================
# Production Factory (Heroku, etc.)
# =============================================================================


def create_app_factory(
    process_adapter_class: type | None = None,
) -> "FastAPI":
    """
    ASGI factory for production deployment.

    Creates a FastAPI application by loading the DSL spec from the project
    directory and configuring from environment variables. Designed for use
    with Uvicorn's --factory flag.

    Args:
        process_adapter_class: Custom ProcessAdapter class.
            Can also be set via DAZZLE_PROCESS_ADAPTER env var:
            - "eventbus" -> EventBusProcessAdapter (recommended with REDIS_URL)
            - "temporal" -> TemporalAdapter

    Environment Variables:
        DAZZLE_PROJECT_ROOT: Project root directory (default: current directory)
        DATABASE_URL: PostgreSQL connection URL (Heroku format supported)
        AUTH_DATABASE_URL: PostgreSQL URL for auth DB (defaults to DATABASE_URL)
        REDIS_URL: Redis connection URL (for sessions/cache)
        DAZZLE_ENV: Environment name (development/staging/production)
        DAZZLE_SECRET_KEY: Secret key for sessions/tokens
        DAZZLE_ENABLE_PROCESSES: Enable/disable process workflows (default: "true")
        DAZZLE_PROCESS_ADAPTER: Process adapter type ("eventbus", "temporal")
        DAZZLE_AUDIT_INTEGRITY: Audit-log tamper-evidence mode (#1206).
            "none" (default) | "hash_chain". Overrides `[audit] integrity`
            in `dazzle.toml`. See `docs/guides/security.md` T5.
        DAZZLE_SECURITY_PROFILE: Security profile override (#1235).
            "basic" | "standard" | "strict". Overrides the DSL-declared
            `app { security_profile: ... }`. Drives rate limiting, CSRF,
            and upload-size policy.

    Usage:
        uvicorn dazzle.http.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT

    Multi-worker (production):
        uvicorn dazzle.http.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers 4

    Procfile example:
        web: uvicorn dazzle.http.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-4}

    Returns:
        FastAPI application configured for production
    """

    # Determine project root
    project_root = Path(os.environ.get("DAZZLE_PROJECT_ROOT", ".")).resolve()
    manifest_path = project_root / "dazzle.toml"

    if not manifest_path.exists():
        raise RuntimeError(
            f"dazzle.toml not found at {manifest_path}. "
            "Set DAZZLE_PROJECT_ROOT to the project directory."
        )

    # Import Dazzle core modules (deferred to avoid circular imports)
    try:
        from dazzle.core.errors import DazzleError, ParseError
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle.core.sitespec_loader import load_sitespec_with_copy, sitespec_exists
    except ImportError as e:
        raise RuntimeError(
            f"Dazzle core modules not available: {e}. "
            "Ensure dazzle is installed: pip install dazzle"
        )

    # Load manifest
    logger.info("Loading Dazzle project from %s", project_root)
    manifest = load_manifest(manifest_path)

    # Resolve DATABASE_URL: env → dazzle.toml [database] → default

    database_url = resolve_database_url(manifest)
    logger.info("Database URL resolved (%s chars)", len(database_url))

    # Parse REDIS_URL (Heroku format: redis://h:password@host:port)
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        logger.info("Redis URL configured")

    # Determine environment. This factory (uvicorn --factory) treats an unset
    # DAZZLE_ENV as production — pin it so the downstream fail-closed auth guard
    # (which reads DAZZLE_ENV directly) sees the same intent (#1420).

    pin_production_env()
    dazzle_env = os.environ.get("DAZZLE_ENV", "production")
    enable_dev_mode = dazzle_env == "development"
    enable_test_mode = dazzle_env in ("development", "test")

    # Process workflow support (can be disabled via env var)
    enable_processes = os.environ.get("DAZZLE_ENABLE_PROCESSES", "true").lower() == "true"

    # Audit-log tamper-evidence (#1206): env var beats manifest beats default.
    # `DAZZLE_AUDIT_INTEGRITY` overrides `[audit] integrity` in dazzle.toml.
    # Both paths fall through `build_server_config` which validates the value.
    audit_integrity = os.environ.get(
        "DAZZLE_AUDIT_INTEGRITY",
        getattr(manifest, "audit_integrity", "none"),
    )

    # Security profile (#1235): env var beats DSL-declared profile beats default.
    # `DAZZLE_SECURITY_PROFILE` overrides `app { security_profile: ... }` in the
    # DSL. If both are unset, build_server_config falls through to "basic".
    security_profile_override = os.environ.get("DAZZLE_SECURITY_PROFILE") or None

    # Parse DSL and build spec. Pass `known_renderers=` so the linker
    # rejects `render: <unknown>` clauses against the framework defaults
    # PLUS any project-declared extras (`[renderers] extra` in
    # dazzle.toml) — see `dazzle.core.renderer_registry.known_renderer_names`
    # (#1116).

    try:
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(
            modules,
            manifest.project_root,
            known_renderers=known_renderer_names(manifest),
        )
    except (ParseError, DazzleError) as e:
        raise RuntimeError(f"Failed to parse DSL: {e}")

    # Load SiteSpec if available (merges copy.md content if present)
    sitespec_data = None
    if sitespec_exists(project_root):
        try:
            sitespec = load_sitespec_with_copy(project_root)
            sitespec_data = sitespec.model_dump()
            logger.info("Loaded SiteSpec with %s pages", len(sitespec.pages))
        except Exception as e:
            logger.warning("Failed to load sitespec.yaml: %s", e)

    # Extract personas with default routes for auth redirect (#255)

    persona_routes = compute_persona_default_routes(
        appspec.personas, appspec.workspaces, appspec.rhythms, appspec.surfaces
    )
    personas = [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "goals": p.goals,
            "default_route": persona_routes.get(p.id),
        }
        for p in appspec.personas
    ]

    # Resolve process adapter class from parameter or environment
    resolved_adapter_class = process_adapter_class
    if resolved_adapter_class is None:
        adapter_env = os.environ.get("DAZZLE_PROCESS_ADAPTER", "").lower()
        if adapter_env == "eventbus":
            try:
                from dazzle.core.process import EventBusProcessAdapter

                resolved_adapter_class = EventBusProcessAdapter
                logger.info("Using EventBusProcessAdapter (DAZZLE_PROCESS_ADAPTER=eventbus)")
            except ImportError:
                logger.warning("EventBusProcessAdapter requested but not available (install redis)")
        elif adapter_env == "temporal":
            try:
                from dazzle.core.process import TemporalAdapter

                resolved_adapter_class = TemporalAdapter
                logger.info("Using TemporalAdapter (DAZZLE_PROCESS_ADAPTER=temporal)")
            except ImportError:
                logger.warning("TemporalAdapter requested but not available (install temporalio)")
        # Default: None means auto-detect (requires REDIS_URL for EventBus)

    # Build unified server config
    config = build_server_config(
        appspec,
        database_url=database_url if database_url else None,
        enable_auth=manifest.auth.enabled,
        auth_config=manifest.auth if manifest.auth.enabled else None,
        enable_files=True,
        files_path=project_root / ".dazzle" / "uploads",
        enable_test_mode=enable_test_mode,
        services_dir=project_root / "services",
        enable_dev_mode=enable_dev_mode,
        enable_processes=enable_processes,
        process_adapter_class=resolved_adapter_class,
        tenant_config=manifest.tenant if manifest.tenant.isolation != "none" else None,
        personas=personas,
        scenarios=[],
        sitespec_data=sitespec_data,
        project_root=project_root,
        storage_defs=getattr(manifest, "storage_defs", None),
        audit_integrity=audit_integrity,
        security_profile=security_profile_override,
    )

    # Build and return the FastAPI app
    builder = DazzleBackendApp(appspec, config=config)
    app = builder.build()

    # Get theme CSS for page routes
    theme_css = ""
    try:
        from dazzle.page.runtime.css_loader import get_bundled_css

        theme_css = get_bundled_css()
    except Exception:
        logger.debug("Failed to load bundled theme CSS", exc_info=True)

    assemble_post_build_routes(
        app,
        appspec,
        builder,
        project_root=project_root,
        sitespec_data=sitespec_data,
        theme_css=theme_css,
        dark_mode_toggle=manifest.dark_mode_toggle,
    )

    _stash_tenant_state_marker(app, appspec)
    _mount_tenant_resolution_middleware(app, appspec, builder)

    _invoke_project_post_build_hook(app)

    # Log startup info
    logger.info("Dazzle app '%s' ready", appspec.name)
    logger.info("  Entities: %s", len(appspec.domain.entities))
    logger.info("  Surfaces: %s", len(appspec.surfaces))
    logger.info("  Environment: %s", dazzle_env)
    logger.info("  Database: PostgreSQL")
    if enable_dev_mode:
        logger.info("  Dev mode: enabled")

    return app
