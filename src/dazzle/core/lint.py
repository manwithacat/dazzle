from . import ir
from .validator import (
    extended_lint,
    validate_approvals,
    validate_entities,
    validate_event_payload_secrets,
    validate_experiences,
    validate_foreign_models,
    validate_integrations,
    validate_ledgers,
    validate_money_fields,
    validate_notifications,
    validate_services,
    validate_slas,
    validate_surfaces,
    validate_ux_specs,
    validate_webhooks,
)


def lint_appspec(appspec: ir.AppSpec, extended: bool = False) -> tuple[list[str], list[str]]:
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

    Returns:
        Tuple of (errors, warnings)
        - errors: List of error messages that must be fixed
        - warnings: List of warnings that should be addressed
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

    errors, warnings = validate_slas(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Extended lint rules
    if extended:
        extended_warnings = extended_lint(appspec)
        all_warnings.extend(extended_warnings)

    # v0.14.1: Include link warnings (e.g., unused imports)
    link_warnings = appspec.metadata.get("link_warnings", [])
    all_warnings.extend(link_warnings)

    return all_errors, all_warnings
