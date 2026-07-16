"""
Runtime server - creates and runs a FastAPI application from AppSpec.

This module provides the main entry point for running a Dazzle backend application.
"""

import contextlib
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from pydantic import BaseModel

from dazzle.core.capabilities import resolve_capabilities
from dazzle.core.db_url import add_psycopg_driver, normalise_postgres_scheme
from dazzle.core.environment import is_production
from dazzle.core.ir import AppSpec, EntitySpec, TenancyMode
from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.manifest import load_manifest
from dazzle.core.strings import entity_slug as _entity_slug
from dazzle.core.validator import validate_storage_refs
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.converters.surface_converter import convert_surfaces_to_services
from dazzle.http.runtime.audit_wiring import register_audit_callbacks
from dazzle.http.runtime.auth import (
    AuthMiddleware,
    AuthStore,
)
from dazzle.http.runtime.auth.partition_root import (
    build_partition_hierarchy,
    reconcile_membership_partition_roots,
)
from dazzle.http.runtime.csrf import apply_csrf_protection
from dazzle.http.runtime.document_routes import create_document_routes
from dazzle.http.runtime.exception_handlers import register_exception_handlers
from dazzle.http.runtime.file_routes import create_file_routes, create_static_file_routes
from dazzle.http.runtime.file_storage import FileService
from dazzle.http.runtime.integration_manager import IntegrationManager, _convert_channels
from dazzle.http.runtime.lifespan_hooks import init_lifespan_registry, register_lifespan_hook
from dazzle.http.runtime.migrations import MigrationPlan
from dazzle.http.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
)
from dazzle.http.runtime.page_routes import build_app_page_context
from dazzle.http.runtime.param_store import ParamResolver
from dazzle.http.runtime.policy import EntityPolicyInfo, PolicyRegistry
from dazzle.http.runtime.predicate_compiler import collect_user_attr_refs
from dazzle.http.runtime.rate_limit import apply_rate_limiting
from dazzle.http.runtime.relation_loader import RelationLoader, RelationRegistry
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.repository import RepositoryFactory
from dazzle.http.runtime.rls_schema import build_all_rls_ddl, physical_cast_overrides
from dazzle.http.runtime.route_generator import RouteGenerator
from dazzle.http.runtime.route_validator import validate_routes
from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names
from dazzle.http.runtime.search_schema import build_search_index_ddl
from dazzle.http.runtime.security_middleware import apply_security_middleware
from dazzle.http.runtime.service_generator import CRUDService, ServiceFactory
from dazzle.http.runtime.service_loader import ServiceLoader
from dazzle.http.runtime.services import RuntimeServices
from dazzle.http.runtime.sse_stream import SSEStreamManager, create_sse_routes
from dazzle.http.runtime.sse_wiring import LazyFrameworkBus, register_sse_callbacks
from dazzle.http.runtime.storage import build_entity_storage_bindings
from dazzle.http.runtime.subsystems import SubsystemContext
from dazzle.http.runtime.subsystems.auth import AuthSubsystem
from dazzle.http.runtime.subsystems.channels import ChannelsSubsystem
from dazzle.http.runtime.subsystems.events import EventsSubsystem
from dazzle.http.runtime.subsystems.llm_queue import LLMQueueSubsystem
from dazzle.http.runtime.subsystems.process import ProcessSubsystem
from dazzle.http.runtime.subsystems.seed import SeedSubsystem
from dazzle.http.runtime.subsystems.sla import SLASubsystem
from dazzle.http.runtime.subsystems.system_routes import SystemRoutesSubsystem
from dazzle.http.runtime.tenant_isolation import register_rls_user_attr_names
from dazzle.http.runtime.usage_routes import create_usage_routes
from dazzle.http.runtime.usage_signal import UsageCollector, UsageSignalMiddleware
from dazzle.http.runtime.workspace_aggregation import (  # noqa: F401
    _compute_aggregate_metrics,
    _fetch_count_metric,
    _parse_simple_where,
)
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns as _build_entity_columns,  # noqa: F401
)
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns_full as _build_entity_columns_full,  # noqa: F401
)
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns as _build_surface_columns,  # noqa: F401
)
from dazzle.http.runtime.workspace_columns import (
    field_kind_to_col_type as _field_kind_to_col_type,  # noqa: F401
)
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext  # noqa: F401
from dazzle.http.runtime.workspace_handlers import (  # noqa: F401
    _fetch_region_json,
    _workspace_batch_handler,
)
from dazzle.http.runtime.workspace_region_handler import _workspace_region_handler  # noqa: F401
from dazzle.http.runtime.workspace_route_builder import WorkspaceRouteBuilder
from dazzle.page.runtime.peek_resolver import resolve_peek_mode
from dazzle.page.runtime.theme import install_theme_middleware
from dazzle.perf.bootstrap import maybe_configure_tracer
from dazzle.perf.instrument import instrument_app

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
    from dazzle.core.manifest import StorageConfig, TenantConfig
    from dazzle.core.process.adapter import ProcessAdapter
    from dazzle.http.events.framework import EventFramework
    from dazzle.http.runtime.audit_log import AuditLogger
    from dazzle.http.runtime.auth_detection import AuthConfig
    from dazzle.http.runtime.pg_backend import PostgresBackend
    from dazzle.http.runtime.process_manager import ProcessManager
    from dazzle.http.runtime.sla_manager import SLAManager
    from dazzle.signing.service import PdfBranding

logger = logging.getLogger(__name__)


# =============================================================================
# Server Configuration
# =============================================================================


@dataclass
class ServerConfig:
    """
    Configuration for DazzleBackendApp.

    Groups all initialization options into a single object for cleaner APIs.
    """

    # Database settings
    database_url: str | None = None  # PostgreSQL URL (e.g. postgresql://user:pass@host/db)

    # Authentication settings
    enable_auth: bool = False
    auth_config: "AuthConfig | None" = None  # from manifest (for OAuth providers)
    # auth Plan 1c: lazily provision a single default Organization + one
    # membership per identity at activation (invisible single-org degradation).
    # Default False — non-breaking; Plan 1d turns it on for migrated apps and
    # the new-app scaffolder defaults it on.
    auto_provision_single_org: bool = False

    # File upload settings
    enable_files: bool = False
    files_path: Path = field(default_factory=lambda: Path(".dazzle/uploads"))

    # Development/testing settings
    enable_test_mode: bool = False
    services_dir: Path = field(default_factory=lambda: Path("services"))

    # Dev control plane
    enable_dev_mode: bool = False
    personas: list[dict[str, Any]] = field(default_factory=list)
    scenarios: list[dict[str, Any]] = field(default_factory=list)

    # Messaging channels (v0.9)
    enable_channels: bool = True  # Auto-enabled if channels defined in spec

    # Security (v0.11.0)
    security_profile: str = "basic"  # basic | standard | strict
    cors_origins: list[str] | None = None  # Custom CORS origins

    # SiteSpec (v0.16.0) - Public site shell
    sitespec_data: dict[str, Any] | None = None  # SiteSpec as dict
    project_root: Path | None = None  # For content file loading

    # Process/workflow support (v0.24.0)
    enable_processes: bool = True  # Enable process workflow execution
    process_adapter_class: type | None = None  # Custom ProcessAdapter class
    process_specs: "list[ProcessSpec]" = field(default_factory=list)
    schedule_specs: "list[ScheduleSpec]" = field(default_factory=list)
    entity_status_fields: dict[str, str] = field(default_factory=dict)  # entity_name → status field

    # Tenant isolation (v0.43.0)
    tenant_config: "TenantConfig | None" = None

    # Fragment sources from DSL source= annotations (v0.25.1)
    fragment_sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    # View-based list projections (v0.26.0) — entity_name -> [field_names]
    entity_list_projections: dict[str, list[str]] = field(default_factory=dict)
    # Surface search fields (v0.34.2) — entity_name -> [field_names]
    entity_search_fields: dict[str, list[str]] = field(default_factory=dict)
    # Surface filter fields (v0.44.1) — entity_name -> [field_names]
    entity_filter_fields: dict[str, list[str]] = field(default_factory=dict)
    # Auto-eager-load ref relations (v0.26.0) — entity_name -> [relation_names]
    entity_auto_includes: dict[str, list[str]] = field(default_factory=dict)
    # FK field → target entity mapping for dotted-path scope resolution (#556)
    entity_ref_targets: dict[str, dict[str, str]] = field(default_factory=dict)

    # v0.61.107 (#932): per-name [storage.<name>] config blocks from dazzle.toml.
    # Propagated by build_server_config() so DazzleBackendApp can wire upload-ticket
    # routes when entities have `field foo: file storage=<name>` bindings.
    storage_defs: "dict[str, StorageConfig]" = field(default_factory=dict)

    # CSRF exempt paths (#1212). Opt-in extension for downstream apps that need
    # to mark internal POST endpoints (e.g. a public-read GraphQL gateway
    # authenticated by Bearer) as exempt without mutating
    # `app.state.csrf_config.exempt_paths` after boot. Merged with the
    # framework defaults in `csrf.configure_csrf_for_profile`; duplicates are
    # de-duped. The default exempt list is documented in
    # `docs/guides/security.md` section 3 T3 — `POST /graphql` is NOT in it.
    csrf_exempt_paths: list[str] = field(default_factory=list)

    # Phase 2 (declarative CSRF §4.2): extra origins to admit even when they
    # don't match the request Host (e.g. a same-site embedder). Threaded into
    # `csrf.configure_csrf_for_profile` as `extra_trusted_origins`; merged with
    # the (empty) default and de-duped.
    csrf_trusted_origins: list[str] = field(default_factory=list)

    # Audit log tamper-resistance (#1197). Opt-in. Default "none" preserves
    # today's behaviour exactly — no schema change, no extra SELECT-prev-hash.
    # "hash_chain" enables a per-row sha256 chain (column `row_hash`) so a
    # tampered row breaks the chain at the modified entry. See
    # `AuditLogger.verify_chain()` for offline verification.
    audit_integrity: str = "none"  # "none" | "hash_chain"


def _tenancy_metadata_kwargs(appspec: AppSpec) -> dict[str, Any]:
    """Tenant-scoping kwargs for ``build_metadata`` (RLS Phase A).

    Returns ``partition_key`` + ``tenant_scoped`` only under
    ``tenancy: mode: shared_schema``; otherwise an empty dict so the
    non-tenant ``build_metadata`` path is unchanged. An entity is
    tenant-scoped iff it carries the partition_key field (covers both
    framework-injected and hand-declared discriminators).
    """

    tenancy = appspec.tenancy
    if tenancy is None or tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA:
        return {}
    pk = tenancy.isolation.partition_key
    return {
        "partition_key": pk,
        "tenant_scoped": scoped_entity_names(appspec.domain.entities, pk),
    }


def _compute_rls_user_attr_names(entities: list[Any]) -> set[str]:
    """App-wide set of ``current_user`` attrs referenced by any scope rule (Phase C).

    The union of
    :func:`~dazzle.http.runtime.predicate_compiler.collect_user_attr_refs` over
    every scoped entity's ``access.scopes`` predicates. This is the exact set of
    ``dazzle.user_<attr>`` GUCs the runtime must set per request so the per-verb
    scope policies' ``current_setting('dazzle.user_<attr>', true)`` resolves.

    Registered once at startup (``register_rls_user_attr_names``) so the auth
    dependency resolves only these attrs per request without re-walking trees.
    A ``current_user`` reference (the user's PK) contributes ``"id"``. Entities
    without scope rules contribute nothing.
    """

    names: set[str] = set()
    for entity in entities:
        access = getattr(entity, "access", None)
        scopes = getattr(access, "scopes", None) if access is not None else None
        if not scopes:
            continue
        for rule in scopes:
            predicate = getattr(rule, "predicate", None)
            if predicate is not None:
                names |= collect_user_attr_refs(predicate)
    return names


def _maybe_configure_tracer() -> None:
    """Configure the OTel tracer when ``dazzle perf trace`` set the env.

    Delegates to :func:`dazzle.perf.bootstrap.maybe_configure_tracer`
    which is also called at CLI entry (``dazzle/cli/__init__.py``) so
    that framework-boot spans (``dsl.parse``, route generation) are
    captured before the FastAPI app is built (#1158).  Keeping this
    call inside ``_create_app`` is harmless — the function is idempotent
    and the CLI path fires first.
    """

    maybe_configure_tracer()


def _maybe_instrument_for_perf(app: Any) -> None:
    """Apply ``dazzle perf`` instrumentation when ``DAZZLE_PERF_ENABLED``
    is set. The env var is the only signal — `dazzle perf trace` sets
    it before spawning the runtime; humans starting the server directly
    don't pay the instrumentation cost.
    """
    import os

    if os.environ.get("DAZZLE_PERF_ENABLED") != "1":
        return

    instrument_app(app)


# =============================================================================
# Application Builder
# =============================================================================


def _any_workspace_live(workspaces: list[Any]) -> bool:
    """#1399 slice 1 — True if any workspace opted into SSE live push."""
    return any(getattr(ws, "live", False) for ws in workspaces)


class DazzleBackendApp:
    """
    Dazzle Backend Application.

    Creates a complete FastAPI application from an AppSpec.
    """

    def __init__(
        self,
        appspec: AppSpec,
        config: ServerConfig | None = None,
        *,
        database_url: str | None = None,
        enable_auth: bool | None = None,
        auth_config: "AuthConfig | None" = None,
        enable_files: bool | None = None,
        files_path: str | Path | None = None,
        enable_test_mode: bool | None = None,
        services_dir: str | Path | None = None,
        # Dev control plane
        enable_dev_mode: bool | None = None,
        personas: list[dict[str, Any]] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        # SiteSpec (v0.16.0)
        sitespec_data: dict[str, Any] | None = None,
        project_root: str | Path | None = None,
        # Extra static directories to prepend to the framework's /static mount.
        # Consumer apps that mount their own /static AFTER .build() used to be
        # silently shadowed (issue #793); pass paths here to have them served first.
        extra_static_dirs: list[str | Path] | None = None,
        # v0.61.106 (#932 cycle 3): per-name [storage.<name>] config
        # blocks loaded from dazzle.toml. When non-empty AND the appspec
        # has any `field foo: file storage=<name>` bindings, the
        # framework auto-generates `POST /api/{entity}/upload-ticket`
        # routes that mint pre-signed POST policies via the
        # registered StorageProvider for each storage. None / empty
        # = no auto-routes (existing behaviour preserved).
        storage_defs: dict[str, "StorageConfig"] | None = None,
    ):
        """
        Initialize the backend application.

        Args:
            appspec: Dazzle AppSpec (parsed IR)
            config: Server configuration object (preferred)
            database_url: PostgreSQL connection URL (or set DATABASE_URL env var)
            enable_auth: Whether to enable authentication (default: False)
            enable_files: Whether to enable file uploads (default: False)
            files_path: Path for file storage (default: .dazzle/uploads)
            enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
            services_dir: Path to domain service stubs directory (default: services/)
            enable_dev_mode: Enable dev control plane (default: False)
            personas: List of persona configurations for dev mode
            scenarios: List of scenario configurations for dev mode
            sitespec_data: SiteSpec as dict for public site shell (v0.16.0)
            project_root: Project root for content file loading (v0.16.0)
        """
        # Use config if provided, otherwise build from legacy parameters
        if config is None:
            config = ServerConfig()

        import os

        # Convert AppSpec to runtime-ready specs

        self._appspec = appspec
        self._entities = convert_entities(appspec.domain.entities)
        # RLS tenancy Phase C — register the app-wide set of current_user attrs
        # referenced by any scope rule (only under shared_schema; empty otherwise).
        # The auth dependency resolves exactly these into dazzle.user_<attr> GUCs
        # per request. Registered unconditionally (empty when not applicable) so a
        # prior app instance in the same process can't leak a stale set.
        self._rls_user_attr_names = self._compute_rls_user_attr_names_for_appspec()

        register_rls_user_attr_names(self._rls_user_attr_names)
        self._service_specs, self._endpoint_specs = convert_surfaces_to_services(
            appspec.surfaces, appspec.domain
        )
        self._channels = _convert_channels(appspec.channels)
        self._database_url = database_url or config.database_url or os.environ.get("DATABASE_URL")
        self._enable_auth = enable_auth if enable_auth is not None else config.enable_auth
        self._auth_config = auth_config if auth_config is not None else config.auth_config
        self._enable_files = enable_files if enable_files is not None else config.enable_files
        self._files_path = Path(files_path) if files_path else config.files_path
        self._enable_test_mode = (
            enable_test_mode if enable_test_mode is not None else config.enable_test_mode
        )
        self._services_dir = Path(services_dir) if services_dir else config.services_dir
        # Dev control plane
        self._enable_dev_mode = (
            enable_dev_mode if enable_dev_mode is not None else config.enable_dev_mode
        )
        self._personas = personas if personas is not None else config.personas
        self._scenarios = scenarios if scenarios is not None else config.scenarios
        # SiteSpec (v0.16.0)
        self._sitespec_data = sitespec_data if sitespec_data is not None else config.sitespec_data
        self._project_root = Path(project_root) if project_root else config.project_root
        self._extra_static_dirs: list[Path] = (
            [Path(d) for d in extra_static_dirs] if extra_static_dirs else []
        )
        # v0.61.106 (#932 cycle 3): storage config + lazy registry.
        # Prefer kwarg, fall back to config — matches every other field's precedence.
        _resolved_storage_defs = storage_defs if storage_defs is not None else config.storage_defs
        self._storage_defs: dict[str, StorageConfig] = dict(_resolved_storage_defs or {})
        self._storage_registry: Any = None  # built in _wire_storage_routes()
        self._app: FastAPI | None = None
        self._models: dict[str, type[BaseModel]] = {}
        self._schemas: dict[str, dict[str, type[BaseModel]]] = {}
        self._services: dict[str, Any] = {}
        self._create_invokers: dict[str, Any] = {}  # #1422: in-process create invokers
        self._service_factory: ServiceFactory | None = None
        self._repositories: dict[str, Any] = {}
        self._db_manager: PostgresBackend | None = None
        self._auth_store: AuthStore | None = None
        self._auth_middleware: AuthMiddleware | None = None
        self._audit_logger: AuditLogger | None = None
        self._usage_collector: Any = None  # UsageCollector | None (ADR-0050)
        self._file_service: FileService | None = None
        self._last_migration: MigrationPlan | None = None
        self._start_time: datetime | None = None
        self._service_loader: ServiceLoader | None = None
        # Messaging channels (v0.9)
        self._enable_channels = config.enable_channels
        # Delegate instances (created lazily in _setup_optional_features)
        self._integration_mgr: IntegrationManager | None = None
        self._workspace_builder: WorkspaceRouteBuilder | None = None
        # Security (v0.11.0)
        self._security_profile = config.security_profile
        self._cors_origins = config.cors_origins
        # #1212 — opt-in extra CSRF-exempt paths from ServerConfig.
        self._csrf_exempt_paths = list(config.csrf_exempt_paths)
        # Phase 2 — opt-in extra CSRF-trusted origins from ServerConfig.
        self._csrf_trusted_origins = list(config.csrf_trusted_origins)
        # Event system (v0.18.0)
        self._event_framework: EventFramework | None = None
        # NOTE: _sitespec_data and _project_root are already set above (lines 201-203)
        # with proper parameter precedence over config defaults
        # Process/workflow support (v0.24.0)
        self._enable_processes = config.enable_processes
        self._process_adapter_class = config.process_adapter_class  # Custom adapter class
        self._process_specs: list[ProcessSpec] = config.process_specs
        self._schedule_specs: list[ScheduleSpec] = config.schedule_specs
        self._entity_status_fields: dict[str, str] = config.entity_status_fields
        self._process_manager: ProcessManager | None = None
        self._process_adapter: ProcessAdapter | None = None
        self._sla_manager: SLAManager | None = None
        # Tenant isolation (v0.43.0)
        self._tenant_config = config.tenant_config
        # Fragment sources from DSL source= annotations (v0.25.1)
        self._fragment_sources: dict[str, dict[str, Any]] = config.fragment_sources
        # View-based list projections (v0.26.0)
        self._entity_list_projections: dict[str, list[str]] = config.entity_list_projections
        # Surface search fields (v0.34.2)
        self._entity_search_fields: dict[str, list[str]] = config.entity_search_fields
        # Surface filter fields (v0.44.1)
        self._entity_filter_fields: dict[str, list[str]] = config.entity_filter_fields
        # Auto-eager-load ref relations (v0.26.0)
        self._entity_auto_includes: dict[str, list[str]] = config.entity_auto_includes
        # FK→entity mapping for dotted-path scope resolution (#556)
        self._entity_ref_targets: dict[str, dict[str, str]] = config.entity_ref_targets
        # Keep full config for subsystem context
        self._config: ServerConfig = config
        # Subsystem plugin infrastructure (v0.42.0)
        self._subsystem_ctx: Any | None = (
            None  # SubsystemContext, set in build() after _setup_optional_features
        )
        self._subsystems: list[Any] = self._build_default_subsystems()

    # ------------------------------------------------------------------
    # Subsystem plugin infrastructure
    # ------------------------------------------------------------------

    def _build_default_subsystems(self) -> list[Any]:
        """Create the ordered list of default subsystem plugins."""

        return [
            AuthSubsystem(),
            EventsSubsystem(),
            ChannelsSubsystem(),
            ProcessSubsystem(),
            SLASubsystem(),
            LLMQueueSubsystem(),
            SeedSubsystem(),
            SystemRoutesSubsystem(),
        ]

    def _resolve_capabilities(self) -> Any:
        """Resolve opt-in capabilities from the project manifest (#1342).

        Returns a ``ResolvedCapabilities`` (active = declared ∧ available), or
        ``None`` when there is no manifest to read. Raises
        ``CapabilityUnavailableError`` if a capability is declared but its
        package isn't installed — a loud boot failure with the install runbook.
        """

        if self._project_root is None:
            return resolve_capabilities([])
        manifest_path = self._project_root / "dazzle.toml"
        if not manifest_path.is_file():
            return resolve_capabilities([])

        declared = load_manifest(manifest_path).capabilities.enabled
        return resolve_capabilities(list(declared))

    def _warn_unregistered_renderers(self) -> None:
        """#1413: warn at boot when a custom renderer declared in dazzle.toml
        ``[renderers] extra`` has no runtime handler registered.

        Declaring a renderer (link-time, validated by build_appspec) and
        registering its handler (runtime, ``services.renderer_registry.register``)
        are separate steps. A declared-but-unregistered renderer passes
        ``dazzle validate``/``lint`` but 500s with a FragmentError at first
        request. Surface the gap at the moment it matters — boot — without
        failing the boot (warning, not error).
        """
        if self._project_root is None or self._app is None:
            return
        manifest_path = self._project_root / "dazzle.toml"
        if not manifest_path.is_file():
            return

        try:
            declared = load_manifest(manifest_path).renderers.extra
        except (ValueError, OSError):
            # Best-effort warning only — a malformed/unreadable manifest is
            # surfaced loudly by the appspec build that already ran; don't let
            # this advisory check perturb boot.
            return
        if not declared:
            return
        services = getattr(self._app.state, "services", None)
        registry = getattr(services, "renderer_registry", None)
        if registry is None:
            return
        registered = set(registry.registered_names())
        orphans = sorted(r for r in declared if r not in registered)
        if orphans:
            logger.warning(
                "[dazzle] custom renderer(s) declared in dazzle.toml "
                "[renderers] extra but never registered at runtime: %s — they "
                "will 500 (FragmentError) at request time. Wire "
                "services.renderer_registry.register(name=..., handler=...) at "
                "startup (e.g. your register_all() via register_lifespan_hook). "
                "Declared-but-unregistered renderers pass validate/lint but "
                "fail at request (#1413).",
                ", ".join(orphans),
            )

    def _build_subsystem_context(self, auth_dep: Any = None, optional_auth_dep: Any = None) -> Any:
        """Build SubsystemContext from current DazzleBackendApp state."""

        assert self._app is not None

        # Resolve opt-in capabilities (#1342) from the project manifest. Raises
        # CapabilityUnavailableError (loud boot failure with the install runbook)
        # if a capability is declared but its package isn't installed.
        resolved_capabilities = self._resolve_capabilities()

        return SubsystemContext(
            app=self._app,
            appspec=self._appspec,
            config=self._config,
            services=self._services,
            repositories=self._repositories,
            entities=self._entities,
            channels=self._channels,
            db_manager=self._db_manager,
            auth_middleware=self._auth_middleware,
            enable_auth=self._enable_auth,
            enable_test_mode=self._enable_test_mode,
            auth_store=self._auth_store,
            auth_dep=auth_dep,
            optional_auth_dep=optional_auth_dep,
            auth_config=self._auth_config,
            database_url=self._database_url or "",
            security_profile=self._security_profile,
            project_root=self._project_root,
            capabilities=resolved_capabilities,
            extra_static_dirs=list(self._extra_static_dirs),
            last_migration=self._last_migration,
            # Resolved instance vars (may differ from config when passed as constructor kwargs)
            sitespec_data=self._sitespec_data,
            enable_files=self._enable_files,
            files_path=self._files_path,
            services_dir=self._services_dir,
        )

    def _run_subsystems(self) -> None:
        """Call startup() on each registered subsystem plugin in order."""
        assert self._subsystem_ctx is not None
        for plugin in self._subsystems:
            try:
                plugin.startup(self._subsystem_ctx)
            except Exception as exc:  # pragma: no cover
                logging.getLogger(__name__).warning(
                    "Subsystem '%s' startup failed: %s", getattr(plugin, "name", "?"), exc
                )
        # Sync mutable outputs back to DazzleBackendApp attributes so existing
        # properties (channel_manager, process_manager, etc.) still work.
        ctx = self._subsystem_ctx
        if ctx.event_framework is not None:
            self._event_framework = ctx.event_framework
        if ctx.process_manager is not None:
            self._process_manager = ctx.process_manager
        if ctx.process_adapter is not None:
            self._process_adapter = ctx.process_adapter
        if ctx.sla_manager is not None:
            self._sla_manager = ctx.sla_manager

    # ------------------------------------------------------------------
    # Build phases — called in order by build()
    # ------------------------------------------------------------------

    def _reconcile_membership_partition_roots(self) -> None:
        """Backfill/refresh membership ``partition_root_id`` at boot (#1463).

        No-op unless auth is enabled with a tenant hierarchy. Wrapped so a
        reconciliation failure (e.g. a transient DB error) never aborts boot — it
        degrades closed (un-backfilled leaf memberships bind their raw tenant →
        fewer rows, never a cross-tenant leak), so a logged warning is the right
        severity. New memberships are still resolved correctly at write time.
        """
        store = self._auth_store
        if store is None:
            return
        hierarchy = getattr(store, "_partition_hierarchy", None)
        if hierarchy is None:
            return
        try:
            reconcile_membership_partition_roots(store, hierarchy)
        except Exception:  # noqa: BLE001 — boot must not fail on a fail-closed backfill
            logger.warning(
                "membership partition-root reconciliation failed; leaf memberships "
                "bind their raw tenant until the next successful boot (fail-closed)",
                exc_info=True,
            )

    @contextlib.asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Modern FastAPI lifespan replacing the deprecated ``on_event`` hooks.

        Reads instance state at *startup* time (after ``build()`` has fully
        populated ``self._db_manager`` / ``self._audit_logger`` / pool sizes),
        so it is safe to attach at ``FastAPI(...)`` construction even though
        those attributes are set in later build phases.

        Startup: open the DB connection pool (#438), then start the audit
        logger if one was configured. The audit logger's ``start()`` is
        deferred to here so a running event loop is guaranteed (#1214) — Py3.12
        removed the implicit event-loop acquisition that the prior sync
        construction path relied on.

        Shutdown: stop the audit logger (if configured), then close the pool —
        mirroring the previous ordering (pool opens first, closes last).
        """
        from dazzle.http.runtime.lifespan_hooks import (
            run_legacy_router_events,
            run_shutdown_hooks,
            run_startup_hooks,
        )

        pool_min = int(os.environ.get("DAZZLE_DB_POOL_MIN", "2"))
        pool_max = int(os.environ.get("DAZZLE_DB_POOL_MAX", "10"))
        assert self._db_manager is not None
        self._db_manager.open_pool(min_size=pool_min, max_size=pool_max)
        if self._audit_logger is not None:
            self._audit_logger.start()
        if self._usage_collector is not None:
            self._usage_collector.start()  # ADR-0050 first-party usage signal
        # Subsystem startup hooks (seed/events/queues/sla/process/channels/…) run after the
        # pool is open so they can use the DB. Replaces the @on_event hooks a custom lifespan
        # silently dropped.
        await run_startup_hooks(app)
        # #1463: backfill/refresh membership partition roots now that the tenant
        # tables exist (after schema setup + seed hooks). Degrades closed — a
        # failure leaves leaf memberships binding their raw tenant (fewer rows,
        # never more), so log and continue rather than aborting boot.
        self._reconcile_membership_partition_roots()
        # #1366: HOST-APP @app.on_event handlers — drained with original
        # FastAPI semantics (a failed startup hook aborts boot) after the
        # framework is up. Each emits a deprecation warning pointing at
        # dazzle.register_lifespan_hook, the supported path.
        await run_legacy_router_events(app, "startup")
        # #1413: after all registration (framework defaults + project
        # register_all via startup hooks/legacy events), warn on any custom
        # renderer declared in dazzle.toml that never got a runtime handler.
        self._warn_unregistered_renderers()
        try:
            yield
        finally:
            # Host shuts down first (proper nesting), then framework hooks,
            # then audit logger, then the pool.
            await run_legacy_router_events(app, "shutdown")
            await run_shutdown_hooks(app)
            if self._audit_logger is not None:
                await self._audit_logger.stop()
            if self._usage_collector is not None:
                await self._usage_collector.stop()  # final flush of queued usage events
            self._db_manager.close_pool()

    def _create_app(self) -> None:
        """Create the FastAPI app instance and apply middleware."""
        _maybe_configure_tracer()
        self._app = FastAPI(
            title=self._appspec.name,
            description=self._appspec.title or f"Dazzle Backend: {self._appspec.name}",
            version=self._appspec.version,
            lifespan=self._lifespan,
        )
        # Subsystems register startup/shutdown work here (replacing @app.on_event, which
        # a custom lifespan silently ignores). Initialised before _run_subsystems runs.

        init_lifespan_registry(self._app)
        _maybe_instrument_for_perf(self._app)

        # Attach runtime service container (v0.49.0, #673)

        services = RuntimeServices()
        register_default_renderers(services)
        services.app_spec = self._appspec
        self._app.state.services = services

        # Phase 4 app-shell migration (v0.67.45): the `fragment_chrome`
        # flag is retired. Every render path went typed-Fragment-only
        # over v0.67.43 / v0.67.44. The state attribute is no longer
        # set here — readers were removed in those ships. The
        # `app.state.fragment_chrome_css_links` / `_js_scripts` /
        # `_theme` per-deployment branding overrides are NOT retired
        # — those are still consumed by the typed Page builders.

        # Security middleware (v0.11.0). v0.61.0 Phase 3: resolve active
        # analytics providers so their CSP origins are allow-listed.

        _active_providers: list[Any] = []
        if self._appspec.analytics is not None:
            from dazzle.compliance.analytics import get_provider_definition

            for inst in self._appspec.analytics.providers:
                definition = get_provider_definition(inst.name)
                if definition is not None:
                    _active_providers.append(definition)

        apply_security_middleware(
            self._app,
            self._security_profile,
            cors_origins=self._cors_origins,
            analytics_providers=_active_providers or None,
        )

        # Rate limiting (v1.0.0)

        apply_rate_limiting(self._app, self._security_profile)

        # CSRF protection (v1.0.0)

        apply_csrf_protection(
            self._app,
            self._security_profile,
            extra_exempt_paths=self._csrf_exempt_paths or None,
            extra_trusted_origins=self._csrf_trusted_origins or None,
        )

        # GZip compression (v0.33.0) — must be added before other middleware
        from starlette.middleware.gzip import GZipMiddleware

        self._app.add_middleware(GZipMiddleware, minimum_size=500)

        # Theme-variant middleware (UX-048 / UX-056 Q1) — reads the
        # `dz_theme` cookie and publishes it into a ContextVar so the
        # Jinja `theme_variant()` global can emit `<html data-theme>`
        # correctly on first paint (prevents the flash-of-light for
        # returning dark-mode users).

        install_theme_middleware(self._app)

        # Metrics middleware (v0.27.0)
        try:
            from dazzle.http.runtime.metrics import add_metrics_middleware

            add_metrics_middleware(self._app)
        except ImportError:
            pass

        # Usage-signal middleware (ADR-0050 Option A, 3a): record heading-action
        # clicks. Raw ASGI (NOT BaseHTTPMiddleware — SSE/streaming-safe, per the
        # csrf.py convention); records after the response when request.state.tenant
        # is resolved, no-op unless the `X-Dz-Usage-Action` header (set by the
        # hx-boosted heading anchors) is present.
        self._app.add_middleware(UsageSignalMiddleware)

        # Tenant isolation middleware (schema-per-tenant)
        tenant_config = self._tenant_config
        if tenant_config and tenant_config.isolation == "schema":
            from dazzle.http.runtime.tenant_middleware import (
                TenantMiddleware,
                build_resolver,
            )
            from dazzle.tenant.registry import TenantRegistry

            resolver = build_resolver(tenant_config)
            assert self._database_url is not None, "database_url required for tenant isolation"
            registry = TenantRegistry(self._database_url)
            registry.ensure_table()

            # #957 cycle 8 — pull per_tenant_config schema off the
            # linked tenancy spec so the middleware can coerce the
            # JSONB config and expose `request.state.tenant_config`.
            _per_tenant_schema: dict[str, str] = {}
            if self._appspec and self._appspec.tenancy:
                _per_tenant_schema = dict(self._appspec.tenancy.per_tenant_config)

            self._app.add_middleware(
                TenantMiddleware,
                resolver=resolver,
                registry=registry,
                per_tenant_config_schema=_per_tenant_schema,
            )

        # Exception handlers (v0.28.0)

        register_exception_handlers(self._app)

    def _migrate_tenant_schemas(self) -> None:
        """Create/update tables in each active tenant schema (#561).

        Fail-closed under ``isolation = "schema"`` (#1209): per-tenant
        failures are accumulated, logged at ERROR, and a ``RuntimeError``
        is raised at the end of the loop naming every failed schema. This
        halts boot rather than silently falling back to the ``public``
        schema and violating the declared isolation posture. Mirrors the
        audit-trail fail-closed invariant at #1172.
        """
        import logging

        from sqlalchemy import create_engine

        logger = logging.getLogger(__name__)
        assert self._database_url is not None

        try:
            from dazzle.tenant.registry import TenantRegistry

            registry = TenantRegistry(self._database_url)
            registry.ensure_table()
            tenants = registry.list()
        except Exception as exc:
            logger.warning("Could not list tenants for schema migration: %s", exc)
            return

        metadata = build_metadata(
            self._entities,
            surfaces=list(self._appspec.surfaces),
            **_tenancy_metadata_kwargs(self._appspec),
        )
        # Normalise Heroku-style postgres:// alias before adding driver suffix
        sa_url = add_psycopg_driver(normalise_postgres_scheme(self._database_url))

        failed_tenants: list[tuple[str, str]] = []

        for tenant in tenants:
            if tenant.status != "active":
                continue
            schema_name = tenant.schema_name
            if not schema_name:
                continue
            try:
                import re

                if not re.fullmatch(r"[a-zA-Z0-9_]+", schema_name):
                    logger.error("Invalid tenant schema name: %s", schema_name)
                    failed_tenants.append((schema_name, "invalid schema name"))
                    continue
                engine = create_engine(sa_url)
                with engine.connect() as conn:
                    # Use raw DBAPI cursor with parameterised query
                    # to avoid SQLAlchemy text() taint concerns.
                    dbapi_conn = conn.connection
                    cur = dbapi_conn.cursor()
                    try:
                        from psycopg import sql as pgsql

                        # SET cannot take a bound parameter; compose the
                        # already-validated identifier safely instead (#1201).
                        stmt = pgsql.SQL("SET search_path TO {}, public").format(
                            pgsql.Identifier(schema_name)
                        )
                        cur.execute(stmt)  # nosemgrep
                    finally:
                        cur.close()
                    metadata.create_all(conn)
                    conn.commit()
                engine.dispose()
                logger.info("Migrated tenant schema %s", schema_name)
            except Exception as exc:
                # Log at ERROR (operators must see this) and accumulate
                # so every tenant is still attempted before we raise.
                logger.error("Failed to migrate tenant schema %s: %s", schema_name, exc)
                # One-line excerpt — keep the structured raise message
                # below readable when many tenants fail.
                excerpt = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
                failed_tenants.append((schema_name, excerpt))

        if failed_tenants:
            # Fail-closed invariant (#1209): under ``isolation = "schema"``
            # a silently-skipped tenant means the app would serve that
            # tenant's traffic from the ``public`` schema — a direct
            # violation of the declared isolation posture. Halt boot.
            # Callers must repair the listed schemas (manual SQL or
            # schema rollback) before the app will serve. Do NOT
            # downgrade this raise to a warning.
            details = "; ".join(f"{schema} ({excerpt})" for schema, excerpt in failed_tenants)
            raise RuntimeError(
                "tenant schema migration failed for "
                f"{len(failed_tenants)} schema(s): {details}. "
                "Repair the listed tenants before booting (see #1209)."
            )

    def _apply_search_indexes(self, engine: Any) -> None:
        """Apply #954 cycle 2 search indexes (tsvector + GIN) to *engine*.

        Reads ``self._appspec.searches`` and runs the DDL produced by
        :func:`build_search_index_ddl`. No-op when the AppSpec has no
        search blocks. Statements are idempotent (``IF NOT EXISTS``)
        so dev-mode reboots don't error.
        """
        searches = list(getattr(self._appspec, "searches", []) or [])
        if not searches:
            return
        from sqlalchemy import text as _sa_text

        statements = build_search_index_ddl(self._entities, searches)
        if not statements:
            return
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(_sa_text(stmt))
        logger.info(
            "Applied %d FTS index statement%s for %d searchable entit%s",
            len(statements),
            "" if len(statements) == 1 else "s",
            len(searches),
            "y" if len(searches) == 1 else "ies",
        )

    def _compute_rls_user_attr_names_for_appspec(self) -> set[str]:
        """The app-wide scope-attr set under ``shared_schema``, else empty (Phase C).

        Gated on ``tenancy: mode: shared_schema`` (mirrors ``_apply_rls_policies``):
        only then do per-verb scope policies exist, so only then are
        ``dazzle.user_<attr>`` GUCs needed. Other isolation modes / non-tenant apps
        get an empty set → the per-request bind is a no-op.
        """

        tenancy = self._appspec.tenancy
        if tenancy is None or tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA:
            return set()
        return _compute_rls_user_attr_names(self._entities)

    def _apply_rls_policies(self, engine: Any) -> None:
        """Apply RLS tenant fence + per-verb scope/baseline policies (Phase B + C).

        Mirrors :meth:`_apply_search_indexes`: runtime-applied DDL post
        ``create_all`` (not an Alembic migration — see the Phase B/C plans). Gated
        on ``tenancy: mode: shared_schema``; a no-op for every other isolation
        mode (and for non-tenant apps), so behaviour is unchanged there.

        For each tenant-scoped entity it emits ``ENABLE`` + ``FORCE ROW LEVEL
        SECURITY`` and the restrictive ``tenant_fence`` (Phase B), then:

        - **scoped entity** (≥1 ``access.scopes`` rule): Phase C per-verb
          permissive policies (``scope_select``/``scope_insert``/
          ``scope_update``/``scope_delete``) compiled from the scope predicate
          algebra; the permissive ``tenant_baseline`` is dropped (a verb without
          a scope rule is denied at the DB).
        - **tenant-flat entity** (no scope rules): Phase B's permissive
          ``tenant_baseline`` (all verbs).

        All DDL is idempotent (drop-before-create). The role DDL is **not** run
        here (roles are cluster/deploy-level). App-layer scope filters remain in
        force as defence-in-depth, so a skipped apply cannot leak.
        """
        from sqlalchemy import text as _sa_text

        # All partitioning (scoped-vs-flat, fail-loud-on-missing-fk_graph, the
        # shared_schema / no-scoped no-op gates) now lives in build_all_rls_ddl
        # so the dev apply, prod apply, inspect, and drift paths share one
        # generator. Behaviour here is identical to the old inline version.
        # The DB-free build is only an emptiness gate (its gates fire before any
        # cast is computed) — the applied DDL is rebuilt with the live column
        # types below, so casts match the physical schema even when a dev DB
        # (db_policy=preserve) predates a column-type change (#1531).
        if not build_all_rls_ddl(self._appspec, self._entities):
            return
        with engine.begin() as conn:
            rows = conn.execute(
                _sa_text(
                    "SELECT table_name, column_name, udt_name "
                    "FROM information_schema.columns WHERE table_schema = current_schema()"
                )
            ).fetchall()
            statements = build_all_rls_ddl(
                self._appspec, self._entities, physical_types=physical_cast_overrides(rows)
            )
            for stmt in statements:
                conn.execute(_sa_text(stmt))
        logger.info(
            "Applied RLS policies (%d statement%s)",
            len(statements),
            "" if len(statements) == 1 else "s",
        )

    def _setup_models(self) -> None:
        """Generate Pydantic models and create/update schemas from the spec."""
        self._models = generate_all_entity_models(self._entities)
        # auth Plan 1d: under shared_schema, the framework partition key is
        # server-supplied (DB default from the bound session) — exclude it from
        # the create/update INPUT schemas for tenant-scoped entities.

        partition_key: str | None = None
        scoped: set[str] = set()
        tenancy = getattr(self._appspec, "tenancy", None) if self._appspec else None
        if tenancy is not None and tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA:
            partition_key = tenancy.isolation.partition_key
            scoped = scoped_entity_names(self._entities, partition_key)
        for entity in self._entities:
            ts = entity.name in scoped
            self._schemas[entity.name] = {
                "create": generate_create_schema(
                    entity, partition_key=partition_key, tenant_scoped=ts
                ),
                "update": generate_update_schema(
                    entity, partition_key=partition_key, tenant_scoped=ts
                ),
            }

    def _setup_database(self) -> None:
        """Initialize database backend, run migrations, create repositories."""
        if not self._database_url:
            raise ValueError(
                "database_url is required. Set DATABASE_URL environment variable "
                "or pass database_url to ServerConfig/DazzleBackendApp."
            )

        from dazzle.http.runtime.pg_backend import PostgresBackend

        self._db_manager = PostgresBackend(self._database_url)
        may_create_schema = self._should_create_schema_on_startup()

        if may_create_schema:
            # Development/test convenience only. Production schema changes must
            # go through Alembic so broken migration state is not hidden.
            from sqlalchemy import create_engine as _sa_create_engine

            from dazzle.http.runtime.sa_schema import build_metadata

            metadata = build_metadata(
                self._entities,
                surfaces=list(self._appspec.surfaces),
                **_tenancy_metadata_kwargs(self._appspec),
            )
            # Normalise Heroku-style postgres:// alias before adding driver suffix
            sa_url = add_psycopg_driver(normalise_postgres_scheme(self._database_url))
            # ONE engine for both steps; disposed exactly once in the finally so
            # create_engine is called a single time.
            engine = _sa_create_engine(sa_url)
            try:
                # Tolerant best-effort for dev schema conflicts ONLY: create_all
                # + the FTS indexes. A failure here is downgraded to a WARNING
                # and boot continues (the create-all-convenience invariant).
                try:
                    metadata.create_all(engine)
                    # #954 cycle 2 — apply tsvector + GIN index DDL after the
                    # base schema lands. Idempotent (IF NOT EXISTS); safe to
                    # re-run on every dev boot.
                    self._apply_search_indexes(engine)
                except Exception as exc:
                    logger.warning("Development schema create_all failed: %s", exc)

                # RLS tenancy Phase B — apply the tenant fence + permissive
                # baseline OUTSIDE the tolerant except above (C-1), on the SAME
                # engine: a fence-apply failure MUST halt boot for a shared_schema
                # app rather than be downgraded to a WARNING that lets the app
                # serve tenant traffic fence-less. The exception propagates after
                # being logged loudly. No-op for non-tenant / non-shared_schema
                # apps, so it never raises for them.
                try:
                    self._apply_rls_policies(engine)
                except Exception as rls_exc:
                    logger.error(
                        "RLS policy apply FAILED — tenant fence NOT installed; "
                        "shared-schema tenancy is unenforced. Halting boot: %s",
                        rls_exc,
                    )
                    raise
            finally:
                engine.dispose()
        else:
            logger.info("Skipping startup schema creation in production; Alembic owns schema.")

        # Development: create ALL framework tables via the orchestrator (ADR-0044).
        # Production: verify _dazzle_params exists (Alembic owns schema; the
        # orchestrator runs eagerly on dev and is a no-op on prod if tables exist).
        from dazzle.http.runtime.migrations import verify_dazzle_params_table

        if may_create_schema:
            from dazzle.http.runtime.framework_schema import ensure_framework_schema

            with self._db_manager.connection() as _fw_conn:
                ensure_framework_schema(_fw_conn)
        else:
            verify_dazzle_params_table(self._db_manager)

        # Build param resolver from AppSpec (#572)

        param_specs = {p.key: p for p in self._appspec.params} if self._appspec.params else {}
        self._param_resolver = ParamResolver(specs=param_specs)

        # Migrate tenant schemas when using schema-per-tenant isolation (#561)
        if self._tenant_config and self._tenant_config.isolation == "schema":
            self._migrate_tenant_schemas()

        # Connection pool open/close is handled by the app lifespan
        # (``_lifespan``), which reads ``DAZZLE_DB_POOL_MIN/MAX`` at startup
        # time. See ``_create_app`` (#438).

        # Build relation loader for nested ref resolution (#272)

        relation_registry = RelationRegistry.from_entities(self._entities)
        # Populate display_field map from IR for FK display resolution (#555)
        for _ir_entity in self._appspec.domain.entities:
            if _ir_entity.display_field:
                relation_registry.display_fields[_ir_entity.name] = _ir_entity.display_field
        relation_loader = RelationLoader(
            registry=relation_registry,
            entities=self._entities,
        )

        repo_factory = RepositoryFactory(
            self._db_manager,
            self._models,
            relation_loader=relation_loader,
        )
        self._repositories = repo_factory.create_all_repositories(self._entities)

    def _should_create_schema_on_startup(self) -> bool:
        """Return whether startup may create entity tables directly."""

        return not is_production()

    def _setup_services(self) -> None:
        """Create CRUD services and wire them to repositories."""
        state_machines = {
            entity.name: entity.state_machine for entity in self._entities if entity.state_machine
        }
        entity_specs = {entity.name: entity for entity in self._entities}

        factory = ServiceFactory(self._models, state_machines, entity_specs)
        self._service_factory = factory
        self._services = factory.create_all_services(
            self._service_specs,
            self._schemas,
        )

        if self._db_manager:
            for _service_name, service in self._services.items():
                if isinstance(service, CRUDService):
                    entity_name = service.entity_name
                    repo = self._repositories.get(entity_name)
                    if repo:
                        service.set_repository(repo)

        # Wire project-level service hooks (v0.29.0)
        self._wire_service_hooks()
        self._load_i18n_translations()

    def _load_i18n_translations(self) -> None:
        """Discover + register project translation files (#955 cycle 5).

        Reads ``locale/<locale>/LC_MESSAGES/messages.{mo,po}`` under the
        project root and registers each into the global
        :class:`~dazzle.i18n.MessageCatalogue`. The cycle-2 ``_()``
        filter then returns translated strings instead of source text.

        No-op when the project has no ``locale/`` tree — that's the
        common case for English-only apps. Failures are caught + logged
        because a malformed .po file shouldn't block boot.
        """
        if not self._project_root:
            return
        try:
            from dazzle.i18n.loader import load_translations

            load_translations(self._project_root)
        except Exception:
            logger.warning("i18n translation load failed", exc_info=True)

    def _resolve_pdf_branding(self) -> "PdfBranding | None":
        """Build a ``PdfBranding`` for the signing routes from the
        project manifest's ``[signing]`` block.

        Resolution order:

        1. ``[signing]`` block in ``dazzle.toml``, when ``organisation``
           is set — surfaces the full ``organisation`` / ``tagline`` /
           ``footer_text`` / ``location`` quartet.
        2. ``[project] name`` from the manifest — minimal fallback so
           projects that don't bother with a ``[signing]`` block still
           get their own name on every signed PDF.
        3. ``None`` — let the signing router default to its built-in
           ``PdfBranding(organisation="Dazzle App")``.
        """
        try:
            from dazzle.core.manifest import load_manifest
            from dazzle.signing.service import PdfBranding
        except ImportError:
            return None

        if not self._project_root:
            return None
        manifest_path = self._project_root / "dazzle.toml"
        if not manifest_path.is_file():
            return None

        try:
            manifest = load_manifest(manifest_path)
        except Exception:
            logger.warning(
                "Failed to load dazzle.toml for PdfBranding — falling back to defaults",
                exc_info=True,
            )
            return None

        signing_cfg = manifest.signing
        if signing_cfg.organisation:
            return PdfBranding(
                organisation=signing_cfg.organisation,
                organisation_tagline=signing_cfg.tagline,
                footer_text=signing_cfg.footer_text,
                location=signing_cfg.location,
            )

        # Fall back to the manifest's project name so something
        # project-specific lands on the PDF even without a [signing]
        # block.
        if manifest.name and manifest.name != "unnamed":
            return PdfBranding(organisation=manifest.name)

        return None

    def _resolve_signing_recovery(self) -> tuple[str, str]:
        """Read ``[signing] support_contact`` / ``resend_hook`` (TR-53).

        Returns ``(support_contact, resend_hook)`` — both empty strings
        when unconfigured or the manifest can't be read, so the signing
        router degrades to a plain (but non-dead-end) expired page.
        """
        if not self._project_root:
            return "", ""
        manifest_path = self._project_root / "dazzle.toml"
        if not manifest_path.is_file():
            return "", ""
        try:
            from dazzle.core.manifest import load_manifest

            signing_cfg = load_manifest(manifest_path).signing
        except Exception:
            return "", ""
        return signing_cfg.support_contact, signing_cfg.resend_hook

    def _wire_service_hooks(self) -> None:
        """Discover and register project-level service hooks."""
        if not self._project_root:
            return
        hooks_dir = self._project_root / "hooks"
        if not hooks_dir.is_dir():
            return

        try:
            from dazzle.http.runtime.hook_registry import build_registry
        except ImportError:
            return

        registry = build_registry(hooks_dir)
        if registry.count == 0:
            return

        logger.info("Registered %d service hook(s): %s", registry.count, registry.summary())

        # Wire hooks to CRUD services
        for _service_name, service in self._services.items():
            if not isinstance(service, CRUDService):
                continue
            entity_name = service.entity_name

            for h in registry.get_hooks("entity.pre_create", entity_name):
                service.add_pre_create_hook(h.function)
            for h in registry.get_hooks("entity.pre_update", entity_name):
                service.add_pre_update_hook(h.function)
            for h in registry.get_hooks("entity.pre_delete", entity_name):
                service.add_pre_delete_hook(h.function)
            for h in registry.get_hooks("entity.post_create", entity_name):
                service.on_created(h.function)
            for h in registry.get_hooks("entity.post_update", entity_name):
                service.on_updated(h.function)
            for h in registry.get_hooks("entity.post_delete", entity_name):
                service.on_deleted(h.function)

        # #956 cycle 4 — wire the audit emitter callbacks against
        # services for every `audit on X:` block. Silent no-op when
        # the AppSpec has no audit declarations.

        register_audit_callbacks(self._services, list(self._appspec.audits))

        # #953 cycle 6 — wire job-trigger callbacks. Pure-scheduled
        # jobs (no triggers) are skipped here; cycle-7's cron
        # scheduler enqueues those instead. The in-memory queue
        # accumulates messages even before a worker is running;
        # cycle-7+ will start the worker loop. Cycle-8 will swap
        # the in-memory queue for `RedisJobQueue` satisfying the
        # same Protocol — no caller change required.
        if self._appspec.jobs:
            from dazzle.http.runtime.job_queue import InMemoryJobQueue
            from dazzle.http.runtime.job_triggers import register_job_triggers

            self._job_queue = InMemoryJobQueue()
            register_job_triggers(self._services, list(self._appspec.jobs), self._job_queue)

        # #952 cycle 4 — wire notification dispatch callbacks against
        # services for every `notification X:` block that declares a
        # trigger entity. Manual-fire notifications (no trigger) and
        # apps without any notification declarations both no-op.
        notifications = list(getattr(self._appspec, "notifications", []) or [])
        if notifications:
            from dazzle.core.manifest import NotificationsConfig, load_manifest
            from dazzle.http.runtime.notification_wiring import (
                register_notification_triggers,
            )
            from dazzle.notifications import build_dispatcher_from_manifest

            notifications_cfg = NotificationsConfig()
            if self._project_root is not None:
                manifest_path = self._project_root / "dazzle.toml"
                if manifest_path.is_file():
                    try:
                        notifications_cfg = load_manifest(manifest_path).notifications
                    except Exception:
                        logger.warning(
                            "Failed to load [notifications] from dazzle.toml — "
                            "falling back to LogProvider",
                            exc_info=True,
                        )

            self._notification_dispatcher = build_dispatcher_from_manifest(notifications_cfg)
            register_notification_triggers(
                self._services,
                notifications,
                self._notification_dispatcher,
            )

        # Wire post_upload hooks to file upload callbacks (v0.39.0, #437)
        if hasattr(self, "_upload_callbacks"):
            for _service_name, service in self._services.items():
                if not isinstance(service, CRUDService):
                    continue
                _ename = service.entity_name
                for h in registry.get_hooks("entity.post_upload", _ename):
                    _hook_fn = h.function

                    async def _upload_hook(
                        entity_name: str,
                        entity_id: str,
                        field_name: str,
                        file_meta: dict[str, Any],
                        fn: Any = _hook_fn,
                    ) -> None:
                        await fn(entity_name, entity_id, file_meta)

                    self._upload_callbacks.append(_upload_hook)

    def _wire_sse_live_push(self) -> None:
        """#1399 slice 1 — wire SSE live push when a workspace declares `live: on`.

        Must run AFTER ``_run_subsystems()`` (which sets ``self._event_framework``).
        The framework's concrete bus only exists after its start lifespan hook
        runs, so we bind everything to a ``LazyFrameworkBus`` proxy that resolves
        the live bus at call time. Three wirings, all gated on opt-in + framework:

        1. Nudge publishers on every CRUD service (entity mutation -> bus).
        2. An ``SSEStreamManager`` + ``/_ops/sse/events`` route (bus -> browser),
           mounted independently of the ops dashboard.
        3. Lifespan start/stop for the manager, registered AFTER the framework's
           start hook so subscription happens against a started bus.
        """
        if not _any_workspace_live(list(self._appspec.workspaces)):
            return
        framework = self._event_framework
        if framework is None:
            logger.warning(
                "Workspace declares `live: on` but no event framework is available; "
                "SSE live push disabled."
            )
            return

        assert self._app is not None
        # Defensive: never double-mount the SSE router (e.g. if a future ops
        # dashboard also mounts /_ops/sse). validate_routes() would reject the
        # collision otherwise.
        if any(getattr(r, "path", "") == "/_ops/sse/events" for r in self._app.routes):
            logger.info("SSE routes already mounted; skipping live-push mount.")
            return
        lazy_bus = LazyFrameworkBus(framework)
        register_sse_callbacks(self._services, lazy_bus)

        sse_manager = SSEStreamManager(event_bus=lazy_bus)
        self._app.include_router(create_sse_routes(sse_manager))

        async def _start_sse() -> None:
            await sse_manager.start()

        async def _stop_sse() -> None:
            await sse_manager.stop()

        register_lifespan_hook(self._app, startup=_start_sse, shutdown=_stop_sse)
        logger.info("SSE live push enabled (mounted /_ops/sse/events).")

    def _wire_storage_routes(self) -> None:
        """Register storage upload-ticket routes (#932 cycle 3).

        For every entity with at least one ``field foo: file
        storage=<name>`` binding, generate ``POST /api/{entity}/upload-ticket``
        backed by the configured ``StorageProvider``.

        Validates DSL ↔ manifest cross-references first — unresolved
        ``storage=<name>`` references raise a clear error at startup
        rather than at first request. Warnings (e.g. ``storage=`` on
        a non-file field) are logged but don't block startup.

        Existing projects with no ``[storage.<name>]`` blocks AND no
        ``storage=`` field bindings see zero behaviour change.
        """
        import logging

        from dazzle.http.runtime.storage import (
            StorageRegistry,
            register_storage_proxy_routes,
            register_upload_ticket_routes,
        )

        # Fast-out when neither side declares anything storage-related.
        has_field_refs = any(
            getattr(f, "storage", None)
            for entity in self._appspec.domain.entities
            for f in entity.fields
        )
        if not self._storage_defs and not has_field_refs:
            return

        errors, warnings = validate_storage_refs(self._appspec, self._storage_defs)
        log = logging.getLogger(__name__)
        for warn in warnings:
            log.warning("storage_validation_warning %s", warn)
        if errors:
            joined = "\n  ".join(errors)
            raise RuntimeError(
                f"Storage validation failed:\n  {joined}\n"
                "Either declare the [storage.<name>] block in dazzle.toml "
                "or remove the `storage=<name>` binding from the DSL field."
            )

        registry = StorageRegistry.from_manifest(self._storage_defs)
        self._storage_registry = registry

        # #932 cycle 4: expose registry on app.state so:
        #   1. The auto-verifier in route_generator's create/update
        #      handlers can resolve providers per-request.
        #   2. Project-side custom finalize handlers (the documented
        #      "30-line pattern") can call
        #      ``request.app.state.storage_registry.get(<name>)``.
        if self._app is not None:
            self._app.state.storage_registry = registry

        if has_field_refs and self._app is not None:
            paths = register_upload_ticket_routes(
                app=self._app, appspec=self._appspec, registry=registry
            )
            if paths:
                log.info(
                    "storage_routes_registered count=%d paths=%s",
                    len(paths),
                    paths,
                )
            # #942 cycle 1a: read-side proxy routes (one per storage
            # referenced by any field). Streams the bytes through the
            # server under cookie auth — no presigned download URLs.
            proxy_paths = register_storage_proxy_routes(
                app=self._app, appspec=self._appspec, registry=registry
            )
            if proxy_paths:
                log.info(
                    "storage_proxy_routes_registered count=%d paths=%s",
                    len(proxy_paths),
                    proxy_paths,
                )

    def _setup_auth(self) -> tuple[Any, Any]:
        """Initialize auth store, middleware, and social auth.

        Returns (auth_dep, optional_auth_dep) for route generation.
        """
        # #1420 Slice 1 — fail closed: auth disabled in production is a critical
        # misconfiguration (generated CRUD would be world-writable). Runs before
        # any auth/DB state is touched.
        from dazzle.http.runtime.auth.insecure_guard import (
            assert_secure_auth_config,
            insecure_ack_from_env,
        )

        assert_secure_auth_config(
            self._enable_auth,
            production=is_production(),
            allow_insecure=insecure_ack_from_env(),
        )

        auth_dep = None
        optional_auth_dep = None
        if not self._enable_auth:
            return auth_dep, optional_auth_dep

        assert self._database_url is not None  # guaranteed by _setup_database()
        # Pass the DSL user entity name so auth can load domain attributes
        # (e.g. school, department) into preferences for scope rules (#532).
        _user_entity = (
            getattr(self._auth_config, "user_entity", "User") if self._auth_config else "User"
        )
        self._auth_store = AuthStore(
            database_url=self._database_url,
            user_entity_table=_user_entity,
        )
        # #1463: install the tenant-host parent graph so create_membership resolves
        # each membership's archetype:tenant partition root at write time. None for
        # flat tenancy (no `parent:` edges). Boot reconciliation (in _lifespan)
        # backfills/refreshes existing rows once the tenant tables exist.
        _tenant_entities = getattr(getattr(self._appspec, "domain", None), "entities", None)
        self._auth_store.set_partition_hierarchy(build_partition_hierarchy(_tenant_entities))
        # AuthStore construction is now pure (no I/O); run its first-use schema
        # init eagerly at boot to preserve fail-fast + eager-DDL behavior. A no-op
        # in production (skip_boot_schema_ddl: migrations own the schema, #1462).
        self._auth_store.ensure_initialized()
        self._auth_middleware = AuthMiddleware(self._auth_store)

        # ADR-0039 (#778/#1398): wire the domain-`User` provisioning mirror onto the
        # production auth-user create path **only** when the app declares an
        # `auth_identity:` bridge (D5 — undeclared `User` behaves exactly as today). The
        # test/QA route gets the mirror unconditionally (create_test_routes, which keeps
        # the #1398 best-effort for undeclared `User`). One rule, both paths (D4).
        _user_ir = self._user_ir_entity()
        if _user_ir is not None and _user_ir.auth_identity is not None:
            from dazzle.http.runtime.auth_identity_mirror import mirror_auth_user_to_domain

            _store = self._auth_store  # non-None here (just constructed)
            assert _store is not None

            def _provision_domain_user(user: Any, _spec: EntitySpec = _user_ir) -> None:
                mirror_auth_user_to_domain(
                    _store._execute_modify,
                    _spec,
                    user_id=str(user.id),
                    email=user.email,
                    username=user.username or "",
                    role=(user.roles[0] if user.roles else ""),
                )

            _store._on_user_created = _provision_domain_user

        # #933: register the AuthStore with the module-level singleton
        # so project route handlers can call `current_user_id(request)`
        # / `current_user(request)` / `@require_auth(...)` without
        # re-implementing the cookie + sessions-table dance.
        from dazzle.http.runtime.auth import register_auth_store

        register_auth_store(self._auth_store)

        from dazzle.http.runtime.auth import (
            create_auth_dependency,
            create_optional_auth_dependency,
        )

        auth_dep = create_auth_dependency(self._auth_store)
        optional_auth_dep = create_optional_auth_dependency(self._auth_store)

        return auth_dep, optional_auth_dep

    def _user_ir_entity(self) -> EntitySpec | None:
        """The core-IR principal entity (ADR-0039) — the configured `user_entity`
        (default `User`), or None if the app defines no such entity."""
        name = getattr(self._auth_config, "user_entity", "User") if self._auth_config else "User"
        return next((e for e in self._appspec.domain.entities if e.name == name), None)

    @staticmethod
    def _verify_scope_predicates(cedar_access_specs: dict[str, Any], fk_graph: Any) -> None:
        """Verify all scope predicates compile at startup (belt-and-suspenders).

        Iterates every entity with scope rules and calls ``compile_predicate``
        on each, catching errors early rather than at request time.
        """
        import logging

        logger = logging.getLogger(__name__)
        for entity_name, access_spec in cedar_access_specs.items():
            scopes = getattr(access_spec, "scopes", None)
            if not scopes:
                continue
            for scope_rule in scopes:
                predicate = getattr(scope_rule, "predicate", None)
                if predicate is None:
                    continue
                try:
                    from dazzle.http.runtime.predicate_compiler import compile_predicate

                    compile_predicate(predicate, entity_name, fk_graph)
                except Exception:
                    logger.exception(
                        "Scope predicate compilation failed for entity '%s' — "
                        "scope filtering will fall back to legacy pipeline at runtime",
                        entity_name,
                    )

    def _setup_routes(self, auth_dep: Any, optional_auth_dep: Any) -> None:
        """Generate entity CRUD routes, audit routes, file routes, and dev routes."""
        assert self._app is not None

        # Extract access specs
        entity_access_specs: dict[str, dict[str, Any]] = {}
        for entity in self._entities:
            if entity.metadata and "access" in entity.metadata:
                entity_access_specs[entity.name] = entity.metadata["access"]

        cedar_access_specs: dict[str, Any] = {}
        for entity in self._entities:
            if entity.access:
                cedar_access_specs[entity.name] = entity.access

        # Audit logger (#1172). The runtime AuditLogger writes every
        # access-control decision to `_dazzle_audit_log`. It is the
        # production audit trail — distinct from the verification-layer
        # observability seam in `dazzle.rbac.audit`.
        audit_logger = None
        _has_auditable_entities = any(
            (entity.metadata and "access" in entity.metadata)
            or getattr(entity, "audit", None)
            or entity.access
            for entity in self._entities
        )
        if _has_auditable_entities:
            # Fail-closed audit invariant (#1172): an app with access-
            # controlled or audited entities MUST boot with a working
            # audit trail, or not boot at all — a silently-absent trail
            # is a compliance hole. `_setup_database` already raises
            # without a database_url, so this is belt-and-suspenders: if
            # a future refactor reorders boot or makes the DB optional,
            # the server refuses to start rather than run un-audited.
            if not self._database_url:
                raise RuntimeError(
                    "Audit logging required: this app has access-controlled "
                    "or audited entities but no database_url to persist the "
                    "audit trail. Set DATABASE_URL or ServerConfig.database_url."
                )
            from dazzle.http.runtime.audit_log import AuditLogger

            audit_logger = AuditLogger(
                database_url=self._database_url,
                audit_integrity=self._config.audit_integrity,
            )
            # Keep a handle on the builder so callers (graceful shutdown,
            # in-process tests) can deterministically `drain()` the audit
            # queue instead of racing the 1s background flush timer.
            #
            # start()/stop() are driven by the app lifespan (``_lifespan``),
            # not called here: start() is deferred to lifespan startup so a
            # running event loop is guaranteed (#1214). Py3.12 removed the
            # implicit event-loop acquisition that ``asyncio.ensure_future``
            # previously relied on, so starting from this sync construction
            # path raises ``RuntimeError`` when no loop is current. The
            # lifespan reads ``self._audit_logger`` at startup time, so this
            # assignment must precede app startup (it does — it runs at build
            # time, well before the lifespan fires).
            self._audit_logger = audit_logger

        # ADR-0050 Option A (first-party usage signal): construct the usage
        # collector whenever a database is available (any app can capture usage,
        # unlike audit which is gated on auditable entities). start()/stop() are
        # driven by the lifespan (reads self._usage_collector at startup). Dormant
        # until Phase 3 wires record() calls; reachable via request.app.state.
        if self._database_url:
            self._usage_collector = UsageCollector(database_url=self._database_url)
            self._app.state.usage_collector = self._usage_collector
            services = getattr(self._app.state, "services", None)
            if services is not None:
                services.usage_collector = self._usage_collector
            # ADR-0050 3a (Phase 4): expose the pooled DB backend so the workspace
            # handler can read usage counts at render time (best-effort, pooled).
            self._app.state.db_manager = self._db_manager

        # Project route overrides — registered first for priority (v0.29.0)
        # #1601: never swallow registration failures at debug — one bad
        # override used to drop every host route with no production log.
        if self._project_root:
            from dazzle.http.runtime.route_overrides import (
                RouteOverrideRegistrationError,
                build_override_router,
                discover_route_overrides,
                find_unbound_shadowing_overrides,
            )

            # #1392 item 2 — page-context builder for `# dazzle:returns fragment`
            # overrides: chrome the handler's inner HTML in the app shell. deps=None
            # ⇒ appspec from app.state + shell frame (the item-2 guarantee).
            async def _ov_page_ctx(request: Any, current_route: str) -> Any:
                return await build_app_page_context(request, current_route=current_route)

            try:
                override_router = build_override_router(
                    self._project_root / "routes", page_ctx_builder=_ov_page_ctx
                )
            except RouteOverrideRegistrationError:
                # Fail boot loudly (default). Soft mode is handled inside
                # build_override_router and does not raise.
                raise
            except Exception:
                logger.error(
                    "Route override discovery/build failed — host custom routes "
                    "will not be mounted",
                    exc_info=True,
                )
                raise

            if override_router is not None:
                self._app.include_router(override_router)

            # #1420 Slice 3 / ADR-0040 D2 — conformance: a route-override that
            # shadows a generated entity route without a `# dazzle:implements`
            # binding bypasses permit/scope. Surface it loudly at boot.
            try:
                _overrides = discover_route_overrides(self._project_root / "routes")
                _generated = {(ep.method.value, ep.path) for ep in self._endpoint_specs}
                for _violation in find_unbound_shadowing_overrides(_overrides, _generated):
                    logger.warning("[dazzle] %s", _violation)
            except Exception:
                logger.warning(
                    "Route override shadowing conformance check skipped",
                    exc_info=True,
                )

            # Extension routers registered in dazzle.toml (#786).
            # Registered after single-file overrides but before generated routes
            # so they still win first-match against auto-generated endpoints.
            try:
                from dazzle.core.manifest import load_manifest
                from dazzle.http.runtime.route_overrides import load_extension_routers

                manifest_path = self._project_root / "dazzle.toml"
                if manifest_path.is_file():
                    manifest = load_manifest(manifest_path)
                    router_specs = manifest.extensions.routers
                    for ext_router in load_extension_routers(self._project_root, router_specs):
                        self._app.include_router(ext_router)
            except Exception:
                logger.debug("Extension router loading skipped", exc_info=True)

        # Entity CRUD routes
        service_specs = {svc.name: svc for svc in self._service_specs}

        # Pre-compute HTMX metadata per entity so list API endpoints can
        # render table row fragments with correct column definitions.
        # Use surface field projection when a list surface exists (#405).
        _entity_list_surfaces: dict[str, Any] = {}
        _entity_all_list_surfaces: dict[str, list[Any]] = {}
        for _surf in self._appspec.surfaces:
            _eref = _surf.entity_ref
            _mode = str(_surf.mode or "").lower()
            if _eref and _mode == "list":
                if _eref not in _entity_list_surfaces:
                    _entity_list_surfaces[_eref] = _surf
                _entity_all_list_surfaces.setdefault(_eref, []).append(_surf)

        entity_htmx_meta: dict[str, dict[str, Any]] = {}
        app_prefix = "/app"
        for entity in self._entities:
            slug = _entity_slug(entity.name)
            _ls = _entity_list_surfaces.get(entity.name)
            cols = (
                _build_surface_columns(entity, _ls, self._appspec.enums)
                if _ls
                else _build_entity_columns(entity, self._appspec.enums)
            )
            # ADR-0050 2d → L4: for the pure entity-fallback (no list surface), cache
            # the FULL untruncated column set so the request-time usage inferer can
            # rescue a heavily-engaged field that build-time salience would shed. None
            # for surface-declared columns (explicit author projection wins).
            cols_full = None if _ls else _build_entity_columns_full(entity, self._appspec.enums)
            # #1494 (2c, Slice 2): peek is declared PER SURFACE, but one entity can
            # host several list surfaces with different `peek:` modes. Map each
            # surface's table_id (= surface.name = region_name) to its resolved
            # peek so the `/api` row-hydrate path picks the mode for the *actual*
            # surface being viewed (recovered from HX-Target) — keeping the row
            # chevron in step with the per-surface SlideOver container `_build_list`
            # emits. `peek_mode` stays the first-surface value (the byte-stable
            # default used when no table_id is resolvable).
            peek_by_table_id = {
                _s.name: resolve_peek_mode(_s, entity).value
                for _s in _entity_all_list_surfaces.get(entity.name, [])
            }
            # #1603: per-surface open-via detail templates (key both surface.name
            # and dt-{name} — HTMX table_id is `dt-{surface.name}`).
            from dazzle.page.open_via import resolve_list_detail_url_template

            detail_url_by_table_id: dict[str, str] = {}
            for _s in _entity_all_list_surfaces.get(entity.name, []):
                _tmpl = resolve_list_detail_url_template(_s, entity, app_prefix=app_prefix)
                detail_url_by_table_id[_s.name] = _tmpl
                detail_url_by_table_id[f"dt-{_s.name}"] = _tmpl
            _default_detail = (
                resolve_list_detail_url_template(_ls, entity, app_prefix=app_prefix)
                if _ls is not None
                else f"{app_prefix}/{slug}/{{id}}"
            )
            entity_htmx_meta[entity.name] = {
                "columns": cols,
                "columns_full": cols_full,  # ADR-0050 2d: untruncated (entity-fallback only)
                "detail_url": _default_detail,
                "detail_url_by_table_id": detail_url_by_table_id,
                "entity_name": entity.name,
                # #1494 (2c): resolved `peek:` mode for the (first) list surface.
                # Unset → "off" (Slice-1 default, byte-stable); `peek: expand` opts
                # the entity-list rows into the inline detail-panel chevron.
                "peek_mode": resolve_peek_mode(_ls, entity).value if _ls else "off",
                "peek_by_table_id": peek_by_table_id,
                # Convergence C1.1: rows hydrated over /api render bulk-select
                # checkboxes iff the (first) list surface declares bulk actions
                # (first-surface value, same convention as peek_mode).
                "bulk_actions": bool(
                    _ls is not None and getattr(getattr(_ls, "ux", None), "bulk_actions", None)
                ),
                # Convergence C2.3: the type-derived inline-editable column set
                # (mirrors template_compiler's rule). Never threaded before —
                # hydrated rows lost their edit affordance when ADR-0049 moved
                # row rendering to /api.
                "inline_editable": [
                    str(c.get("key", ""))
                    for c in cols
                    if str(c.get("type", "")) in ("text", "bool", "badge", "date", "datetime")
                    and str(c.get("key", "")) not in ("id", "created_at", "updated_at")
                    and not str(c.get("key", "")).endswith("_id")
                    # A badge cell edits via a <select> built from the column's
                    # enum options — without them the editor would be empty.
                    and (str(c.get("type", "")) != "badge" or c.get("filter_options"))
                ],
            }

        # Build per-entity audit config mapping.
        # When audit_trail is True (app-level switch), all entities get audit
        # logging by default. Entities can still opt out with audit: false.
        entity_audit_configs: dict[str, Any] = {}
        _global_audit = self._appspec.audit_trail
        for entity in self._entities:
            _ac = getattr(entity, "audit", None)
            if _ac is not None:
                entity_audit_configs[entity.name] = _ac
            elif _global_audit:
                # Default to audit: all when audit_trail is globally enabled
                from dazzle.core.ir import AuditConfig

                entity_audit_configs[entity.name] = AuditConfig(enabled=True)

        # Belt-and-suspenders: verify all scope predicates compile at startup
        _fk_graph = getattr(self._appspec, "fk_graph", None)
        if _fk_graph is not None:
            self._verify_scope_predicates(cedar_access_specs, _fk_graph)

        # Build graph metadata for edge entities (#619 Phase 2)
        entity_graph_specs: dict[str, Any] = {}
        for ir_entity in self._appspec.domain.entities:
            if ir_entity.graph_edge is not None:
                node_specs: dict[str, Any] = {}
                for field_name in (ir_entity.graph_edge.source, ir_entity.graph_edge.target):
                    ir_field = next((f for f in ir_entity.fields if f.name == field_name), None)
                    if ir_field and ir_field.type.ref_entity:
                        ref_ent = next(
                            (
                                e
                                for e in self._appspec.domain.entities
                                if e.name == ir_field.type.ref_entity
                            ),
                            None,
                        )
                        if ref_ent and ref_ent.graph_node:
                            node_specs[ir_field.type.ref_entity] = ref_ent.graph_node
                entity_graph_specs[ir_entity.name] = (ir_entity.graph_edge, node_specs)

        # Build node graph metadata for neighborhood endpoints (#619 Phase 3)
        node_graph_specs: dict[str, dict[str, Any]] = {}
        for ir_entity in self._appspec.domain.entities:
            if ir_entity.graph_node is not None:
                edge_entity_name = ir_entity.graph_node.edge_entity
                edge_ir = next(
                    (e for e in self._appspec.domain.entities if e.name == edge_entity_name),
                    None,
                )
                if edge_ir and edge_ir.graph_edge:
                    node_graph_specs[ir_entity.name] = {
                        "graph_edge": edge_ir.graph_edge,
                        "graph_node": ir_entity.graph_node,
                        "node_table": ir_entity.name,
                        "edge_table": edge_entity_name,
                    }

        # #928: per-entity display_field map (parallels relation_registry's
        # internal map but exposed through the route generator so the list
        # handler can inject `__display__` on top-level list responses).
        entity_display_fields: dict[str, str] = {
            ir_entity.name: ir_entity.display_field
            for ir_entity in self._appspec.domain.entities
            if ir_entity.display_field
        }

        # #932 cycle 4: compute storage-bound field bindings so the
        # create/update handlers can auto-verify uploaded s3_keys.

        entity_storage_bindings = build_entity_storage_bindings(self._appspec)

        # #957 cycle 6: pull admin_personas off the linked tenancy spec.
        # `_appspec.tenancy` may be None for apps without a `tenancy:`
        # block — empty list is the safe default.
        _admin_personas: list[str] = []
        if self._appspec and self._appspec.tenancy:
            _admin_personas = list(self._appspec.tenancy.admin_personas)

        # #1551: early-construct the FileService so the route generator can
        # wire attach-time triple verification into create/update handlers.
        # _mount_file_routes (called later) skips reconstruction when the
        # service is already set and proceeds directly to route mounting.
        # This must happen before generate_all_routes because handler
        # factories capture file_service at construction time (closures).
        _entity_file_fields: dict[str, list[str]] = {}
        if self._enable_files and self._appspec:
            from dazzle.http.runtime.file_storage import (
                FileMetadataStore,
                FileValidator,
                LocalStorageBackend,
            )

            _storage = LocalStorageBackend(self._files_path, "/files")
            _metadata_store = FileMetadataStore(database_url=self._database_url)
            _validator = FileValidator()
            self._file_service = FileService(_storage, _metadata_store, _validator)

            for _ent in self._appspec.domain.entities:
                _ff = [f.name for f in _ent.fields if f.type.kind == FieldTypeKind.FILE]
                if _ff:
                    _entity_file_fields[_ent.name] = _ff

        # #1551 review fix — wire byte_audit whenever document routes will be
        # mounted, NOT only when _has_auditable_entities. An app with file
        # fields but no scope:/permit:/audit: declarations (the "posture" access
        # path) serves stored bytes with byte_audit = None → silently unaudited.
        # _wire_byte_audit reuses audit_logger if already constructed above;
        # otherwise it builds one from the same inputs when a DB is present.
        self._wire_byte_audit(audit_logger)

        route_generator = RouteGenerator(
            security_profile=self._security_profile,
            services=self._services,
            models=self._models,
            schemas=self._schemas,
            entity_access_specs=entity_access_specs,
            auth_dep=auth_dep,
            optional_auth_dep=optional_auth_dep,
            require_auth_by_default=self._enable_auth and not self._enable_test_mode,
            auth_store=self._auth_store,
            audit_logger=audit_logger,
            cedar_access_specs=cedar_access_specs,
            entity_list_projections=self._entity_list_projections,
            entity_search_fields=self._entity_search_fields,
            entity_filter_fields=self._entity_filter_fields,
            entity_auto_includes=self._entity_auto_includes,
            entity_htmx_meta=entity_htmx_meta,
            entity_audit_configs=entity_audit_configs,
            entity_ref_targets=self._entity_ref_targets,
            fk_graph=_fk_graph,
            entity_graph_specs=entity_graph_specs,
            node_graph_specs=node_graph_specs,
            entity_display_fields=entity_display_fields,
            db_manager=self._db_manager,
            entity_storage_bindings=entity_storage_bindings,
            entity_soft_delete={e.name: e.soft_delete for e in self._entities},
            admin_personas=_admin_personas,
            file_service=self._file_service,
            entity_file_fields=_entity_file_fields or None,
        )

        # Cycle 249 (EX-049): populate persona_backed_entities from appspec
        # so the create handler can auto-inject refs to backing entities.
        if self._appspec and self._appspec.personas:
            for persona in self._appspec.personas:
                if persona.backed_by:
                    route_generator.persona_backed_entities[persona.backed_by] = (
                        persona.id,
                        persona.link_via,
                    )

        # ADR-0039 D3b (#778/#1398): if the `User` entity declares `auth_identity:`,
        # resolve `ref User` create-injection by the declared link instead of the #774
        # auth-id assumption. Undeclared ⇒ None ⇒ #774 unchanged (D5).
        _user_ir = self._user_ir_entity()
        if _user_ir is not None and _user_ir.auth_identity is not None:
            route_generator.auth_identity_user_link = _user_ir.auth_identity.link_via

        # Collect (method, path) pairs already claimed by project overrides
        # and extension routers so the generic CRUD generator can skip
        # them — first-match still wins at request time, but a skipped
        # mount means no boot-time "Route conflict" warning (#1101).
        claimed_routes: set[tuple[str, str]] = set()
        for _route in self._app.routes:
            _methods = getattr(_route, "methods", None)
            _path = getattr(_route, "path", None)
            if not _methods or not _path:
                continue
            for _m in _methods:
                claimed_routes.add((_m, _path))

        router = route_generator.generate_all_routes(
            self._endpoint_specs,
            service_specs,
            claimed_routes=claimed_routes,
        )
        self._app.include_router(router)
        # #1422: capture the per-entity in-process create invokers populated during
        # route generation, and expose them on app.state for the experience-form
        # POST (in-process create, no self-fetch). Set on both this app and (via
        # app_factory) any separately-constructed served app.
        self._create_invokers = route_generator.create_invokers
        self._app.state.entity_create_invokers = self._create_invokers

        # v0.71.24 (#1126) — build the public policy registry from the
        # same inputs the route generator just consumed. Project route
        # overrides reach it via `app.state.policy_registry` (or, more
        # commonly, indirectly via the public `dazzle.http.runtime.
        # policy.check_entity_op` helper). Closes the "route overrides
        # bypass permit/scope" gap surfaced by #1126.

        # `_services` is keyed by service name; resolve an entity-keyed view
        # once so both the `service=` lookup and the entity-set enumeration
        # below see entity names, not service names (#1181).
        _services_by_entity = self.services_by_entity()
        policy_registry = PolicyRegistry(
            entities={
                entity_name: EntityPolicyInfo(
                    entity_name=entity_name,
                    cedar_access_spec=cedar_access_specs.get(entity_name),
                    fk_graph=_fk_graph,
                    admin_personas=list(_admin_personas),
                    service=_services_by_entity.get(entity_name),
                )
                for entity_name in {
                    *cedar_access_specs.keys(),
                    *_services_by_entity.keys(),
                }
            }
        )
        self._app.state.policy_registry = policy_registry

        # v0.61.106 (#932 cycle 3): storage upload-ticket auto-routes.
        # Validates `field foo: file storage=<name>` references against
        # the loaded `[storage.<name>]` blocks, then registers
        # `POST /api/{entity}/upload-ticket` for every entity with at
        # least one storage-bound field. Skips silently when neither
        # is declared so existing projects see zero behaviour change.
        self._wire_storage_routes()

        self._mount_audit_query_routes(audit_logger, auth_dep)
        self._mount_atomic_flow_routes(auth_dep, cedar_access_specs, _fk_graph, audit_logger)
        self._mount_grant_routes(auth_dep)
        self._mount_audit_history_routes(auth_dep)
        self._mount_locale_routes()
        self._mount_file_routes(optional_auth_dep)
        self._mount_document_routes(
            cedar_access_specs, _fk_graph, optional_auth_dep, _admin_personas
        )
        self._mount_search_routes()
        self._mount_fts_routes(auth_dep)
        self._mount_signing_routes()
        self._mount_bulk_routes(cedar_access_specs, _fk_graph, optional_auth_dep, _admin_personas)
        self._mount_parent_graph_routes(node_graph_specs)
        self._mount_test_routes()
        self._mount_dev_routes()

    def _mount_audit_query_routes(self, audit_logger: Any, auth_dep: Any) -> None:
        assert self._app is not None
        # Audit query routes
        if audit_logger:
            from dazzle.http.runtime.audit_routes import create_audit_routes

            audit_router = create_audit_routes(
                audit_logger=audit_logger,
                auth_dep=auth_dep,
            )
            self._app.include_router(audit_router)

    def _mount_atomic_flow_routes(
        self, auth_dep: Any, cedar_access_specs: Any, _fk_graph: Any, audit_logger: Any
    ) -> None:
        assert self._app is not None
        # #1228 Phase 3c.iii — atomic-flow routes (POST /api/atomic/<name>)
        if self._appspec and self._appspec.atomic_flows and self._db_manager:
            from dazzle.http.runtime.atomic_flow_routes import (
                build_atomic_flow_router,
            )

            atomic_router = build_atomic_flow_router(
                list(self._appspec.atomic_flows),
                self._db_manager,
                # auth Plan 1b: the atomic-flow router invokes this with the
                # AuthContext (atomic_flow_routes `auth_context=user`), so read
                # effective_roles (active membership) — not the global user.roles.
                user_role_extractor=lambda ac: list(getattr(ac, "effective_roles", None) or []),
                auth_dep=auth_dep,
                # #1313 slice 1b/1c — per-step scope enforcement. Same access
                # specs + FK graph the policy registry uses above.
                access_specs=cedar_access_specs,
                fk_graph=_fk_graph,
                # #1313 — async audit fact per committed step (ADR-0029 inv. 5).
                audit_logger=audit_logger,
            )
            self._app.include_router(atomic_router)

            # #1317 — if any flow opts into strict in-transaction audit, create
            # the `_dazzle_atomic_audit` side-table ONCE here at boot (own
            # connection, committed independently) — race-free, vs a per-request
            # CREATE TABLE IF NOT EXISTS inside the mutation transaction.
            from dazzle.core.ir import FlowAuditMode

            if any(
                getattr(f, "audit_mode", None) == FlowAuditMode.STRICT
                for f in self._appspec.atomic_flows
            ):
                from dazzle.http.runtime.atomic_flow_executor import ensure_atomic_audit_table

                with self._db_manager.connection() as _audit_conn:
                    ensure_atomic_audit_table(_audit_conn)

            # #1319 / ADR-0032 Slice B — wire the transition→atomic invoke context
            # into each CRUD service so a status transition carrying `invoke_flow`
            # runs the named flow in its status-write transaction, each step
            # scope-enforced. cedar_access_specs + _fk_graph are the same maps the
            # atomic router above received; the registry keys flows by name.
            _atomic_flow_registry = {f.name: f for f in self._appspec.atomic_flows}
            for _svc in self._services.values():
                _setter = getattr(_svc, "set_invoke_context", None)
                if _setter is not None:
                    _setter(_atomic_flow_registry, cedar_access_specs, _fk_graph)

    def _mount_grant_routes(self, auth_dep: Any) -> None:
        assert self._app is not None
        # Grant management routes (#629)
        if self._appspec and self._appspec.grant_schemas and self._db_manager:
            from dazzle.http.runtime.grant_routes import create_grant_routes

            grant_router = create_grant_routes(
                db_manager=self._db_manager,
                appspec=self._appspec,
                auth_dep=auth_dep,
            )
            self._app.include_router(grant_router)

    def _mount_audit_history_routes(self, auth_dep: Any) -> None:
        assert self._app is not None
        # #956 cycle 11 — audit-history HTMX fragment route. Only
        # registered when the AppSpec declares at least one
        # `audit on X:` block (cycle-2's linker injects the
        # AuditEntry service in that case).
        if self._appspec and self._appspec.audits:
            from dazzle.http.runtime.audit_history_routes import (
                create_audit_history_routes,
            )

            audit_history_router = create_audit_history_routes(
                audit_service=self.service_for_entity("AuditEntry"),
                audits=list(self._appspec.audits),
                auth_dep=auth_dep,
            )
            self._app.include_router(audit_history_router)

    def _mount_locale_routes(self) -> None:
        assert self._app is not None
        # #955 cycle 6 — locale switcher endpoint (`POST /_dazzle/i18n/locale`).
        # Always mounted; the macro template only renders when supported_locales
        # is non-empty. Cookie name + supported set come from manifest I18nConfig.
        try:
            from dazzle.core.manifest import I18nConfig, load_manifest
            from dazzle.http.runtime.locale_routes import create_locale_routes

            i18n_cfg = I18nConfig()
            if self._project_root is not None:
                manifest_path = self._project_root / "dazzle.toml"
                if manifest_path.is_file():
                    try:
                        i18n_cfg = load_manifest(manifest_path).i18n
                    except Exception:
                        logger.debug(
                            "i18n manifest load skipped — using defaults",
                            exc_info=True,
                        )
            locale_router = create_locale_routes(
                cookie_name=i18n_cfg.cookie_name,
                supported_locales=frozenset(i18n_cfg.supported_locales)
                if i18n_cfg.supported_locales
                else None,
            )
            self._app.include_router(locale_router)
        except Exception:
            logger.warning("Locale router mount failed", exc_info=True)

        # ADR-0050 Phase 5 / 1a: field-engagement beacon endpoint, mounted only when
        # a usage collector exists (a database is configured). The dz-usage.js hook
        # POSTs here on first form-field focus so the 1a widget inferer can adapt.
        if getattr(self._app.state, "usage_collector", None) is not None:
            self._app.include_router(create_usage_routes())

    def _mount_file_routes(self, optional_auth_dep: Any = None) -> None:
        assert self._app is not None
        # #1551: the legacy /files surface honours the app's auth posture
        # (same expression the document/bulk routes use).
        _files_auth_posture = self._enable_auth and not self._enable_test_mode
        # File uploads
        if self._enable_files:
            # #1551: the FileService may already be constructed (early-init in
            # _setup_routes for route-generator wiring). Reuse it if so; build
            # it now if not (e.g. when _mount_file_routes is called standalone
            # in tests or subsystem contexts that skip _setup_routes).
            if self._file_service is None:
                self._ensure_file_service()
            # else: already early-constructed in _setup_routes (no reconstruction needed)
            file_service = self._file_service
            if file_service is None:
                raise RuntimeError("FileService required when enable_files is set")

            # Profile-based upload size limits (v1.0.0)
            _upload_limits = {"basic": 50, "standard": 10, "strict": 5}
            _max_mb = _upload_limits.get(self._security_profile, 10)

            # Per-entity/field size overrides from DSL (v0.39.0, #436)
            _field_size_overrides: dict[tuple[str, str], int] = {}
            if self._appspec:
                for _ent in self._appspec.domain.entities:
                    for _f in _ent.fields:
                        if _f.type.kind == FieldTypeKind.FILE and _f.type.max_size:
                            _field_size_overrides[(_ent.name, _f.name)] = _f.type.max_size

            # Post-upload callbacks: event bus + hook registry (v0.39.0, #437)
            # Stored on self so hook registry wiring can append later.
            self._upload_callbacks: list[Any] = []
            _upload_callbacks = self._upload_callbacks

            _upload_bus = self._app.state.services.event_bus

            async def _on_file_uploaded(
                entity_name: str,
                entity_id: str,
                field_name: str,
                file_meta: dict[str, Any],
                bus: Any = _upload_bus,
            ) -> None:
                data = {"field_name": field_name, **file_meta}
                await bus.emit_file_uploaded(entity_name, entity_id, data)

            _upload_callbacks.append(_on_file_uploaded)

            create_file_routes(
                self._app,
                file_service,
                max_upload_size=_max_mb * 1024 * 1024,
                field_size_overrides=_field_size_overrides,
                on_upload_callbacks=_upload_callbacks,
                optional_auth_dep=optional_auth_dep,
                require_auth_by_default=_files_auth_posture,
            )
            create_static_file_routes(
                self._app,
                base_path=str(self._files_path),
                url_prefix="/files",
                optional_auth_dep=optional_auth_dep,
                require_auth_by_default=_files_auth_posture,
            )

    def _mount_search_routes(self) -> None:
        assert self._app is not None
        # Cross-entity search endpoint (#782) — registered only when any
        # entity has declared search fields (surface search_fields: or
        # entity `searchable` modifiers).
        if self._entity_search_fields and self._repositories:
            from dazzle.http.runtime.search_routes import create_search_routes

            search_router = create_search_routes(
                repositories=self._repositories,
                entity_search_fields=self._entity_search_fields,
            )
            if search_router is not None:
                self._app.include_router(search_router)

    def _mount_fts_routes(self, auth_dep: Any) -> None:
        assert self._app is not None
        # #954 cycle 3 — tsvector-backed search endpoint(s). Registered
        # only when the AppSpec declares `search on <Entity>:` blocks.
        # The endpoint queries the cycle-2 search_vector column with
        # scope-aware filtering — RBAC-correct on day one.
        if getattr(self._appspec, "searches", None) and self._repositories:
            try:
                from dazzle.http.runtime.fts_routes import create_fts_routes

                fts_router = create_fts_routes(
                    appspec=self._appspec,
                    repositories=self._repositories,
                    fk_graph=getattr(self, "_fk_graph", None),
                    auth_dep=auth_dep,
                    admin_personas=getattr(self, "_admin_personas", None),
                )
                if fts_router is not None:
                    self._app.include_router(fts_router)
            except Exception:
                logger.warning("FTS routes mount failed", exc_info=True)

    def _ensure_file_service(self) -> None:
        """Construct FileService if missing (local disk + dazzle_files metadata).

        Used by file routes and by signing (TR-49 durable signed_document). Signing
        must persist PDFs even when general ``enable_files`` upload UI is off.
        """
        if self._file_service is not None:
            return
        from dazzle.http.runtime.file_storage import (
            FileMetadataStore,
            FileValidator,
            LocalStorageBackend,
        )

        storage = LocalStorageBackend(self._files_path, "/files")
        metadata_store = FileMetadataStore(database_url=self._database_url)
        validator = FileValidator()
        self._file_service = FileService(storage, metadata_store, validator)

    def _mount_signing_routes(self) -> None:
        assert self._app is not None
        # Native document signing endpoints (#1283 phase 3d) — mounted
        # when any entity has `signable: true`. The factory short-
        # circuits to None when no signable entity exists, so apps that
        # never use the primitive get a clean OpenAPI surface and never
        # import the fpdf2/pyhanko crypto chain.
        if self._repositories and self._appspec.domain:
            try:
                from dazzle.signing.routes import create_signing_routes

                # TR-49: signed-copy download needs FileService even if the
                # general file-upload surface is disabled.
                has_signable = any(
                    getattr(e, "signable", False) for e in self._appspec.domain.entities
                )
                if has_signable:
                    try:
                        self._ensure_file_service()
                    except Exception:
                        logger.warning(
                            "Could not construct FileService for signing PDF persistence",
                            exc_info=True,
                        )

                support_contact, resend_hook = self._resolve_signing_recovery()
                signing_router = create_signing_routes(
                    list(self._appspec.domain.entities),
                    repositories=self._repositories,
                    file_service=self._file_service,
                    branding=self._resolve_pdf_branding(),
                    project_root=self._project_root,
                    support_contact=support_contact,
                    resend_hook=resend_hook,
                )
                if signing_router is not None:
                    self._app.include_router(signing_router)
                    logger.info(
                        "  Signing: /sign/{entity}/{id} + /api/sign/{entity}/{id}"
                        " (file_service=%s)",
                        "yes" if self._file_service else "no",
                    )
            except ImportError:
                # dazzle.signing imports `cryptography` lazily but the
                # routes module itself is stdlib-only; an ImportError
                # here means the package is broken, not opted out.
                logger.exception("Failed to import dazzle.signing.routes")

    def _wire_byte_audit(self, audit_logger: "AuditLogger | None") -> None:
        """Set app.state.byte_audit whenever stored bytes can be served.

        The predicate is ``self._file_service is not None`` — the same
        condition that gates ``_mount_document_routes``.  This covers apps
        that have file fields but no RBAC/audit declarations (the "posture"
        access path): without this fix those apps would serve bytes with
        ``byte_audit = None`` → silently unaudited first-access.

        When ``audit_logger`` is already constructed (``_has_auditable_entities``
        was True) it is reused.  Otherwise a fresh ``AuditLogger`` is built
        from the same inputs, provided a database is configured.  If no database
        is available (a fileless / DB-less test rig) this is a no-op —
        ``serve_bytes`` already handles ``audit=None`` as a permitted no-op.

        Must be called in ``_setup_routes`` after ``self._file_service`` is
        potentially constructed (i.e. after the early-init block at #1551).
        """
        if not getattr(self, "_file_service", None):
            return
        _logger = audit_logger
        if _logger is None and self._database_url:
            from dazzle.http.runtime.audit_log import AuditLogger

            _logger = AuditLogger(
                database_url=self._database_url,
                audit_integrity=self._config.audit_integrity,
            )
            self._audit_logger = _logger
        if _logger is not None:
            assert self._app is not None
            from dazzle.http.runtime.byte_serving import ByteAudit

            self._app.state.byte_audit = ByteAudit(_logger)

    def _mount_document_routes(
        self, cedar_access_specs: Any, _fk_graph: Any, optional_auth_dep: Any, _admin_personas: Any
    ) -> None:
        """hx-pdf P1 (#162): the scope-gated document range proxy.

        Mounted whenever file storage is enabled — the route is the
        scope-correct read path for file fields (document access =
        entity access), the target of the pdf Hyperpart's
        ``data-dz-pdf-src``.
        """
        assert self._app is not None
        if not getattr(self, "_file_service", None):
            return
        self._app.include_router(
            create_document_routes(
                file_service=self._file_service,
                services=self.services_by_entity(),
                cedar_access_specs=cedar_access_specs,
                fk_graph=_fk_graph,
                optional_auth_dep=optional_auth_dep,
                admin_personas=_admin_personas,
                audit_logger=getattr(self, "_audit_logger", None),
                require_auth_by_default=self._enable_auth and not self._enable_test_mode,
            )
        )

    def _mount_bulk_routes(
        self, cedar_access_specs: Any, _fk_graph: Any, optional_auth_dep: Any, _admin_personas: Any
    ) -> None:
        assert self._app is not None
        # Bulk-action endpoints (#785) — registered when any list-mode
        # surface declares `ux: bulk_actions:`.
        if self._repositories and self._appspec.surfaces:
            from dazzle.http.runtime.bulk_routes import create_bulk_routes

            # `create_bulk_routes` expects `services` keyed by entity name
            # (it gates each bulk route on `entity_name in services` for the
            # scope-aware pre-read). `self._services` is keyed by *service*
            # name (`list_invoices`, ...), so pass the entity-keyed view
            # (#1181) — otherwise every bulk route is silently skipped under
            # auth ("no service for scope enforcement").
            # C0b: the all-matching resolver re-runs the echoed query through
            # gated_list with the SAME search/filter/visibility config the
            # list view used — parity is the §15 guarantee. (Same derivation
            # of the legacy visibility specs as the CRUD route generation.)
            _visibility_specs: dict[str, Any] = {
                entity.name: entity.metadata["access"]
                for entity in self._entities
                if entity.metadata and "access" in entity.metadata
            }
            bulk_router = create_bulk_routes(
                list(self._appspec.surfaces),
                repositories=self._repositories,
                services=self.services_by_entity(),
                cedar_access_specs=cedar_access_specs,
                fk_graph=_fk_graph,
                optional_auth_dep=optional_auth_dep,
                admin_personas=_admin_personas,
                entity_search_fields=self._entity_search_fields,
                entity_filter_fields=self._entity_filter_fields,
                entity_access_specs=_visibility_specs,
                entity_ref_targets=self._entity_ref_targets,
            )
            if bulk_router is not None:
                self._app.include_router(bulk_router)

    def _mount_parent_graph_routes(self, node_graph_specs: Any) -> None:
        assert self._app is not None
        # Parent-scoped graph endpoints (#781) — registered when any
        # graph_node: block declares `parent: <ref_field>`.
        if node_graph_specs and self._repositories:
            from dazzle.http.runtime.graph_routes import build_parent_graph_routes

            parent_graph_router = build_parent_graph_routes(
                node_graph_specs=node_graph_specs,
                entities=self._entities,
                repositories=self._repositories,
            )
            if parent_graph_router is not None:
                self._app.include_router(parent_graph_router)

    def _mount_test_routes(self) -> None:
        assert self._app is not None
        # Test routes
        if self._enable_test_mode and self._db_manager:
            from dazzle.http.runtime.test_routes import create_test_routes

            test_router = create_test_routes(
                db_manager=self._db_manager,
                repositories=self._repositories,
                entities=self._entities,
                auth_store=self._auth_store,
                personas=self._personas,
                project_root=self._project_root,
                user_ir_spec=self._user_ir_entity(),
            )
            self._app.include_router(test_router)

    def _mount_dev_routes(self) -> None:
        assert self._app is not None
        # Dev control plane
        if self._enable_dev_mode or self._enable_test_mode:
            from dazzle.http.runtime.control_plane import create_control_plane_routes

            control_plane_router = create_control_plane_routes(
                db_manager=self._db_manager,
                repositories=self._repositories if self._db_manager else None,
                entities=self._entities,
            )
            self._app.include_router(control_plane_router)

    # ------------------------------------------------------------------
    # Public build orchestrator
    # ------------------------------------------------------------------

    def build(self) -> FastAPI:
        """
        Build the FastAPI application.

        Returns:
            FastAPI application instance
        """
        self._create_app()
        self._setup_models()
        self._setup_database()
        self._setup_services()
        auth_dep, optional_auth_dep = self._setup_auth()
        self._setup_routes(auth_dep, optional_auth_dep)
        # Build subsystem context with auth deps, then run subsystems.
        # SystemRoutesSubsystem (last) handles _setup_optional_features and
        # _setup_system_routes.
        self._subsystem_ctx = self._build_subsystem_context(auth_dep, optional_auth_dep)
        self._run_subsystems()
        # #1399 slice 1 — SSE live push. After subsystems so self._event_framework
        # is set; before route validation so the SSE route is counted.
        self._wire_sse_live_push()
        # Sync integration_mgr and workspace_builder back from subsystem context
        if self._subsystem_ctx.integration_mgr is not None:
            self._integration_mgr = self._subsystem_ctx.integration_mgr
        if self._subsystem_ctx.workspace_builder is not None:
            self._workspace_builder = self._subsystem_ctx.workspace_builder
        # Sync channel_manager back so IntegrationManager-based properties work
        if self._subsystem_ctx.channel_manager is not None:
            if self._integration_mgr is not None:
                self._integration_mgr.channel_manager = self._subsystem_ctx.channel_manager

        # Validate routes for conflicts

        assert self._app is not None
        validate_routes(self._app)

        return self._app

    @property
    def app(self) -> FastAPI | None:
        """Get the FastAPI application (None if not built)."""
        return self._app

    @property
    def models(self) -> dict[str, type[BaseModel]]:
        """Get generated Pydantic models."""
        return self._models

    @property
    def services(self) -> dict[str, Any]:
        """Get service instances."""
        return self._services

    @property
    def entity_auto_includes(self) -> dict[str, list[str]]:
        """Per-entity ``auto_include`` relations (#1422 — threaded into the page
        layer so in-process reads hydrate the same relations the REST read does)."""
        return self._entity_auto_includes

    @property
    def create_invokers(self) -> dict[str, Any]:
        """Per-entity in-process CREATE invokers (#1422) — the experience-form POST
        calls these to mutate in-process via the enforced create path instead of
        self-fetching the REST endpoint."""
        return self._create_invokers

    def get_service(self, name: str) -> Any | None:
        """Get a service by name."""
        return self._services.get(name)

    def services_by_entity(self) -> dict[str, Any]:
        """Entity-name-keyed view of the services (#1181, #1428).

        `_services` is keyed by *service* name (`list_invoices`, ...), so an
        entity-name lookup against it silently misses. Delegates to the
        `ServiceFactory`, which owns the keying.
        """
        if self._service_factory is None:
            return {}
        return self._service_factory.services_by_entity()

    def service_for_entity(self, entity_name: str) -> Any | None:
        """Return a service wrapping `entity_name`'s repository, or None.

        Use this instead of `_services.get(entity_name)` — the latter keys by
        service name and silently resolves to None for entity-name callers
        (#1181).
        """
        if self._service_factory is None:
            return None
        return self._service_factory.service_for_entity(entity_name)

    @property
    def auth_store(self) -> AuthStore | None:
        """Get the auth store (None if auth not enabled)."""
        return self._auth_store

    @property
    def audit_logger(self) -> "AuditLogger | None":
        """Get the runtime audit logger (None if no auditable entities).

        Exposed so a graceful-shutdown path or an in-process test can call
        ``audit_logger.drain()`` to synchronously persist the audit queue —
        the deterministic alternative to waiting on the 1s background flush.
        """
        return self._audit_logger

    @property
    def auth_middleware(self) -> AuthMiddleware | None:
        """Get the auth middleware (None if auth not enabled)."""
        return self._auth_middleware

    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._enable_auth

    @property
    def file_service(self) -> FileService | None:
        """Get the file service (None if files not enabled)."""
        return self._file_service

    @property
    def files_enabled(self) -> bool:
        """Check if file uploads are enabled."""
        return self._enable_files

    @property
    def test_mode_enabled(self) -> bool:
        """Check if test mode is enabled."""
        return self._enable_test_mode

    @property
    def dev_mode_enabled(self) -> bool:
        """Check if dev mode is enabled."""
        return self._enable_dev_mode

    @property
    def repositories(self) -> dict[str, Any]:
        """Get repository instances."""
        return self._repositories

    @property
    def service_loader(self) -> ServiceLoader | None:
        """Get the domain service loader (None if not initialized)."""
        return self._service_loader

    @property
    def channel_manager(self) -> Any | None:
        """Get the channel manager (None if channels not enabled)."""
        return self._integration_mgr.channel_manager if self._integration_mgr else None

    @property
    def channels_enabled(self) -> bool:
        """Check if messaging channels are enabled."""
        return self._enable_channels and self.channel_manager is not None

    @property
    def process_manager(self) -> Any | None:
        """Get the process manager (None if processes not enabled)."""
        return self._process_manager

    @property
    def process_adapter(self) -> Any | None:
        """Get the process adapter (None if processes not enabled)."""
        return self._process_adapter

    @property
    def processes_enabled(self) -> bool:
        """Check if process workflows are enabled."""
        return self._enable_processes and self._process_manager is not None


__all__ = [
    "DazzleBackendApp",
    "ServerConfig",
]
