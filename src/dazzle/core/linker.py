from . import ir
from .archetype_expander import _to_snake_case, expand_archetypes, generate_archetype_surfaces
from .errors import (
    E_SUBTYPE_DUPLICATE_PK,
    E_SUBTYPE_FIELD_NAME_OVERLAP,
    E_SUBTYPE_GRANT_INCOMPLETE,
    E_SUBTYPE_KIND_RESERVED,
    E_SUBTYPE_OF_CYCLE,
    E_SUBTYPE_OF_MULTILEVEL,
    E_SUBTYPE_OF_UNKNOWN_BASE,
    E_SUBTYPE_SOFT_DELETE_ON_CHILD,
    LinkError,
)
from .ir.audit import AUDIT_ENTRY_FIELDS
from .ir.feedback_widget import FEEDBACK_REPORT_FIELDS
from .ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from .ir.fk_graph import FKGraph
from .ir.jobs import JOB_RUN_FIELDS
from .ir.llm import AI_JOB_FIELDS
from .ir.onboarding_state import ONBOARDING_STATE_FIELDS
from .ir.security import SecurityConfig, SecurityProfile
from .linker_impl import (
    build_symbol_table,
    check_unused_imports,
    merge_fragments,
    resolve_dependencies,
    validate_module_access,
    validate_references,
)
from .tenancy_inject import inject_partition_key


class RenderValidationError(ValueError):
    """A render: clause referenced a renderer that is not registered."""


def build_appspec(
    modules: list[ir.ModuleIR],
    root_module_name: str,
    *,
    known_renderers: set[str] | None = None,
) -> ir.AppSpec:
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
        entities = [*entities, _build_ai_job_entity(_derive_aijob_subject_targets(merged_fragment))]

    # #1454: ProcessRun when any process runs an llm_intent step — the run is the AIJob subject.
    _has_llm_step = any(
        getattr(s, "kind", None) == ir.ProcessStepKind.LLM_INTENT
        for p in merged_fragment.processes
        for s in p.steps
    )
    if _has_llm_step and not any(e.name == "ProcessRun" for e in entities):
        entities = [*entities, _build_process_run_entity()]

    # 9a. Auto-generate AuditEntry entity when any `audit on X:` block is
    # present (#956 cycle 2). Single shared system entity for all
    # audited entity types — `entity_type` discriminator on each row.
    surfaces = merged_fragment.surfaces
    if merged_fragment.audits and not any(e.name == "AuditEntry" for e in entities):
        entities = [*entities, _build_audit_entry_entity()]
        # #991 — pair the entity with an admin LIST surface so the
        # route generator emits CRUD endpoints (/auditentries +
        # /api/auditentry) for external inspection. Mirrors the
        # FeedbackReport pattern below.
        surfaces = [*surfaces, _build_audit_entry_admin_surface()]

    # 9aa. Auto-generate JobRun entity when any `job X:` block is
    # present (#953 cycle 2). Single shared platform entity holding
    # one row per worker invocation — `job_name` discriminator. The
    # cycle-3 worker writes here; the cycle-4 scheduler reads `status`
    # to skip already-running scheduled jobs.
    if merged_fragment.jobs and not any(e.name == "JobRun" for e in entities):
        entities = [*entities, _build_job_run_entity()]
        # #991 — admin LIST surface so the route generator emits
        # CRUD endpoints for the worker (and operator triage tools).
        surfaces = [*surfaces, _build_job_run_admin_surface()]

    # 9b. Auto-generate FeedbackReport entity + surfaces when feedback_widget is enabled
    fw = merged_fragment.feedback_widget
    if fw is not None and fw.enabled and not any(e.name == "FeedbackReport" for e in entities):
        entities = [*entities, _build_feedback_report_entity()]
        surfaces = [
            *surfaces,
            _build_feedback_create_surface(),
            _build_feedback_admin_surface(),
            _build_feedback_edit_surface(),
        ]

    # 9b.1 Auto-generate OnboardingState entity when any `guide` block is
    # declared (v0.71.1). Per-(user, guide, version) progression rows.
    # Apps with no guides don't pay the table cost.
    if merged_fragment.guides and not any(e.name == "OnboardingState" for e in entities):
        entities = [*entities, _build_onboarding_state_entity()]

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

    # 9c.1 Validate `subtype_of:` declarations and synthesise discriminator
    # (#1217 Phase 3e.ii). Must precede _inject_soft_delete_fields so rule
    # 10 (soft_delete on child) fires before auto-injection masks intent.
    entities = _link_subtypes(entities, merged_fragment.grant_schemas)

    # 9d. Inject `deleted_at: datetime optional` for entities with
    # the `soft_delete` directive (#1218 Option A). The runtime filters
    # read paths on `deleted_at IS NULL` and the DELETE handler
    # stamps the column instead of issuing a hard DELETE — both
    # require the column to exist. Authors who already declared
    # `deleted_at` explicitly keep theirs.
    entities = _inject_soft_delete_fields(entities)

    # 9e. Inject the 11 native-signing fields + default audit on
    # entities with `signable: true` (#1283 phase 3). The runtime
    # signing routes + `dazzle.signing` backend (shipped phase 2)
    # read these columns. Project-declared fields with the same name
    # take precedence — explicit always wins.
    entities = _inject_signable_fields(entities)

    # 9f. Inject the framework-owned tenant discriminator (RLS tenancy Phase A).
    # Runs here — after merge (tenancy is available) and after all other entity
    # injection, but before the FK graph — so the injected `tenant_id` is seen by
    # the FK graph, scope-predicate compilation, converters, and schema gen.
    entities = inject_partition_key(list(entities), merged_fragment.tenancy)

    # 10. Build FK graph and compile scope predicates
    from .ir.fk_graph import FKGraph
    from .ir.predicate_builder import build_scope_predicate

    fk_graph = FKGraph.from_entities(list(entities))
    entities = _compile_scope_predicates(entities, fk_graph, build_scope_predicate)

    # 10a.1 — derive parent-before-child step order for create-DAG atomic flows
    # (#1315). Declared `steps` order is preserved; `derived_step_order` carries
    # the FK-topological permutation when (and only when) reordering is needed.
    atomic_flows = _derive_atomic_step_orders(merged_fragment.atomic_flows, fk_graph)
    atomic_flows = _derive_flow_invariant_anchors(atomic_flows, fk_graph)

    # 10b. Derive verifiable triples
    from .ir.triples import derive_triples

    triples = derive_triples(entities, surfaces, merged_fragment.personas)

    # 10c. Validate render: references against the registered renderer set.
    # Skipped when no registry is supplied (lint/tests/non-runtime callers).
    workspaces = [*merged_fragment.workspaces, *admin_workspaces]
    if known_renderers is not None:
        _validate_render_references(surfaces, workspaces, known_renderers)

    # 10c.1 Linker rule 9 — validate subtype_panel: blocks (#1217 Phase 3e.v).
    # Raises on unknown discriminator / non-base host; returns warnings joined
    # into link_warnings below.
    subtype_panel_warnings = _validate_subtype_panels(entities, surfaces)

    # 10d. Guide concordance — every guide step's target / completion /
    # cta must resolve against the actual DSL state (#1106 follow-up,
    # v0.71.0). Drift becomes a compile error, not a runtime surprise.
    from .guide_concordance import check_guide_concordance

    guide_errors, _guide_warnings = check_guide_concordance(
        merged_fragment.guides,
        surfaces=surfaces,
        entities=entities,
        personas=merged_fragment.personas,
        streams=merged_fragment.streams,
    )
    if guide_errors:
        error_msg = "Guide concordance failed:\n" + "\n".join(f"  - {e}" for e in guide_errors)
        raise LinkError(error_msg)

    # 11. Build final AppSpec
    return ir.AppSpec(
        name=app_name,
        title=app_title,
        version="0.1.0",
        app_config=root_module.app_config,
        domain=ir.DomainSpec(entities=entities),
        fk_graph=fk_graph,
        triples=triples,
        surfaces=surfaces,
        workspaces=workspaces,
        navs=merged_fragment.navs,  # v0.61.95 (#926); persona nav_ref check (#1324)
        experiences=merged_fragment.experiences,
        apis=merged_fragment.apis,
        domain_services=merged_fragment.domain_services,  # #1070
        # #1075 — propagate the remaining shared ModuleFragment/AppSpec fields.
        archetypes=merged_fragment.archetypes,
        assets=merged_fragment.assets,
        channels=merged_fragment.channels,
        data_products=merged_fragment.data_products,
        documents=merged_fragment.documents,
        e2e_flows=merged_fragment.e2e_flows,
        atomic_flows=atomic_flows,
        event_model=merged_fragment.event_model,
        fixtures=merged_fragment.fixtures,
        hless_pragma=merged_fragment.hless_pragma,
        interfaces=merged_fragment.interfaces,
        messages=merged_fragment.messages,
        policies=merged_fragment.policies,
        projections=merged_fragment.projections,
        streams=merged_fragment.streams,
        subscriptions=merged_fragment.subscriptions,
        templates=merged_fragment.templates,
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
        notifications=merged_fragment.notifications,  # v0.34.0 Notifications (#952)
        tenancy=merged_fragment.tenancy,  # #957 cycle 3
        jobs=merged_fragment.jobs,  # #953 Background Jobs
        audits=merged_fragment.audits,  # #956 Audit Trail
        searches=merged_fragment.searches,  # #954 Full-Text Search
        grant_schemas=merged_fragment.grant_schemas,  # v0.42.0 Runtime RBAC
        params=merged_fragment.params,  # v0.44.0 Runtime Parameters
        feedback_widget=merged_fragment.feedback_widget,  # Feedback Widget
        guides=merged_fragment.guides,  # Guided onboarding (v0.71.0)
        subprocessors=merged_fragment.subprocessors,  # v0.61.0 Analytics / Privacy
        analytics=merged_fragment.analytics,  # v0.61.0 Phase 3
        audit_trail=root_module.app_config.audit_trail if root_module.app_config else False,
        metadata={
            "modules": [m.name for m in sorted_modules],
            "root_module": root_module_name,
            "link_warnings": [
                *unused_import_warnings,  # v0.14.1
                *subtype_panel_warnings,  # v0.71.184 (#1217 Phase 3e.v)
            ],
        },
    )


def _link_subtypes(
    entities: list[ir.EntitySpec],
    grant_schemas: list[ir.GrantSchemaSpec],
) -> list[ir.EntitySpec]:
    """Validate `subtype_of:` declarations and synthesise discriminators (#1217 Phase 3e.ii).

    See ADR-0026. Enforces rules 1, 2, 3/5, 6, 7, 10, and 11 from spec §5. On
    success, populates `subtype_children` on each base and appends a `kind`
    enum field listing the snake_case child names.
    """
    by_name = {e.name: e for e in entities}
    # Rule 11: a grant on a child subtype would silently broaden delegated
    # access to rows the base's RBAC posture intends to govern. Require the
    # author to declare the base grant explicitly so the policy is visible.
    scoped_entities = {gs.scope for gs in grant_schemas}

    children_by_base: dict[str, list[str]] = {}
    for entity in entities:
        if entity.subtype_of is None:
            continue
        base_name = entity.subtype_of

        if base_name == entity.name:
            raise LinkError(
                f"{E_SUBTYPE_OF_CYCLE}: Entity '{entity.name}' declares "
                f"subtype_of itself; cycles are not permitted."
            )

        if base_name not in by_name:
            raise LinkError(
                f"{E_SUBTYPE_OF_UNKNOWN_BASE}: Entity '{entity.name}' declares "
                f"subtype_of '{base_name}', but no entity by that name exists."
            )

        parent = by_name[base_name]
        if parent.subtype_of is not None:
            raise LinkError(
                f"{E_SUBTYPE_OF_MULTILEVEL}: Entity '{entity.name}' declares "
                f"subtype_of '{base_name}', which itself declares "
                f"subtype_of '{parent.subtype_of}'. Subtype hierarchies must be flat."
            )

        base_field_names = {f.name for f in parent.fields}
        for f in entity.fields:
            if ir.FieldModifier.PK in f.modifiers:
                raise LinkError(
                    f"{E_SUBTYPE_DUPLICATE_PK}: Entity '{entity.name}' is a "
                    f"subtype of '{base_name}' and must not declare its own "
                    f"primary key (field '{f.name}'). The PK is inherited from the base."
                )
            # #1236: a child field that shadows a base field name would
            # produce an ambiguous SELECT under the auto-JOIN (the column
            # appears in both ``"{Child}".*`` and the aliased base column).
            if f.name in base_field_names:
                raise LinkError(
                    f"{E_SUBTYPE_FIELD_NAME_OVERLAP}: Entity '{entity.name}' is a "
                    f"subtype of '{base_name}' and declares a field '{f.name}' "
                    f"that shadows a base field. Subtype children must declare "
                    f"disjoint field names from the base; rename the child field "
                    f"or move it onto the base."
                )

        if getattr(entity, "soft_delete", False):
            raise LinkError(
                f"{E_SUBTYPE_SOFT_DELETE_ON_CHILD}: Entity '{entity.name}' is a "
                f"subtype of '{base_name}' and must not declare `soft_delete:`. "
                f"Declare soft_delete on the base entity instead."
            )

        if entity.name in scoped_entities and base_name not in scoped_entities:
            raise LinkError(
                f"{E_SUBTYPE_GRANT_INCOMPLETE}: Entity '{entity.name}' has a "
                f"grant_schema but its base '{base_name}' does not. "
                f"Declare a grant_schema with `scope: {base_name}` "
                f"alongside the one on '{entity.name}', or remove the child grant."
            )

        children_by_base.setdefault(base_name, []).append(entity.name)

    out: list[ir.EntitySpec] = []
    for entity in entities:
        children = children_by_base.get(entity.name)
        if children is None:
            out.append(entity)
            continue

        if any(f.name == "kind" for f in entity.fields):
            raise LinkError(
                f"{E_SUBTYPE_KIND_RESERVED}: Entity '{entity.name}' is a "
                f"polymorphic base (children: {sorted(children)}) and already "
                f"declares a `kind` field. `kind` is reserved as the subtype "
                f"discriminator."
            )

        children_sorted = sorted(children)
        kind_field = ir.FieldSpec(
            name="kind",
            type=ir.FieldType(
                kind=ir.FieldTypeKind.ENUM,
                enum_values=[_to_snake_case(c) for c in children_sorted],
            ),
            modifiers=[ir.FieldModifier.REQUIRED],
        )
        out.append(
            entity.model_copy(
                update={
                    "subtype_children": tuple(children_sorted),
                    "fields": [*entity.fields, kind_field],
                }
            )
        )
    return out


def _validate_subtype_panels(
    entities: list[ir.EntitySpec],
    surfaces: list[ir.SurfaceSpec],
) -> list[str]:
    """Linker rule 9 — `subtype_panel:` branches must reference real subtypes.

    Walks every surface's sections for a populated `subtype_panel`, and:
    - Raises ``LinkError(E_SUBTYPE_PANEL_UNKNOWN_KIND)`` when the surface's
      entity is not a polymorphic base, or a branch's ``when_kind`` does
      not match any child of the base.
    - Returns ``W_SUBTYPE_PANEL_INCOMPLETE`` warning strings for panels that
      omit one or more known subtypes — caller joins these into
      ``metadata['link_warnings']``.
    """
    from .archetype_expander import _to_snake_case
    from .errors import E_SUBTYPE_PANEL_UNKNOWN_KIND, W_SUBTYPE_PANEL_INCOMPLETE

    by_name = {e.name: e for e in entities}
    warnings: list[str] = []
    for surface in surfaces:
        # SurfaceSpec.entity_ref is the canonical attribute (surfaces.py:303).
        base = by_name.get(surface.entity_ref) if surface.entity_ref else None
        for section in surface.sections:
            if section.subtype_panel is None:
                continue
            if base is None or not base.is_polymorphic_base:
                raise LinkError(
                    f"{E_SUBTYPE_PANEL_UNKNOWN_KIND}: subtype_panel: on surface "
                    f"'{surface.name}' but its entity "
                    f"{'(none)' if base is None else f'{base.name!r}'} is not a "
                    f"polymorphic base. Add `subtype_of:` declarations to make "
                    f"it a base, or remove the subtype_panel block."
                )
            valid_kinds = {_to_snake_case(c) for c in base.subtype_children}
            seen: set[str] = set()
            for branch in section.subtype_panel.branches:
                if branch.when_kind not in valid_kinds:
                    raise LinkError(
                        f"{E_SUBTYPE_PANEL_UNKNOWN_KIND}: subtype_panel branch "
                        f"`when kind = {branch.when_kind}` in surface "
                        f"'{surface.name}' does not match any subtype of "
                        f"'{base.name}' (known: {sorted(valid_kinds)})."
                    )
                seen.add(branch.when_kind)
            missing = valid_kinds - seen
            if missing:
                warnings.append(
                    f"{W_SUBTYPE_PANEL_INCOMPLETE}: surface '{surface.name}' "
                    f"subtype_panel missing branches for: {sorted(missing)}."
                )
    return warnings


def _inject_soft_delete_fields(entities: list[ir.EntitySpec]) -> list[ir.EntitySpec]:
    """Append a `deleted_at: datetime optional` field to every entity
    with ``soft_delete=True`` that does not already declare one (#1218).

    The runtime soft-delete plumbing (read-path tombstone filter +
    DELETE-as-UPDATE) needs the column to exist. Authors who already
    declared ``deleted_at`` explicitly keep their field unchanged —
    we only fill the gap when ``soft_delete`` is set with no
    accompanying field.
    """
    out: list[ir.EntitySpec] = []
    for entity in entities:
        if not getattr(entity, "soft_delete", False):
            out.append(entity)
            continue
        if any(f.name == "deleted_at" for f in entity.fields):
            out.append(entity)
            continue
        new_field = FieldSpec(
            name="deleted_at",
            type=FieldType(kind=FieldTypeKind.DATETIME),
            modifiers=[FieldModifier.OPTIONAL],
        )
        out.append(entity.model_copy(update={"fields": [*entity.fields, new_field]}))
    return out


# Field set auto-injected on entities with `signable: true` (#1283 phase 3).
# Project-declared fields with the same name win — explicit always beats
# auto-inject. The 7-value status enum mirrors cyfuture's working state
# machine; the URL/IP/UA/timestamp columns are the audit + crypto footprint
# the signing runtime relies on.
_SIGNABLE_AUTO_FIELDS: tuple[tuple[str, FieldType, tuple[FieldModifier, ...]], ...] = (
    (
        "status",
        FieldType(
            kind=FieldTypeKind.ENUM,
            enum_values=[
                "draft",
                "sent",
                "viewed",
                "signed",
                "declined",
                "expired",
                "superseded",
            ],
        ),
        (FieldModifier.REQUIRED,),
    ),
    (
        "signing_service",
        FieldType(kind=FieldTypeKind.ENUM, enum_values=["native", "manual"]),
        (FieldModifier.REQUIRED,),
    ),
    (
        "signing_url",
        FieldType(kind=FieldTypeKind.STR, max_length=500),
        (FieldModifier.OPTIONAL,),
    ),
    ("signed_document", FieldType(kind=FieldTypeKind.FILE), (FieldModifier.OPTIONAL,)),
    (
        "signing_token_hash",
        FieldType(kind=FieldTypeKind.STR, max_length=64),
        (FieldModifier.OPTIONAL,),
    ),
    (
        "signer_ip",
        FieldType(kind=FieldTypeKind.STR, max_length=45),
        (FieldModifier.OPTIONAL,),
    ),
    (
        "signer_user_agent",
        FieldType(kind=FieldTypeKind.STR, max_length=500),
        (FieldModifier.OPTIONAL,),
    ),
    ("sent_at", FieldType(kind=FieldTypeKind.DATETIME), (FieldModifier.OPTIONAL,)),
    ("viewed_at", FieldType(kind=FieldTypeKind.DATETIME), (FieldModifier.OPTIONAL,)),
    ("signed_at", FieldType(kind=FieldTypeKind.DATETIME), (FieldModifier.OPTIONAL,)),
    ("expires_at", FieldType(kind=FieldTypeKind.DATETIME), (FieldModifier.OPTIONAL,)),
)

# Public, ordered tuple of the column names auto-injected on `signable: true`
# entities. Each is a plain single-column scalar/datetime/enum/file field, so the
# column name equals the field name — used by the schema-drift detector
# (`dazzle db verify`, #1340) to flag a signable table frozen at a stale shape
# before a create 500s on a missing signing column.
SIGNABLE_AUTO_FIELD_NAMES: tuple[str, ...] = tuple(name for name, _t, _m in _SIGNABLE_AUTO_FIELDS)


def _inject_signable_fields(entities: list[ir.EntitySpec]) -> list[ir.EntitySpec]:
    """Inject the 11 signing fields + default audit on `signable: true`
    entities (#1283 phase 3).

    For each entity with ``signable=True``:

    * Append every field in ``_SIGNABLE_AUTO_FIELDS`` whose name is not
      already declared. Project-declared fields with the same name keep
      their existing type/modifiers — explicit always wins (allows
      e.g. a wider ``status`` enum or a longer ``signing_url``).
    * If ``audit`` is unset, default to
      ``AuditConfig(enabled=True, operations=[])`` — signing is
      legally meaningful, so the audit trail is on by default.

    The state machine merge (auto-emit the 7-state transitions block
    when no project-declared transitions exist) is intentionally
    deferred to a later slice; phase 3 covers fields + audit defaults
    only. The runtime read path needs the columns regardless of whether
    the project supplied its own transitions block.
    """
    from .ir.domain import AuditConfig

    out: list[ir.EntitySpec] = []
    for entity in entities:
        if not getattr(entity, "signable", False):
            out.append(entity)
            continue

        existing = {f.name for f in entity.fields}
        new_fields = list(entity.fields)
        for name, ftype, mods in _SIGNABLE_AUTO_FIELDS:
            if name in existing:
                continue
            new_fields.append(FieldSpec(name=name, type=ftype, modifiers=list(mods)))

        updates: dict[str, object] = {"fields": new_fields}
        if entity.audit is None:
            updates["audit"] = AuditConfig(enabled=True, operations=[])

        out.append(entity.model_copy(update=updates))
    return out


def _validate_render_references(
    surfaces: list[ir.SurfaceSpec],
    workspaces: list[ir.WorkspaceSpec],
    known: set[str],
) -> None:
    """Validate that every render: clause names a registered renderer.

    Raises RenderValidationError on the first unknown name, listing the
    registered renderers so the author sees the available alternatives.
    """
    for s in surfaces:
        if s.render is not None and s.render not in known:
            raise RenderValidationError(
                _unknown_renderer_message(s.render, known, f"surface {s.name!r}")
            )
    for ws in workspaces:
        for r in ws.regions:
            if r.render is not None and r.render not in known:
                raise RenderValidationError(
                    _unknown_renderer_message(
                        r.render, known, f"workspace {ws.name!r} region {r.name!r}"
                    )
                )


def _unknown_renderer_message(name: str, known: set[str], location: str) -> str:
    """Format the agent-actionable error for an unknown renderer name (#1117).

    Pre-#1117 this was a one-line "unknown renderer X; registered: [...]"
    that said what was wrong but not how to fix it. Project authors saw
    the wall but not the door. The new shape names both halves of the
    extension contract — manifest allowlist + runtime registration — so
    an LLM agent reading the error knows exactly which two places need
    edits.
    """
    return (
        f"{location} declares render: {name!r}, but that name isn't in the "
        f"known-renderers set (currently: {sorted(known)}).\n\n"
        "To register a project-side renderer, two steps are required:\n"
        f"  1. Declare the name in dazzle.toml so the link-time validator accepts it:\n"
        "       [renderers]\n"
        f"       extra = [{name!r}]\n"
        "  2. Register the runtime handler in app code (typically in your\n"
        "     app factory or a startup hook):\n"
        "       services.renderer_registry.register(\n"
        f"           name={name!r}, handler=MyRendererClass()\n"
        "       )\n\n"
        "See fixtures/custom_renderer/ for a worked end-to-end example."
    )


def _derive_atomic_step_orders(
    atomic_flows: list[ir.AtomicFlowSpec],
    fk_graph: FKGraph,
) -> list[ir.AtomicFlowSpec]:
    """Set ``derived_step_order`` on create-DAG atomic flows (#1315, ADR-0029 §1).

    A flow qualifies only when every step is a ``create`` (no ``update`` — those
    carry temporal/semantic order the FK graph can't express) and its create
    entities topologically sort by FK (no cycle). For a qualifying flow the
    framework derives parent-before-child order so the author need not hand-order
    the steps. Declared ``steps`` order is left untouched; the permutation lives
    in ``derived_step_order``. A flow already in a valid declared order (the
    common case) keeps ``derived_step_order = None`` — no reorder needed, so
    existing flows are byte-unchanged and the executor runs declared order.
    """
    result: list[ir.AtomicFlowSpec] = []
    for flow in atomic_flows:
        steps = flow.steps
        # Only the all-create family is FK-orderable; any update → declared order.
        if not steps or any(isinstance(s, ir.FlowUpdate) for s in steps):
            result.append(flow)
            continue
        if not _above_refs_are_all_fk_edges(steps, fk_graph):
            # Some `above.E.id` is assigned to a non-FK field, so FK-topo order
            # would not guarantee E is created before the referencing step.
            # Don't reorder — keep the author's declared (resolvable) order.
            result.append(flow)
            continue
        entities = [s.entity for s in steps]
        order = fk_graph.creation_order(entities)
        if order is None:
            # FK cycle / duplicate / self-ref → fall back to declared order.
            result.append(flow)
            continue
        index_of = {e: i for i, e in enumerate(entities)}
        derived = [index_of[e] for e in order]
        if derived == list(range(len(steps))):
            # Declared order already parent-before-child — nothing to carry.
            result.append(flow)
            continue
        result.append(flow.model_copy(update={"derived_step_order": derived}))
    return result


def _derive_flow_invariant_anchors(
    atomic_flows: list[ir.AtomicFlowSpec],
    fk_graph: FKGraph,
) -> list[ir.AtomicFlowSpec]:
    """Derive each flow invariant's lockable anchor at link time (#1318, ADR-0031).

    An invariant ``<agg>(<entity>.<field> where <filter>) <op> <rhs>`` is enforced
    against the rows the flow touches. To lock it to the right scope, the linker
    finds the **anchor**: a ``where`` term ``<column> = input.<name>`` where
    ``<column>`` (or ``<column>_id``) is an **FK on the invariant's ``entity``**.
    The FK's target entity becomes ``anchor_entity`` and ``name`` becomes
    ``anchor_input``. The first such FK-equality-to-input term (declared order)
    wins — a flow locks one anchor in v1. If no term resolves to an FK on the
    entity, the anchor stays ``None`` and the validator (Task 5) rejects the
    invariant as unanchored. The filter itself is enforced from ``raw_filter``
    directly at runtime (no compiled predicate in v1).
    """
    result: list[ir.AtomicFlowSpec] = []
    for flow in atomic_flows:
        if not flow.invariants:
            result.append(flow)
            continue
        new_invariants: list[ir.FlowInvariant] = []
        for inv in flow.invariants:
            anchor_entity: str | None = None
            anchor_input: str | None = None
            for column, kind, value in inv.raw_filter:
                if kind != "input":
                    continue
                try:
                    _fk_field, target = fk_graph.resolve_segment(inv.entity, column)
                except ValueError:
                    continue  # `column` is not an FK on the invariant's entity
                anchor_entity = target
                anchor_input = value
                break  # first FK-equality-to-input term wins (v1: one anchor)
            new_invariants.append(
                inv.model_copy(
                    update={"anchor_entity": anchor_entity, "anchor_input": anchor_input}
                )
            )
        result.append(flow.model_copy(update={"invariants": new_invariants}))
    return result


def _above_refs_are_all_fk_edges(
    steps: list[ir.AtomicFlowStep],
    fk_graph: FKGraph,
) -> bool:
    """True iff every ``above.E.id`` in *steps* is assigned to an FK field → E.

    FK-topological reorder only guarantees an ``above``-ref resolves when the
    referencing assignment is the FK that points at E (so the topo sort, which
    orders FK targets before sources, places E first). If an ``above``-ref is
    assigned to a non-FK field, FK topology says nothing about their relative
    order, so we must NOT reorder (the caller keeps declared order).
    """
    for step in steps:
        # Only FlowCreate reaches here (caller filtered updates); narrow for mypy.
        if not isinstance(step, ir.FlowCreate):
            return False
        for field, value in step.assignments.items():
            if value.kind != ir.FlowFieldValueKind.ABOVE_REF:
                continue
            try:
                _fk_field, target = fk_graph.resolve_segment(step.entity, field)
            except ValueError:
                return False  # `field` is not an FK on this entity
            if target != value.above_entity:
                return False  # FK points somewhere other than the referenced entity
    return True


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

    Also (#1124, #1311) walks every ``scope: create:`` predicate to
    enforce the bounded FK-path depth cap. As of #1311 (ADR-0028) the
    runtime evaluator resolves FK-path (depth > 1) and ExistsCheck /
    NotExistsCheck create-scope predicates via a payload-time SQL probe,
    so those shapes are accepted; only a pathologically deep FK path
    (> :data:`_MAX_SCOPE_CREATE_FK_DEPTH` hops) is rejected at link time,
    surfacing during ``dazzle validate`` rather than at request time.

    Args:
        entities:             List of entity specifications.
        fk_graph:             FKGraph built from the entities.
        build_scope_predicate: Callable (condition, entity_name, fk_graph) → ScopePredicate.

    Returns:
        Updated list of entity specifications with predicates attached.
    """
    from dazzle.core.ir.domain import PermissionKind

    # ADR-0036 Layer 2: the current_tenant hierarchy expansion (aggregate-vs-single)
    # applies to READ/LIST scopes only — writes (CREATE/UPDATE/DELETE) keep the
    # single leaf check, so an aggregate (ancestor) host is read-only (the single
    # check matches no rows there). Passing entities_by_name opts a scope into the
    # expansion; omitting it preserves the Layer-1 single check.
    _read_ops = {PermissionKind.READ, PermissionKind.LIST}
    _entities_by_name = {e.name: e for e in entities}

    result: list[ir.EntitySpec] = []
    for entity in entities:
        if entity.access is None or not entity.access.scopes:
            result.append(entity)
            continue

        compiled_scopes: list[ir.ScopeRule] = []
        for rule in entity.access.scopes:
            _eb = _entities_by_name if rule.operation in _read_ops else None
            predicate = build_scope_predicate(  # type: ignore[operator]
                rule.condition, entity.name, fk_graph, entities_by_name=_eb
            )
            # #1311 (ADR-0028): FK-path / EXISTS create-scope predicates are
            # resolved at runtime via a payload-time SQL probe; only enforce
            # the bounded FK-path depth cap at link time so a pathologically
            # deep path surfaces during `dazzle validate`.
            if predicate is not None and rule.operation == PermissionKind.CREATE:
                _assert_scope_create_predicate_depth_bounded(predicate, entity.name, rule)
            compiled_scopes.append(rule.model_copy(update={"predicate": predicate}))

        new_access = entity.access.model_copy(update={"scopes": compiled_scopes})
        result.append(entity.model_copy(update={"access": new_access}))

    return result


# Maximum FK-path depth (hops) a `scope: create:` predicate may declare.
# ``teaching_group.department`` is 1 hop; the cap bounds the payload-time
# probe's nested-subquery depth against a pathological author-declared path.
# Generous relative to real scope rules (the deepest in-repo is 2 hops).
_MAX_SCOPE_CREATE_FK_DEPTH = 4


def _assert_scope_create_predicate_depth_bounded(
    predicate: object,
    entity_name: str,
    rule: ir.ScopeRule,
) -> None:
    """Walk a scope:create: predicate and enforce the FK-path depth cap.

    As of #1311 (ADR-0028) the runtime evaluator
    (``dazzle.http.runtime.scope_create_eval``) resolves FK-path
    (depth > 1) and junction-table (ExistsCheck / NotExistsCheck)
    create-scope predicates via a payload-time SQL probe, so those
    shapes are accepted. The only remaining link-time rejection is a
    pathologically deep FK path (more than
    :data:`_MAX_SCOPE_CREATE_FK_DEPTH` hops), which would emit an
    unboundedly nested subquery.

    Raised as RenderValidationError so it propagates through the same
    error path as the other link-time DSL validation issues — users
    see it at ``dazzle validate`` time, not at request time.
    """
    from dazzle.core.ir.predicates import (
        BoolComposite,
        PathCheck,
    )

    personas = ", ".join(getattr(rule, "personas", []) or []) or "(no personas)"
    location = f"entity {entity_name!r} scope: create: as: {personas}"

    if isinstance(predicate, PathCheck):
        hops = len(predicate.path) - 1
        if hops > _MAX_SCOPE_CREATE_FK_DEPTH:
            raise RenderValidationError(
                f"{location}: `scope: create:` FK-path predicate is too deep "
                f"({hops} hops, max {_MAX_SCOPE_CREATE_FK_DEPTH}; "
                f"path={predicate.path!r}). The payload-time probe resolves "
                f"the FK chain as a nested subquery; cap the path or express "
                f"the constraint differently. See docs/reference/rbac-scope.md "
                f"and ADR-0028."
            )
    if isinstance(predicate, BoolComposite):
        for child in predicate.children:
            _assert_scope_create_predicate_depth_bounded(child, entity_name, rule)


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


def _derive_aijob_subject_targets(fragment: object) -> list[str]:
    """#1454: AIJob subject targets = the declared-cognition surface.

    Returns sorted list of entity names that are legal subjects for an AIJob:
    - every ``trigger.on_entity`` declared on any llm_intent
    - "ProcessRun" when any process has at least one llm_intent step
    """
    targets: set[str] = set()
    for intent in getattr(fragment, "llm_intents", []) or []:
        for trig in getattr(intent, "triggers", []) or []:
            if getattr(trig, "on_entity", None):
                targets.add(trig.on_entity)
    has_llm_step = any(
        getattr(s, "kind", None) == ir.ProcessStepKind.LLM_INTENT
        for p in getattr(fragment, "processes", []) or []
        for s in p.steps
    )
    if has_llm_step:
        targets.add("ProcessRun")
    return sorted(targets)


def _build_ai_job_entity(subject_targets: list[str]) -> ir.EntitySpec:
    """Build the auto-generated AIJob system entity for AI cost tracking.

    ``subject`` is a required poly_ref over the declared-cognition surface
    (trigger entities + ProcessRun when any process runs an llm_intent step).
    See #1454 / ADR-0042.
    """
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in AI_JOB_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    # #1454: required poly_ref subject — the governance unit.
    fields.append(
        FieldSpec(
            name="subject",
            type=FieldType(kind=FieldTypeKind.POLY_REF, poly_targets=subject_targets),
            modifiers=[FieldModifier.REQUIRED],
        )
    )

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


def _build_process_run_entity() -> ir.EntitySpec:
    """Build the auto-generated ProcessRun system entity (#1454).

    Persists each process execution as a uuid-pk, user-anchored audit row so a
    process ``llm_intent`` step's AIJob can name it as the subject.
    """
    from dazzle.core.ir.process import PROCESS_RUN_FIELDS

    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in PROCESS_RUN_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(operation=op, require_auth=True, effect=ir.PolicyEffect.PERMIT)
            for op in ir.PermissionKind
        ]
    )
    return ir.EntitySpec(
        name="ProcessRun",
        title="Process Run",
        intent="Audit record of a process execution; subject for process-step AI calls",
        domain="platform",
        patterns=["system", "audit"],
        fields=fields,
        access=access,
    )


def _build_job_run_entity() -> ir.EntitySpec:
    """Build the auto-generated JobRun system entity (#953 cycle 2).

    A single shared platform entity captures every worker invocation
    across all declared jobs. The `job_name` discriminator + `status`
    + timing columns make it the read source for cycle-4's scheduler
    (skip currently-running jobs) and cycle-6's retention sweep.

    Mirrors the AIJob / AuditEntry shape — same access pattern (auth-
    required CRUD via the standard route generator).
    """
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in JOB_RUN_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    # Default access: any authenticated user can READ/LIST job runs —
    # they're internal observability data; admins typically need them
    # for triage. CREATE is permitted because cycle 3's worker writes
    # through the standard service layer rather than a privileged
    # path. UPDATE is permitted so the worker can transition status
    # (pending → running → completed/failed). DELETE is intentionally
    # absent — historical job-run rows are evidence; cycle-6 retention
    # uses a different bulk-delete code path.
    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(
                operation=ir.PermissionKind.CREATE,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
            ir.PermissionRule(
                operation=ir.PermissionKind.READ,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
            ir.PermissionRule(
                operation=ir.PermissionKind.LIST,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
            ir.PermissionRule(
                operation=ir.PermissionKind.UPDATE,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
        ]
    )

    return ir.EntitySpec(
        name="JobRun",
        title="Job Run",
        intent="One worker invocation of a declared background job",
        domain="platform",
        patterns=["system", "audit"],
        fields=fields,
        access=access,
    )


def _build_audit_entry_entity() -> ir.EntitySpec:
    """Build the auto-generated AuditEntry system entity (#956 cycle 2).

    A single shared system entity captures every tracked field change
    across all audited entity types. The `entity_type` and `entity_id`
    columns discriminate; cycle-4's history region filters on those
    when rendering the per-row history.
    """
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in AUDIT_ENTRY_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    # Default access: any authenticated user can READ/LIST audit
    # entries — cycle 5 will tighten this via `show_to`. CREATE is
    # permitted because cycle 3's repository hook writes through the
    # standard service layer rather than a privileged path. UPDATE and
    # DELETE are intentionally absent — audit entries are immutable
    # records of history; deletion is handled by the cycle-6 retention
    # sweep, which uses a different code path.
    access = ir.AccessSpec(
        permissions=[
            ir.PermissionRule(
                operation=ir.PermissionKind.CREATE,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
            ir.PermissionRule(
                operation=ir.PermissionKind.READ,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
            ir.PermissionRule(
                operation=ir.PermissionKind.LIST,
                require_auth=True,
                effect=ir.PolicyEffect.PERMIT,
            ),
        ]
    )

    return ir.EntitySpec(
        name="AuditEntry",
        title="Audit Entry",
        intent="Captures one before/after value pair for an audited field change",
        domain="platform",
        patterns=["system", "audit"],
        fields=fields,
        access=access,
    )


def _build_audit_entry_admin_surface() -> ir.SurfaceSpec:
    """Build a LIST admin surface for AuditEntry (#991).

    Pairs with the auto-injected entity so the route generator
    emits `/auditentries` (LIST), `/auditentries/{id}` (READ),
    and `/app/auditentry` (UI list) endpoints. Without this
    surface the entity exists but has no HTTP-visible CRUD
    routes — the audit-history region works in-process but
    external inspection tools can't query.

    Mirrors the FeedbackReport admin-surface pattern.
    """
    elements = [
        ir.SurfaceElement(field_name=name, label=label)
        for name, label in [
            ("at", "When"),
            ("entity_type", "Entity"),
            ("entity_id", "ID"),
            ("field_name", "Field"),
            ("operation", "Op"),
            ("by_user_id", "By"),
        ]
    ]
    ux = ir.UXSpec(
        sort=[ir.SortSpec(field="at", direction="desc")],
        filter=["entity_type", "operation", "by_user_id"],
        search=["entity_id", "field_name"],
        empty_message="No audit entries yet.",
    )
    return ir.SurfaceSpec(
        name="auditentry_admin",
        title="Audit Entries",
        entity_ref="AuditEntry",
        mode=ir.SurfaceMode.LIST,
        sections=[ir.SurfaceSection(name="main", title="Audit", elements=elements)],
        access=ir.SurfaceAccessSpec(require_auth=True),
        ux=ux,
    )


def _build_job_run_admin_surface() -> ir.SurfaceSpec:
    """Build a LIST admin surface for JobRun (#991).

    Same rationale as `_build_audit_entry_admin_surface`: pairs
    with the cycle-2 entity so the route generator emits CRUD
    endpoints the worker (and operator triage tools) can hit.
    """
    elements = [
        ir.SurfaceElement(field_name=name, label=label)
        for name, label in [
            ("created_at", "Created"),
            ("job_name", "Job"),
            ("status", "Status"),
            ("attempt_number", "Attempt"),
            ("started_at", "Started"),
            ("finished_at", "Finished"),
            ("duration_ms", "Duration (ms)"),
        ]
    ]
    ux = ir.UXSpec(
        sort=[ir.SortSpec(field="created_at", direction="desc")],
        filter=["job_name", "status"],
        search=["job_name", "error_message"],
        empty_message="No job runs yet.",
    )
    return ir.SurfaceSpec(
        name="jobrun_admin",
        title="Job Runs",
        entity_ref="JobRun",
        mode=ir.SurfaceMode.LIST,
        sections=[ir.SurfaceSection(name="main", title="Jobs", elements=elements)],
        access=ir.SurfaceAccessSpec(require_auth=True),
        ux=ux,
    )


def _build_onboarding_state_entity() -> ir.EntitySpec:
    """Build the auto-generated ``OnboardingState`` entity (v0.71.1).

    Auto-injected when the project declares any ``guide`` block. Stores
    one row per ``(user_id, guide_name, guide_version)`` — the
    repository layer (``dazzle.http.runtime.onboarding``) owns the
    UPSERT logic that enforces the composite uniqueness.

    Access policy: a user reads / writes only their own rows; admins
    see everything (mirrors the FeedbackReport scope split). The entity
    is excluded by default from ``dazzle spec status`` since it's
    framework-injected — same treatment as AIJob, FeedbackReport, etc.
    """
    fields: list[FieldSpec] = []
    for name, type_str, modifiers, default in ONBOARDING_STATE_FIELDS:
        field_type = _parse_field_type(type_str)
        mods = [_MODIFIER_MAP[m] for m in modifiers]
        fields.append(FieldSpec(name=name, type=field_type, modifiers=mods, default=default))

    _ops = (
        ir.PermissionKind.CREATE,
        ir.PermissionKind.READ,
        ir.PermissionKind.LIST,
        ir.PermissionKind.UPDATE,
        ir.PermissionKind.DELETE,
    )
    # Self-only scope: user_id = current_user.id (string column).
    _self_cond = ir.ConditionExpr(
        comparison=ir.Comparison(
            field="user_id",
            operator=ir.ComparisonOperator.EQUALS,
            value=ir.ConditionValue(literal="current_user.id"),
        )
    )
    _scope_rules: list[ir.ScopeRule] = []
    for op in _ops:
        _scope_rules.append(ir.ScopeRule(operation=op, condition=_self_cond, personas=["*"]))
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

    return ir.EntitySpec(
        name="OnboardingState",
        title="Onboarding State",
        intent="Per-user progression state for guided onboarding flows",
        domain="platform",
        patterns=["lifecycle", "audit"],
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
        # rows; admins keep full visibility via the ``all as: admin`` scope.
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
        # keep full UPDATE access via the ``all as: admin`` scope. The
        # edit-UI page itself is still at /app/feedbackreports/{id}/edit
        # and rendering is filtered by the same scope — non-admins see
        # only their own rows there too.
        access=ir.SurfaceAccessSpec(require_auth=True),
    )
