"""
Admin entity builder for DAZZLE.

Builds the synthetic platform EntitySpec objects used by the admin workspace.
Entities are profile-gated: some only appear for STANDARD and STRICT profiles.

Part of Issue #686 — universal admin workspace for auth-enabled Dazzle apps.
"""

from dazzle.core import ir
from dazzle.core.errors import LinkError
from dazzle.core.ir.admin_entities import ADMIN_ENTITY_DEFS
from dazzle.core.ir.feedback_widget import FeedbackWidgetSpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.security import SecurityConfig, SecurityProfile
from dazzle.core.ir.surfaces import (
    SurfaceAccessSpec,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)
from dazzle.core.ir.ux import SortSpec, UXSpec
from dazzle.core.ir.workspaces import (
    DisplayMode,
    NavGroupSpec,
    NavItemIR,
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)

# ---------------------------------------------------------------------------
# Field type parser (duplicated from linker._parse_field_type to avoid
# circular imports — linker imports IR which transitively imports many things)
# ---------------------------------------------------------------------------


def _parse_field_type(type_str: str) -> FieldType:
    """Parse a compact field type string into a FieldType.

    Handles: uuid, int, text, bool, float, datetime, str(N), enum[a,b,c].

    Args:
        type_str: Compact type descriptor, e.g. ``"str(200)"`` or
            ``"enum[healthy,degraded,unhealthy]"``.

    Returns:
        A :class:`~dazzle.core.ir.fields.FieldType` instance.

    Raises:
        ValueError: If *type_str* is not recognised.
    """
    if type_str == "uuid":
        return FieldType(kind=FieldTypeKind.UUID)
    if type_str == "int":
        return FieldType(kind=FieldTypeKind.INT)
    if type_str == "text":
        return FieldType(kind=FieldTypeKind.TEXT)
    if type_str == "bool":
        return FieldType(kind=FieldTypeKind.BOOL)
    if type_str == "float":
        return FieldType(kind=FieldTypeKind.FLOAT)
    if type_str == "datetime":
        return FieldType(kind=FieldTypeKind.DATETIME)
    if type_str.startswith("str(") and type_str.endswith(")"):
        max_len = int(type_str[4:-1])
        return FieldType(kind=FieldTypeKind.STR, max_length=max_len)
    if type_str.startswith("decimal(") and type_str.endswith(")"):
        parts = type_str[8:-1].split(",")
        return FieldType(
            kind=FieldTypeKind.DECIMAL,
            precision=int(parts[0]),
            scale=int(parts[1]),
        )
    if type_str.startswith("enum[") and type_str.endswith("]"):
        values = [v.strip() for v in type_str[5:-1].split(",")]
        return FieldType(kind=FieldTypeKind.ENUM, enum_values=values)
    if type_str.startswith("money(") and type_str.endswith(")"):
        currency = type_str[6:-1].strip()
        return FieldType(kind=FieldTypeKind.MONEY, currency_code=currency)
    if type_str.startswith("ref "):
        ref_entity = type_str[4:].strip()
        return FieldType(kind=FieldTypeKind.REF, ref_entity=ref_entity)
    raise ValueError(f"Unknown field type: {type_str!r}")


# ---------------------------------------------------------------------------
# Modifier map
# ---------------------------------------------------------------------------

_MODIFIER_MAP: dict[str, FieldModifier] = {
    "pk": FieldModifier.PK,
    "required": FieldModifier.REQUIRED,
    "unique": FieldModifier.UNIQUE,
}

# ---------------------------------------------------------------------------
# Profile gate helper
# ---------------------------------------------------------------------------


def _is_profile_included(profile_gate: str | None, active_profile: SecurityProfile) -> bool:
    """Return True if the entity should be included for *active_profile*.

    Args:
        profile_gate: ``None`` means available on all profiles; ``"standard"``
            means STANDARD and STRICT only.
        active_profile: The app's active :class:`SecurityProfile`.

    Returns:
        ``True`` if the entity should be included.
    """
    if profile_gate is None:
        return True
    if profile_gate == "standard":
        return active_profile in (SecurityProfile.STANDARD, SecurityProfile.STRICT)
    # Unknown gate → conservative exclude
    return False


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------


def _check_collisions(
    *,
    existing_entity_names: set[str],
    existing_workspace_names: set[str],
    synthetic_entity_names: set[str],
    synthetic_workspace_names: set[str],
) -> None:
    """Raise LinkError if user-declared names collide with synthetic names.

    Args:
        existing_entity_names: Entity names already declared in the DSL.
        existing_workspace_names: Workspace names already declared in the DSL.
        synthetic_entity_names: Entity names that will be auto-generated.
        synthetic_workspace_names: Workspace names that will be auto-generated.

    Raises:
        :class:`~dazzle.core.errors.LinkError`: If any name appears in both the
            user-declared set and the synthetic set.
    """
    entity_collisions = existing_entity_names & synthetic_entity_names
    workspace_collisions = existing_workspace_names & synthetic_workspace_names
    collisions = entity_collisions | workspace_collisions
    if collisions:
        names = ", ".join(sorted(collisions))
        raise LinkError(
            f"Name collision with framework-generated admin infrastructure: {names}. "
            "Rename your entity/workspace to avoid the conflict."
        )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

_ADMIN_PERSONAS: list[str] = ["admin", "super_admin"]
_READ_ONLY_OPS: tuple[ir.PermissionKind, ...] = (
    ir.PermissionKind.READ,
    ir.PermissionKind.LIST,
)


def _build_admin_entities(security: SecurityConfig) -> list[ir.EntitySpec]:
    """Build the list of synthetic platform EntitySpec objects for the admin workspace.

    Only entities whose ``profile_gate`` is satisfied by *security.profile* are
    included.  All generated entities are read-only (READ + LIST) and restricted
    to ``admin`` / ``super_admin`` personas.

    Args:
        security: Application security configuration (provides the active profile).

    Returns:
        A list of :class:`~dazzle.core.ir.domain.EntitySpec` objects ready to be
        merged into the app's domain.
    """
    entities: list[ir.EntitySpec] = []

    for name, title, intent, fields_tuple, patterns, profile_gate in ADMIN_ENTITY_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue

        # Build FieldSpec list from compact tuple definitions
        fields: list[FieldSpec] = []
        for field_name, type_str, modifiers, default in fields_tuple:
            field_type = _parse_field_type(type_str)
            mods = [_MODIFIER_MAP[m] for m in modifiers]
            fields.append(
                FieldSpec(name=field_name, type=field_type, modifiers=mods, default=default)
            )

        # Read-only access restricted to admin personas
        access = ir.AccessSpec(
            permissions=[
                ir.PermissionRule(
                    operation=op,
                    require_auth=True,
                    effect=ir.PolicyEffect.PERMIT,
                    personas=list(_ADMIN_PERSONAS),
                )
                for op in _READ_ONLY_OPS
            ]
        )

        entities.append(
            ir.EntitySpec(
                name=name,
                title=title,
                intent=intent,
                domain="platform",
                patterns=list(patterns),
                fields=fields,
                access=access,
            )
        )

    return entities


# ---------------------------------------------------------------------------
# Admin surface builder
# ---------------------------------------------------------------------------

# Each tuple: (surface_name, entity_ref, title, [(field, label), ...], profile_gate)
_ADMIN_SURFACE_DEFS: list[tuple[str, str, str, list[tuple[str, str]], str | None]] = [
    (
        "_admin_health",
        "SystemHealth",
        "System Health",
        [
            ("component", "Component"),
            ("status", "Status"),
            ("message", "Message"),
            ("checked_at", "Checked"),
        ],
        None,
    ),
    (
        "_admin_deploys",
        "DeployHistory",
        "Deploy History",
        [
            ("version", "Version"),
            ("status", "Status"),
            ("deployed_by", "Deployed By"),
            ("deployed_at", "Deployed At"),
        ],
        None,
    ),
    (
        "_admin_metrics",
        "SystemMetric",
        "System Metrics",
        [
            ("name", "Metric"),
            ("value", "Value"),
            ("unit", "Unit"),
            ("bucket_start", "Time"),
        ],
        "standard",
    ),
    (
        "_admin_processes",
        "ProcessRun",
        "Process Runs",
        [
            ("process_name", "Process"),
            ("status", "Status"),
            ("started_at", "Started"),
            ("current_step", "Step"),
        ],
        "standard",
    ),
    (
        "_admin_sessions",
        "SessionInfo",
        "Active Sessions",
        [
            ("email", "User"),
            ("ip_address", "IP"),
            ("created_at", "Started"),
            ("expires_at", "Expires"),
        ],
        "standard",
    ),
    (
        "_admin_logs",
        "LogEntry",
        "Application Logs",
        [
            ("timestamp", "Time"),
            ("level", "Level"),
            ("component", "Component"),
            ("message", "Message"),
        ],
        "standard",
    ),
    (
        "_admin_events",
        "EventTrace",
        "Event Traces",
        [
            ("topic", "Topic"),
            ("event_type", "Type"),
            ("key", "Key"),
            ("timestamp", "Time"),
        ],
        "standard",
    ),
]


_STATUS_FIELD_NAMES: frozenset[str] = frozenset({"status", "level", "state"})
# Categorical fields that aren't status-named but are legitimate filter
# candidates on admin tables. `event_type` on EventTrace and
# `component` on LogEntry are the canonical cases (#824).
_CATEGORICAL_FIELD_NAMES: frozenset[str] = frozenset(
    {"event_type", "component", "topic", "process_name"}
)
# Timestamp-like suffixes. `_start` / `_end` added in #824 so fields
# like SystemMetric.bucket_start / bucket_end get sensible
# newest-first sort defaults on admin tables.
_TIMESTAMP_SUFFIXES: tuple[str, ...] = (
    "_at",
    "_on",
    "time",
    "timestamp",
    "_start",
    "_end",
)
_NON_SEARCHABLE_FIELDS: frozenset[str] = frozenset(
    {"id", "status", "level", "state", "value", "unit"}
)


def _looks_like_timestamp(field_name: str) -> bool:
    lower = field_name.lower()
    return any(lower.endswith(suffix) for suffix in _TIMESTAMP_SUFFIXES)


def _default_admin_ux(field_defs: list[tuple[str, str]]) -> UXSpec:
    """Build a sensible default UXSpec for a framework-generated admin surface.

    The admin surfaces live outside the DSL so they can't carry author-
    chosen ux blocks. This helper derives plausible defaults (status /
    categorical filter, text-field search, timestamp sort desc, empty
    message) so the admin UI itself has proper UX affordances and the
    lint rule recognises the surface as intentional.

    Closes the improve-loop lint warnings originally surfaced on every
    framework app (v0.57.14), plus the #824 extension:

    - `_admin_metrics` (SystemMetric: bucket_start) — `_start`
      suffix added to `_TIMESTAMP_SUFFIXES` so it sorts.
    - `_admin_events` (EventTrace: event_type) — `event_type` added
      to `_CATEGORICAL_FIELD_NAMES` so it filters.
    - `_admin_logs` (LogEntry: level + component) — `component`
      added as a categorical filter alongside the existing `level`.
    """
    field_names = [name for name, _ in field_defs]
    filter_fields = [
        name
        for name in field_names
        if name in _STATUS_FIELD_NAMES or name in _CATEGORICAL_FIELD_NAMES
    ]
    search_fields = [
        name
        for name in field_names
        if name not in _NON_SEARCHABLE_FIELDS and not _looks_like_timestamp(name)
    ]
    sort_specs: list[SortSpec] = []
    for name in field_names:
        if _looks_like_timestamp(name):
            sort_specs = [SortSpec(field=name, direction="desc")]
            break
    return UXSpec(
        sort=sort_specs,
        filter=filter_fields,
        search=search_fields,
        empty_message="No records yet.",
    )


def _build_admin_surfaces(security: SecurityConfig) -> list[SurfaceSpec]:
    """Build admin LIST surfaces for platform entities.

    Only surfaces whose ``profile_gate`` is satisfied by *security.profile* are
    included. All generated surfaces require authentication and are restricted
    to ``admin`` / ``super_admin`` personas.

    Args:
        security: Application security configuration (provides the active profile).

    Returns:
        A list of :class:`~dazzle.core.ir.surfaces.SurfaceSpec` objects.
    """
    surfaces: list[SurfaceSpec] = []
    access = SurfaceAccessSpec(
        require_auth=True,
        allow_personas=list(_ADMIN_PERSONAS),
    )

    for surface_name, entity_ref, title, field_defs, profile_gate in _ADMIN_SURFACE_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue

        elements = [
            SurfaceElement(field_name=field_name, label=label) for field_name, label in field_defs
        ]
        section = SurfaceSection(name="main", elements=elements)

        surfaces.append(
            SurfaceSpec(
                name=surface_name,
                title=title,
                entity_ref=entity_ref,
                mode=SurfaceMode.LIST,
                sections=[section],
                access=access,
                ux=_default_admin_ux(field_defs),
            )
        )

    return surfaces


# ---------------------------------------------------------------------------
# Admin workspace builder
# ---------------------------------------------------------------------------

# Each tuple: (name, source, display, profile_gate, tenant_admin_visible, feedback_only, multi_tenant_only)
# Note: source is an entity name or None for sourceless regions (e.g. DIAGRAM).
_REGION_DEFS: list[tuple[str, str | None, DisplayMode, str | None, bool, bool, bool]] = [
    ("users", "User", DisplayMode.LIST, None, True, False, False),
    ("tenants", "Tenant", DisplayMode.LIST, "standard", False, False, True),
    ("sessions", "SessionInfo", DisplayMode.LIST, "standard", True, False, False),
    ("health", "SystemHealth", DisplayMode.GRID, None, True, False, False),
    ("metrics", "SystemMetric", DisplayMode.BAR_CHART, "standard", False, False, False),
    ("processes", "ProcessRun", DisplayMode.LIST, "standard", False, False, False),
    ("deploys", "DeployHistory", DisplayMode.LIST, None, True, False, False),
    ("feedback", "FeedbackReport", DisplayMode.LIST, None, True, True, False),
    ("logs", "LogEntry", DisplayMode.LIST, "standard", False, False, False),
    ("events", "EventTrace", DisplayMode.LIST, "standard", False, False, False),
    ("app_map", None, DisplayMode.DIAGRAM, None, False, False, False),
]

_NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("Management", ["users", "tenants", "sessions"]),
    ("Observability", ["health", "metrics", "processes", "logs"]),
    ("Operations", ["deploys", "feedback", "events", "app_map"]),
]

# Actions available on admin regions (region_name -> list of action defs)
# Each action: {"label": str, "endpoint": str, "method": str, "confirm": str, "persona": str}
_REGION_ACTIONS: dict[str, list[dict[str, str]]] = {
    "deploys": [
        {
            "label": "Trigger Deploy",
            "endpoint": "/_admin/api/deploys/trigger",
            "method": "POST",
            "confirm": "Trigger a new deployment?",
            "persona": "super_admin",
        },
    ],
}

# Row-level actions (shown per item)
_ROW_ACTIONS: dict[str, list[dict[str, str]]] = {
    "deploys": [
        {
            "label": "Rollback",
            "endpoint": "/_admin/api/deploys/{id}/rollback",
            "method": "POST",
            "confirm": "Roll back to this deployment?",
            "persona": "super_admin",
        },
    ],
}


def get_region_actions(region_name: str) -> list[dict[str, str]]:
    """Get header-level actions for an admin workspace region."""
    return list(_REGION_ACTIONS.get(region_name, []))


def get_row_actions(region_name: str) -> list[dict[str, str]]:
    """Get row-level actions for an admin workspace region."""
    return list(_ROW_ACTIONS.get(region_name, []))


def _build_regions(
    security: SecurityConfig,
    *,
    multi_tenant: bool,
    feedback_enabled: bool,
    tenant_admin: bool = False,
    existing_entity_names: set[str] | None = None,
) -> list[WorkspaceRegion]:
    """Build WorkspaceRegion list filtered by profile and feature flags.

    Args:
        security: Application security configuration.
        multi_tenant: Whether the app is multi-tenant.
        feedback_enabled: Whether the feedback widget is enabled.
        tenant_admin: If True, only include regions visible to tenant admins.
        existing_entity_names: Set of entity names (user-declared + synthetic) already
            present in the app.  Regions whose source entity is not in this set are
            silently excluded so the workspace passes validation.  When ``None``,
            no filtering is applied (all regions that pass other gates are included).

    Returns:
        A list of :class:`~dazzle.core.ir.workspaces.WorkspaceRegion` objects.
    """
    regions: list[WorkspaceRegion] = []

    for name, source, display, profile_gate, tenant_visible, feedback_only, mt_only in _REGION_DEFS:
        # Profile gate
        if not _is_profile_included(profile_gate, security.profile):
            continue
        # Feedback-only regions require feedback_enabled
        if feedback_only and not feedback_enabled:
            continue
        # Multi-tenant-only regions require multi_tenant
        if mt_only and not multi_tenant:
            continue
        # Tenant admin sees only tenant_admin_visible regions
        if tenant_admin and not tenant_visible:
            continue
        # Skip region if entity-name filtering is enabled and source is missing
        # (sourceless regions like DIAGRAM are always included)
        if source and existing_entity_names is not None and source not in existing_entity_names:
            continue

        regions.append(WorkspaceRegion(name=name, source=source, display=display, limit=None))

    return regions


def _build_nav_groups(region_names: set[str]) -> list[NavGroupSpec]:
    """Build NavGroupSpec list, including only groups with at least one member.

    Args:
        region_names: Set of region names that exist in the workspace.

    Returns:
        A list of :class:`~dazzle.core.ir.workspaces.NavGroupSpec` objects.
    """
    groups: list[NavGroupSpec] = []
    for label, members in _NAV_GROUPS:
        items = [NavItemIR(entity=m) for m in members if m in region_names]
        if items:
            groups.append(NavGroupSpec(label=label, items=items))
    return groups


def _build_admin_workspaces(
    security: SecurityConfig,
    *,
    multi_tenant: bool,
    feedback_enabled: bool,
    existing_entity_names: set[str] | None = None,
) -> list[WorkspaceSpec]:
    """Build admin workspace(s) for the application.

    Always produces ``_platform_admin``. In multi-tenant mode, also produces
    ``_tenant_admin`` with a restricted subset of regions.

    Args:
        security: Application security configuration.
        multi_tenant: Whether the app is multi-tenant.
        feedback_enabled: Whether the feedback widget is enabled.
        existing_entity_names: Set of all entity names (user-declared + synthetic)
            present in the app at workspace-build time.  Used to filter out regions
            whose source entity is not yet available so the workspace passes linker
            validation.

    Returns:
        A list of :class:`~dazzle.core.ir.workspaces.WorkspaceSpec` objects.
    """
    workspaces: list[WorkspaceSpec] = []

    # _platform_admin
    platform_personas = ["super_admin"] if multi_tenant else ["admin", "super_admin"]
    platform_regions = _build_regions(
        security,
        multi_tenant=multi_tenant,
        feedback_enabled=feedback_enabled,
        tenant_admin=False,
        existing_entity_names=existing_entity_names,
    )
    platform_region_names = {r.name for r in platform_regions}
    platform_nav = _build_nav_groups(platform_region_names)
    workspaces.append(
        WorkspaceSpec(
            name="_platform_admin",
            title="Platform Admin",
            regions=platform_regions,
            nav_groups=platform_nav,
            access=WorkspaceAccessSpec(
                level=WorkspaceAccessLevel.PERSONA,
                allow_personas=platform_personas,
            ),
        )
    )

    if multi_tenant:
        # _tenant_admin — subset of regions visible to tenant admins
        tenant_regions = _build_regions(
            security,
            multi_tenant=multi_tenant,
            feedback_enabled=feedback_enabled,
            tenant_admin=True,
            existing_entity_names=existing_entity_names,
        )
        tenant_region_names = {r.name for r in tenant_regions}
        tenant_nav = _build_nav_groups(tenant_region_names)
        workspaces.append(
            WorkspaceSpec(
                name="_tenant_admin",
                title="Tenant Admin",
                regions=tenant_regions,
                nav_groups=tenant_nav,
                access=WorkspaceAccessSpec(
                    level=WorkspaceAccessLevel.PERSONA,
                    allow_personas=["admin"],
                ),
            )
        )

    return workspaces


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def build_admin_infrastructure(
    *,
    entities: list[ir.EntitySpec],
    surfaces: list[ir.SurfaceSpec],
    security_config: SecurityConfig,
    app_config: ir.AppConfigSpec | None,
    feedback_widget: FeedbackWidgetSpec | None,
    existing_workspaces: list[WorkspaceSpec],
) -> tuple[list[ir.EntitySpec], list[ir.SurfaceSpec], list[WorkspaceSpec]]:
    """Build all admin infrastructure: entities, surfaces, workspaces.

    This is the single entry point called from the linker.

    Args:
        entities: User-declared entities (used for collision detection only).
        surfaces: User-declared surfaces (unused; reserved for future checks).
        security_config: Active security configuration for the app.
        app_config: Optional app-level configuration (provides multi_tenant flag).
        feedback_widget: Optional feedback widget spec (provides enabled flag).
        existing_workspaces: User-declared workspaces (used for collision detection).

    Returns:
        A 3-tuple of ``(admin_entities, admin_surfaces, admin_workspaces)`` ready
        to be merged into the app's domain.

    Raises:
        :class:`~dazzle.core.errors.LinkError`: If any generated name collides with
            a user-declared entity or workspace name.
    """
    multi_tenant = app_config.multi_tenant if app_config else False
    feedback_enabled = feedback_widget is not None and feedback_widget.enabled

    admin_entities = _build_admin_entities(security_config)
    admin_surfaces = _build_admin_surfaces(security_config)

    # Build the full set of entity names (user-declared + synthetic) so workspace
    # region sources are only included when their backing entity actually exists.
    existing_entity_names = {e.name for e in entities}
    all_entity_names = existing_entity_names | {e.name for e in admin_entities}
    # FeedbackReport is added by the linker before calling this function when
    # feedback is enabled; add it here too so the feedback workspace region passes.
    if feedback_enabled:
        all_entity_names.add("FeedbackReport")

    admin_workspaces = _build_admin_workspaces(
        security_config,
        multi_tenant=multi_tenant,
        feedback_enabled=feedback_enabled,
        existing_entity_names=all_entity_names,
    )
    existing_workspace_names = {w.name for w in existing_workspaces}
    _check_collisions(
        existing_entity_names=existing_entity_names,
        existing_workspace_names=existing_workspace_names,
        synthetic_entity_names={e.name for e in admin_entities},
        synthetic_workspace_names={w.name for w in admin_workspaces},
    )

    return admin_entities, admin_surfaces, admin_workspaces
