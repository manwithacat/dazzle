from . import ir
from .discovery import Relevance, suggest_capabilities
from .validator import (
    extended_lint,
    validate_admin_personas_scope_conflict,
    validate_approvals,
    validate_atomic_flows,
    validate_audit_config,
    validate_entities,
    validate_event_payload_secrets,
    validate_experiences,
    validate_fitness_repr_fields,
    validate_foreign_models,
    validate_governance_policies,
    validate_graph_declarations,
    validate_integrations,
    validate_ledgers,
    validate_lifecycles,
    validate_money_fields,
    validate_nav_curation,
    validate_notifications,
    validate_persona_nav_refs,
    validate_process_step_service_refs,
    validate_rbac_matrix_diagnostics,
    validate_role_references_against_enum,
    validate_scope_predicates,
    validate_sensitive_fields,
    validate_services,
    validate_slas,
    validate_surfaces,
    validate_tenancy_partition_key,
    validate_transition_invocations,
    validate_ux_specs,
    validate_visibility_bool_field_scope_coverage,
    validate_webhooks,
    validate_workspace_primary_actions,
    validate_workspace_region_actions,
)


def lint_appspec(
    appspec: ir.AppSpec,
    extended: bool = False,
    *,
    suggest: bool = True,
    active_capabilities: set[str] | None = None,
) -> tuple[list[str], list[str], list[Relevance]]:
    """
    Validate AppSpec for semantic errors and warnings.

    Performs comprehensive validation:
    - Entity validation (pk, field types, constraints)
    - Surface validation (entity refs, field refs, action outcomes)
    - Experience validation (reachability, transitions)
    - Service validation (spec URLs, auth profiles)
    - Foreign model validation (service refs, fields)
    - Integration validation (all refs, mappings, schedules)

    Extended mode adds:
    - Naming convention checks (snake_case, PascalCase)
    - Unused entity/surface detection
    - Missing titles/descriptions

    Args:
        appspec: Complete application specification
        extended: If True, perform extended lint checks (naming, unused code)
        suggest: If True (default), compute capability suggestions via
            ``suggest_capabilities`` — which parses every bundled example
            app's DSL to build a comparison index. Callers that only need
            errors/warnings (e.g. the ``dazzle serve`` boot validation)
            should pass ``suggest=False`` to skip that cost; ``relevance``
            is then an empty list.

    Returns:
        Tuple of (errors, warnings, relevance)
        - errors: List of error messages that must be fixed
        - warnings: List of warnings that should be addressed
        - relevance: List of contextual capability suggestions
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # Basic check
    if not appspec.domain.entities and not appspec.surfaces:
        all_warnings.append("No entities or surfaces defined in app.")

    # Run all validation rules
    errors, warnings = validate_entities(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_surfaces(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # #1420 Slice 2: a surface whose op the entity's `expose:` omits is a contradiction.
    from dazzle.core.validation.entities import validate_expose_surface_consistency

    errors, warnings = validate_expose_surface_consistency(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_experiences(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_services(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_foreign_models(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_integrations(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # UX Semantic Layer validation
    errors, warnings = validate_ux_specs(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Cross-entity region action FK validation (#861)
    errors, warnings = validate_workspace_region_actions(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Money field validation (FACT/INTENT streams must use Money type)
    errors, warnings = validate_money_fields(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Event payload secrets validation
    errors, warnings = validate_event_payload_secrets(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # TigerBeetle ledger validation (v0.24.0)
    errors, warnings = validate_ledgers(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Notification validation (v0.34.0)
    errors, warnings = validate_notifications(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Preview construct validation (v0.25.0 — parsed but not yet runtime-enforced)
    errors, warnings = validate_webhooks(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_approvals(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # #1228 Phase 3c — atomic multi-entity flows
    errors, warnings = validate_atomic_flows(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # #1319 / ADR-0032 — transition `invoke <flow>(...)` cross-references
    errors, warnings = validate_transition_invocations(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_slas(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_audit_config(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_governance_policies(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    errors, warnings = validate_sensitive_fields(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Scope predicate validation (FK path integrity)
    errors, warnings = validate_scope_predicates(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Visibility-bool fields without scope coverage (#1062)
    errors, warnings = validate_visibility_bool_field_scope_coverage(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Validator hardening — closes #1061
    for check in (
        validate_role_references_against_enum,
        validate_tenancy_partition_key,
        validate_admin_personas_scope_conflict,
        validate_process_step_service_refs,
        validate_rbac_matrix_diagnostics,
    ):
        errors, warnings = check(appspec)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Graph semantics validation (v0.46.0 — #619)
    errors, warnings = validate_graph_declarations(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Lifecycle block validation (ADR-0020)
    errors, warnings = validate_lifecycles(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Fitness repr_fields declaration (Agent-Led Fitness v1)
    errors, warnings = validate_fitness_repr_fields(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Persona nav_ref resolution (#1324 — `uses nav <name>` must reference
    # a declared top-level `nav <name>:` block)
    errors, warnings = validate_persona_nav_refs(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Workspace primary_actions target resolution (#1324 FR-5 — authored
    # heading-CTA actions must reference a declared surface or workspace)
    errors, warnings = validate_workspace_primary_actions(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Navigation curation lint (#1324 FR-6 — auto-discovery reliance, dead
    # curated nav items, ignored author-declared workspace nav_groups). All
    # WARNINGS.
    errors, warnings = validate_nav_curation(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Extended lint rules
    if extended:
        extended_warnings = extended_lint(appspec)
        all_warnings.extend(extended_warnings)

    # v0.14.1: Include link warnings (e.g., unused imports)
    link_warnings = appspec.metadata.get("link_warnings", [])
    all_warnings.extend(link_warnings)

    # Capability discovery — suggest relevant capabilities based on AppSpec
    # content. Skipped when `suggest=False`: the suggestion pass parses
    # every bundled example app's DSL, which is pure overhead for callers
    # (like `dazzle serve`) that only consume `errors`.
    relevance = suggest_capabilities(appspec, active=active_capabilities) if suggest else []

    return all_errors, all_warnings, relevance
