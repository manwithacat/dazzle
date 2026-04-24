from . import ir
from .archetype_expander import expand_archetypes, generate_archetype_surfaces
from .errors import LinkError
from .ir.feedback_widget import FEEDBACK_REPORT_FIELDS
from .ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from .ir.llm import AI_JOB_FIELDS
from .ir.security import SecurityConfig, SecurityProfile
from .linker_impl import (
    build_symbol_table,
    check_unused_imports,
    merge_fragments,
    resolve_dependencies,
    validate_module_access,
    validate_references,
)


def build_appspec(modules: list[ir.ModuleIR], root_module_name: str) -> ir.AppSpec:
    """
    Build a complete AppSpec by merging and linking all modules.

    Performs:
    1. Module dependency resolution (topological sort)
    2. Cycle detection
    3. Symbol table building
    4. Duplicate detection
    5. Reference validation
    6. Fragment merging

    Args:
        modules: List of parsed modules
        root_module_name: Name of the root module (from dazzle.toml)

    Returns:
        Complete, linked AppSpec

    Raises:
        LinkError: If linking fails (cycles, duplicates, unresolved refs, etc.)
    """
    if not modules:
        raise LinkError("No modules to link")

    if not root_module_name:
        raise LinkError("project.root must be set in dazzle.toml")

    # Find root module
    root_module = None
    for module in modules:
        if module.name == root_module_name:
            root_module = module
            break

    if not root_module:
        raise LinkError(
            f"Root module '{root_module_name}' not found. "
            f"Available modules: {[m.name for m in modules]}"
        )

    # Extract app name and title from root module
    app_name = root_module.app_name or root_module_name
    app_title = root_module.app_title or app_name

    # Build security config from app config (v0.11.0)
    security_config = _build_security_config(root_module.app_config)

    # Stage 3: Full linking implementation

    # 1. Resolve dependencies and detect cycles
    sorted_modules = resolve_dependencies(modules)

    # 2. Build symbol table (detects duplicates)
    symbols = build_symbol_table(sorted_modules)

    # 3. Validate module access (enforce use declarations)
    access_errors = validate_module_access(sorted_modules, symbols)
    if access_errors:
        error_msg = "Module access validation failed:\n" + "\n".join(
            f"  - {e}" for e in access_errors
        )
        raise LinkError(error_msg)

    # 4. Validate all cross-references
    errors = validate_references(symbols)
    if errors:
        error_msg = "Reference validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise LinkError(error_msg)

    # 5. Expand archetypes (v0.10.3)
    # - Merge fields from extended archetypes
    # - Apply semantic archetype expansions (settings, tenant, tenant_settings)
    # - Inject tenant FK into non-settings entities
    expanded_entities = expand_archetypes(list(symbols.entities.values()), symbols)

    # Update symbol table with expanded entities
    symbols._domain.entities = {e.name: e for e in expanded_entities}

    # 6. Generate auto-surfaces for semantic archetypes
    existing_surfaces = list(symbols.surfaces.values())
    auto_surfaces = generate_archetype_surfaces(expanded_entities, existing_surfaces)

    # Add auto-generated surfaces to symbol table
    for surface in auto_surfaces:
        symbols.surfaces[surface.name] = surface

    # 7. Check for unused imports (v0.14.1)
    unused_import_warnings = check_unused_imports(sorted_modules, symbols)

    # 8. Merge fragments into unified structure
    merged_fragment = merge_fragments(sorted_modules, symbols)

    # 9. Auto-generate AIJob entity when LLM config is present (#376)
    entities = merged_fragment.entities
    if merged_fragment.llm_config is not None and not any(e.name == "AIJob" for e in entities):
        entities = [*entities, _build_ai_job_entity()]

    # 9b. Auto-generate FeedbackReport entity + surfaces when feedback_widget is enabled
    fw = merged_fragment.feedback_widget
    surfaces = merged_fragment.surfaces
    if fw is not None and fw.enabled and not any(e.name == "FeedbackReport" for e in entities):
        entities = [*entities, _build_feedback_report_entity()]
        surfaces = [
            *surfaces,
            _build_feedback_create_surface(),
            _build_feedback_admin_surface(),
            _build_feedback_edit_surface(),
        ]

    # 9c. Auto-generate admin platform entities, surfaces, and workspaces (#686)
    from .admin_builder import build_admin_infrastructure

    admin_entities, admin_surfaces, admin_workspaces = build_admin_infrastructure(
        entities=entities,
        surfaces=surfaces,
        security_config=security_config,
        app_config=root_module.app_config,
        feedback_widget=merged_fragment.feedback_widget,
        existing_workspaces=merged_fragment.workspaces,
    )
    entities = [*entities, *admin_entities]
    surfaces = [*surfaces, *admin_surfaces]

    # 10. Build FK graph and compile scope predicates
    from .ir.fk_graph import FKGraph
    from .ir.predicate_builder import build_scope_predicate

    fk_graph = FKGraph.from_entities(list(entities))
    entities = _compile_scope_predicates(entities, fk_graph, build_scope_predicate)

    # 10b. Derive verifiable triples
    from .ir.triples import derive_triples

    triples = derive_triples(entities, surfaces, merged_fragment.personas)

    # 11. Build final AppSpec
    return ir.AppSpec(
        name=app_name,
        title=app_title,
        version="0.1.0",
        domain=ir.DomainSpec(entities=entities),
        fk_graph=fk_graph,
        triples=triples,
        surfaces=surfaces,
        workspaces=[*merged_fragment.workspaces, *admin_workspaces],
        experiences=merged_fragment.experiences,
        apis=merged_fragment.apis,
        foreign_models=merged_fragment.foreign_models,
        integrations=merged_fragment.integrations,
        tests=merged_fragment.tests,
        personas=merged_fragment.personas,  # v0.8.5
        scenarios=merged_fragment.scenarios,  # v0.8.5
        stories=merged_fragment.stories,  # v0.22.0 Stories
        rules=merged_fragment.rules,  # v0.41.0 Convergent BDD
        questions=merged_fragment.questions,  # v0.41.0 Convergent BDD
        rhythms=merged_fragment.rhythms,  # v0.39.0 Rhythms
        security=security_config,  # v0.11.0 Security
        llm_config=merged_fragment.llm_config,  # v0.21.0 LLM Jobs
        llm_models=merged_fragment.llm_models,  # v0.21.0 LLM Jobs
        llm_intents=merged_fragment.llm_intents,  # v0.21.0 LLM Jobs
        processes=merged_fragment.processes,  # v0.23.0 Process Workflows
        schedules=merged_fragment.schedules,  # v0.23.0 Process Workflows
        ledgers=merged_fragment.ledgers,  # v0.24.0 TigerBeetle Ledgers
        transactions=merged_fragment.transactions,  # v0.24.0 TigerBeetle Ledgers
        enums=merged_fragment.enums,  # v0.25.0 Shared Enums
        views=merged_fragment.views,  # v0.25.0 Views
        webhooks=merged_fragment.webhooks,  # v0.25.0 Webhooks
        approvals=merged_fragment.approvals,  # v0.25.0 Approvals
        slas=merged_fragment.slas,  # v0.25.0 SLAs
        islands=merged_fragment.islands,  # UI Islands
        grant_schemas=merged_fragment.grant_schemas,  # v0.42.0 Runtime RBAC
        params=merged_fragment.params,  # v0.44.0 Runtime Parameters
        feedback_widget=merged_fragment.feedback_widget,  # Feedback Widget
        subprocessors=merged_fragment.subprocessors,  # v0.61.0 Analytics / Privacy
        analytics=merged_fragment.analytics,  # v0.61.0 Phase 3
        audit_trail=root_module.app_config.audit_trail if root_module.app_config else False,
        metadata={
            "modules": [m.name for m in sorted_modules],
            "root_module": root_module_name,
            "link_warnings": unused_import_warnings,  # v0.14.1
        },
    )


def _compile_scope_predicates(
    entities: list[ir.EntitySpec],
    fk_graph: object,
    build_scope_predicate: object,
) -> list[ir.EntitySpec]:
    """Compile scope predicates for all entities with scope rules.

    For each entity that has access.scopes, calls build_scope_predicate on
    each ScopeRule's condition and attaches the resulting ScopePredicate to
    the rule's ``predicate`` field.

    Because Pydantic models are frozen, this reconstructs the ScopeRule,
    AccessSpec, and EntitySpec using model_copy(update={...}).

    Args:
        entities:             List of entity specifications.
        fk_graph:             FKGraph built from the entities.
        build_scope_predicate: Callable (condition, entity_name, fk_graph) → ScopePredicate.

    Returns:
        Updated list of entity specifications with predicates attached.
    """
    result: list[ir.EntitySpec] = []
    for entity in entities:
        if entity.access is None or not entity.access.scopes:
            result.append(entity)
            continue

        compiled_scopes: list[ir.ScopeRule] = []
        for rule in entity.access.scopes:
            predicate = build_scope_predicate(rule.condition, entity.name, fk_graph)  # type: ignore[operator]
            compiled_scopes.append(rule.model_copy(update={"predicate": predicate}))

        new_access = entity.access.model_copy(update={"scopes": compiled_scopes})
        result.append(entity.model_copy(update={"access": new_access}))

    return result


def _build_security_config(app_config: ir.AppConfigSpec | None) -> SecurityConfig:
    """
    Build SecurityConfig from app configuration.

    Args:
        app_config: App configuration from root module

    Returns:
        SecurityConfig with profile-based defaults
    """
    if app_config is None:
        return SecurityConfig.from_profile(SecurityProfile.BASIC)

    # Parse security profile
    profile_str = app_config.security_profile.lower()
    try:
        profile = SecurityProfile(profile_str)
    except ValueError:
        # Default to basic if invalid profile
        profile = SecurityProfile.BASIC

    # Build config with profile defaults
    return SecurityConfig.from_profile(
        profile,
        multi_tenant=app_config.multi_tenant,
    )


def _parse_field_type(type_str: str) -> FieldType:
    """Parse a compact field type string into a FieldType.

    Supports: uuid, str(N), int, text, decimal(P,S), bool,
    datetime, enum[a,b,c].
    """
    if type_str == "uuid":
        return FieldType(kind=FieldTypeKind.UUID)
    if type_str == "int":
        return FieldType(kind=FieldTypeKind.INT)
    if type_str == "text":
        return FieldType(kind=FieldTypeKind.TEXT)
    if type_str == "bool":
        return FieldType(kind=FieldTypeKind.BOOL)
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
    if type_str == "float":
        return FieldType(kind=FieldTypeKind.FLOAT)
    raise ValueError(f"Unknown field type: {type_str}")


_MODIFIER_MAP = {
    "pk": FieldModifier.PK,
    "required": FieldModifier.REQUIRED,
    "unique": FieldModifier.UNIQUE,
}


def _build_ai_job_entity() -> ir.EntitySpec:
    """Build the auto-generated AIJob system entity for AI cost tracking."""
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in AI_JOB_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    # Default access: any authenticated user can perform all operations.
    # AIJob records are internal system audit data — no role gating needed,
    # but unauthenticated access is denied.
    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(operation=op, require_auth=True, effect=ir.PolicyEffect.PERMIT)
            for op in ir.PermissionKind
        ]
    )

    return ir.EntitySpec(
        name="AIJob",
        title="AI Job",
        intent="Tracks every AI gateway call with token counts, cost, and audit trail",
        domain="platform",
        patterns=["system", "audit"],
        fields=fields,
        access=access,
    )


def _build_feedback_report_entity() -> ir.EntitySpec:
    """Build the auto-generated FeedbackReport entity for in-app feedback."""
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in FEEDBACK_REPORT_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    # v0.61.6 (#859): scope rules split so non-admins see/update only their
    # own reports, while admins see everything. Previously ``scope: all
    # for: *`` opened LIST to every auth persona — but the admin surface's
    # ``allow_personas=["admin","super_admin"]`` leaked onto the entity's
    # LIST endpoint, producing 403s for the feedback-widget's resolved-
    # report polls for non-admin users.
    _ops = (
        ir.PermissionKind.CREATE,
        ir.PermissionKind.READ,
        ir.PermissionKind.LIST,
        ir.PermissionKind.UPDATE,
        ir.PermissionKind.DELETE,
    )

    # "reported_by = current_user.email" — standard Dazzle runtime pattern.
    _self_cond = ir.ConditionExpr(
        comparison=ir.Comparison(
            field="reported_by",
            operator=ir.ComparisonOperator.EQUALS,
            value=ir.ConditionValue(literal="current_user.email"),
        )
    )
    _scope_rules: list[ir.ScopeRule] = []
    for op in _ops:
        # Default: any authenticated persona sees / acts on own rows only.
        _scope_rules.append(ir.ScopeRule(operation=op, condition=_self_cond, personas=["*"]))
        # Admin: full row visibility.
        _scope_rules.append(
            ir.ScopeRule(
                operation=op,
                condition=None,
                personas=["admin", "super_admin"],
            )
        )

    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(operation=op, require_auth=True, effect=ir.PolicyEffect.PERMIT)
            for op in _ops
        ],
        scopes=_scope_rules,
    )

    # State machine: new → triaged → in_progress → resolved → verified
    #                                  ↓ wont_fix / duplicate
    transitions = [
        ir.StateTransition(from_state="new", to_state="triaged"),
        ir.StateTransition(from_state="triaged", to_state="in_progress"),
        ir.StateTransition(from_state="triaged", to_state="wont_fix"),
        ir.StateTransition(from_state="triaged", to_state="duplicate"),
        ir.StateTransition(from_state="triaged", to_state="resolved"),  # agent shortcut
        ir.StateTransition(from_state="in_progress", to_state="resolved"),
        ir.StateTransition(from_state="in_progress", to_state="wont_fix"),
        ir.StateTransition(from_state="resolved", to_state="verified"),
        ir.StateTransition(from_state="resolved", to_state="in_progress"),
    ]
    state_machine = ir.StateMachineSpec(
        status_field="status",
        states=["new", "triaged", "in_progress", "resolved", "verified", "wont_fix", "duplicate"],
        transitions=transitions,
    )

    return ir.EntitySpec(
        name="FeedbackReport",
        title="Feedback Report",
        intent="In-app feedback from any user — issues, impressions, improvement suggestions",
        domain="platform",
        patterns=["lifecycle", "feedback", "audit"],
        fields=fields,
        access=access,
        state_machine=state_machine,
    )


def _build_feedback_create_surface() -> ir.SurfaceSpec:
    """Build a headless CREATE surface for FeedbackReport (API-only).

    The widget JS is the UI — no sections needed. Any authenticated user
    can submit feedback via POST /feedbackreports.
    """
    return ir.SurfaceSpec(
        name="feedback_create",
        title="Submit Feedback",
        entity_ref="FeedbackReport",
        mode=ir.SurfaceMode.CREATE,
        sections=[],
        access=ir.SurfaceAccessSpec(require_auth=True),
        headless=True,
    )


def _build_feedback_admin_surface() -> ir.SurfaceSpec:
    """Build a LIST+VIEW admin surface for FeedbackReport.

    Renders at /app/feedbackreports. Shows triage fields for admin review.
    """
    elements = [
        ir.SurfaceElement(field_name=name, label=label)
        for name, label in [
            ("category", "Category"),
            ("severity", "Severity"),
            ("description", "Description"),
            ("status", "Status"),
            ("reported_by", "Submitted By"),
            ("page_url", "Page URL"),
            ("created_at", "Created"),
        ]
    ]
    # Sensible defaults so apps don't see "surface has no ux block" lint
    # warnings on every feedback-enabled project.
    # v0.61.13 (#869): notification_sent + reported_by added to the filter
    # list so the feedback widget's resolved-report poll can actually narrow
    # server-side. Without them the ``notification_sent=false`` predicate
    # was silently ignored — the widget re-fired its toast on every page
    # load because GET /feedbackreports kept returning already-acknowledged
    # rows. reported_by matters for admins (entity scope is ``all``); for
    # non-admins the entity-level ``reported_by = current_user.email``
    # scope already restricts rows, so adding it here is a no-op there.
    ux = ir.UXSpec(
        sort=[ir.SortSpec(field="created_at", direction="desc")],
        filter=["category", "severity", "status", "notification_sent", "reported_by"],
        search=["description", "reported_by"],
        empty_message="No feedback yet.",
    )
    return ir.SurfaceSpec(
        name="feedback_admin",
        title="Feedback Reports",
        entity_ref="FeedbackReport",
        mode=ir.SurfaceMode.LIST,
        sections=[ir.SurfaceSection(name="main", title="Feedback", elements=elements)],
        # v0.61.6 (#859): allow_personas dropped — persona-level restriction
        # was leaking onto the entity's shared LIST/PUT endpoints, 403ing the
        # non-admin feedback-widget polls. Entity-level ``reported_by =
        # current_user.email`` scope now restricts non-admins to their own
        # rows; admins keep full visibility via the ``all for: admin`` scope.
        access=ir.SurfaceAccessSpec(require_auth=True),
        ux=ux,
    )


def _build_feedback_edit_surface() -> ir.SurfaceSpec:
    """Build a headless EDIT surface for FeedbackReport (triage/resolve).

    Admin-only. Exposes status transitions + agent triage fields via
    PUT /feedbackreports/{id}. Fields are grouped into three logical
    sections so the form passes the multi-section-form layout rule.
    """

    def _mk(name: str, label: str) -> ir.SurfaceElement:
        return ir.SurfaceElement(field_name=name, label=label)

    status_section = ir.SurfaceSection(
        name="status",
        title="Status",
        elements=[_mk("status", "Status"), _mk("assigned_to", "Assigned To")],
    )
    triage_section = ir.SurfaceSection(
        name="triage",
        title="Triage Notes",
        elements=[
            _mk("agent_notes", "Agent Notes"),
            _mk("agent_classification", "Classification"),
        ],
    )
    relations_section = ir.SurfaceSection(
        name="relations",
        title="Related Context",
        elements=[
            _mk("related_entity", "Related Entity"),
            _mk("related_story", "Related Story"),
        ],
    )

    return ir.SurfaceSpec(
        name="feedback_edit",
        title="Edit Feedback Report",
        entity_ref="FeedbackReport",
        mode=ir.SurfaceMode.EDIT,
        sections=[status_section, triage_section, relations_section],
        # v0.61.6 (#859): allow_personas dropped — persona gate was
        # 403ing the feedback widget's _markNotified PUT for non-admin
        # users. Entity-level ``reported_by = current_user.email`` scope
        # restricts non-admins to updating only their own rows; admins
        # keep full UPDATE access via the ``all for: admin`` scope. The
        # edit-UI page itself is still at /app/feedbackreports/{id}/edit
        # and rendering is filtered by the same scope — non-admins see
        # only their own rows there too.
        access=ir.SurfaceAccessSpec(require_auth=True),
    )
