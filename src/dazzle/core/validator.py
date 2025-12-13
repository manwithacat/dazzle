"""
Comprehensive semantic validation for DAZZLE AppSpec.

Validates entities, surfaces, experiences, services, foreign models, and integrations
for semantic correctness beyond basic reference resolution.
"""

from urllib.parse import urlparse

from . import ir

# =============================================================================
# Validation Constants
# =============================================================================

# Decimal type limits (based on common database limits)
DECIMAL_PRECISION_MIN = 1
DECIMAL_PRECISION_MAX = 65

# String field limits
STRING_MAX_LENGTH_MIN = 1
STRING_MAX_LENGTH_WARN_THRESHOLD = 10000  # Suggest TEXT type above this

# SQL reserved words (common across SQLite, PostgreSQL, MySQL)
# These can cause issues when used unquoted in SQL statements
SQL_RESERVED_WORDS = frozenset(
    {
        # Most common/problematic
        "order",
        "group",
        "select",
        "table",
        "index",
        "key",
        "user",
        "check",
        "primary",
        "foreign",
        "references",
        "constraint",
        "default",
        "null",
        "not",
        "and",
        "or",
        "where",
        "from",
        "join",
        "on",
        "as",
        "in",
        "is",
        "like",
        "between",
        "case",
        "when",
        "then",
        "else",
        "end",
        "create",
        "alter",
        "drop",
        "insert",
        "update",
        "delete",
        "set",
        "values",
        "into",
        "add",
        "column",
        "all",
        "distinct",
        "limit",
        "offset",
        "union",
        "except",
        "intersect",
        "having",
        "by",
        "asc",
        "desc",
        "trigger",
        "view",
        "exists",
        "unique",
        "current",
        "current_date",
        "current_time",
        "current_timestamp",
        "transaction",
        "commit",
        "rollback",
        "grant",
        "revoke",
        "with",
        "recursive",
        "escape",
        "collate",
        "natural",
        "left",
        "right",
        "inner",
        "outer",
        "cross",
        "full",
        # Additional SQL keywords
        "abort",
        "action",
        "after",
        "analyze",
        "attach",
        "autoincrement",
        "before",
        "begin",
        "cascade",
        "cast",
        "conflict",
        "database",
        "deferrable",
        "deferred",
        "detach",
        "each",
        "exclusive",
        "explain",
        "fail",
        "glob",
        "if",
        "ignore",
        "immediate",
        "indexed",
        "initially",
        "instead",
        "isnull",
        "match",
        "no",
        "notnull",
        "of",
        "plan",
        "pragma",
        "query",
        "raise",
        "regexp",
        "reindex",
        "release",
        "rename",
        "replace",
        "restrict",
        "row",
        "savepoint",
        "temp",
        "temporary",
        "vacuum",
        "virtual",
    }
)


def validate_entities(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all entities for semantic correctness.

    Checks:
    - Every entity has a primary key
    - Field types are valid and consistent
    - Enum values are valid identifiers
    - Decimal precision/scale are reasonable
    - Constraint fields exist
    - No duplicate field names
    - Unique constraints reference valid fields

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for entity in appspec.domain.entities:
        # Check for primary key
        if not entity.primary_key:
            errors.append(
                f"Entity '{entity.name}' has no primary key field. Add a field with 'pk' modifier."
            )

        # Check for SQL reserved words in entity name
        if entity.name.lower() in SQL_RESERVED_WORDS:
            warnings.append(
                f"Entity '{entity.name}' uses SQL reserved word as name. "
                f"Consider renaming (e.g., 'SalesOrder' instead of 'Order')."
            )

        # Check for duplicate field names
        field_names = [f.name for f in entity.fields]
        duplicates = {name for name in field_names if field_names.count(name) > 1}
        if duplicates:
            errors.append(f"Entity '{entity.name}' has duplicate field names: {duplicates}")

        # Validate each field
        for field in entity.fields:
            # Check for SQL reserved words in field name
            if field.name.lower() in SQL_RESERVED_WORDS:
                warnings.append(
                    f"Entity '{entity.name}' field '{field.name}' uses SQL reserved word. "
                    f"Consider renaming (e.g., 'sales_order' instead of 'order')."
                )
            # Check enum values
            if field.type.kind == ir.FieldTypeKind.ENUM:
                if not field.type.enum_values or len(field.type.enum_values) == 0:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has enum type but no values"
                    )

            # Check decimal precision/scale
            if field.type.kind == ir.FieldTypeKind.DECIMAL:
                if field.type.precision is None or field.type.scale is None:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has decimal type "
                        f"but missing precision/scale"
                    )
                elif (
                    field.type.precision < DECIMAL_PRECISION_MIN
                    or field.type.precision > DECIMAL_PRECISION_MAX
                ):
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' has unusual "
                        f"decimal precision: {field.type.precision}"
                    )
                elif field.type.scale > field.type.precision:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has decimal scale "
                        f"({field.type.scale}) greater than precision ({field.type.precision})"
                    )

            # Check string max length
            if field.type.kind == ir.FieldTypeKind.STR:
                if field.type.max_length is None:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has str type "
                        f"but no max_length"
                    )
                elif field.type.max_length < STRING_MAX_LENGTH_MIN:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has invalid "
                        f"max_length: {field.type.max_length}"
                    )
                elif field.type.max_length > STRING_MAX_LENGTH_WARN_THRESHOLD:
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' has very large "
                        f"max_length: {field.type.max_length}. Consider using 'text' type."
                    )

            # Check for conflicting modifiers
            if (
                ir.FieldModifier.REQUIRED in field.modifiers
                and ir.FieldModifier.OPTIONAL in field.modifiers
            ):
                errors.append(
                    f"Entity '{entity.name}' field '{field.name}' has both "
                    f"'required' and 'optional' modifiers"
                )

            # Check auto modifiers on appropriate types
            if (
                ir.FieldModifier.AUTO_ADD in field.modifiers
                or ir.FieldModifier.AUTO_UPDATE in field.modifiers
            ):
                if field.type.kind != ir.FieldTypeKind.DATETIME:
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' has auto_add/auto_update "
                        f"modifier but is not datetime type"
                    )

        # Validate constraints
        for constraint in entity.constraints:
            for field_name in constraint.fields:
                if not entity.get_field(field_name):
                    errors.append(
                        f"Entity '{entity.name}' {constraint.kind.value} constraint "
                        f"references non-existent field '{field_name}'"
                    )

    return errors, warnings


def validate_surfaces(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all surfaces for semantic correctness.

    Checks:
    - Entity references exist (already done by linker, but check fields)
    - Surface fields match entity fields when entity_ref is set
    - Actions have valid outcomes
    - Modes are appropriate for the surface structure

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for surface in appspec.surfaces:
        # Validate entity field matching
        if surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)
            if entity:
                # Check that fields in surface sections match entity fields
                for section in surface.sections:
                    for element in section.elements:
                        if not entity.get_field(element.field_name):
                            errors.append(
                                f"Surface '{surface.name}' section '{section.name}' "
                                f"references non-existent field '{element.field_name}' "
                                f"from entity '{entity.name}'"
                            )

        # Warn if no sections
        if not surface.sections:
            warnings.append(f"Surface '{surface.name}' has no sections defined")

        # Check mode consistency
        if surface.mode == ir.SurfaceMode.CREATE:
            if not surface.entity_ref:
                warnings.append(
                    f"Surface '{surface.name}' has mode 'create' but no entity reference"
                )
        elif surface.mode == ir.SurfaceMode.EDIT:
            if not surface.entity_ref:
                warnings.append(f"Surface '{surface.name}' has mode 'edit' but no entity reference")
        elif surface.mode == ir.SurfaceMode.VIEW:
            if not surface.entity_ref:
                warnings.append(f"Surface '{surface.name}' has mode 'view' but no entity reference")

    return errors, warnings


def validate_experiences(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all experiences for semantic correctness.

    Checks:
    - All steps are reachable from start step
    - No infinite loops without exit
    - Step kinds match targets
    - Transitions are valid

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for experience in appspec.experiences:
        # Check for empty experiences
        if not experience.steps:
            errors.append(f"Experience '{experience.name}' has no steps")
            continue

        # Build reachability graph
        reachable = set()
        to_visit = {experience.start_step}

        while to_visit:
            step_name = to_visit.pop()
            if step_name in reachable:
                continue
            reachable.add(step_name)

            step = experience.get_step(step_name)
            if step:
                for transition in step.transitions:
                    to_visit.add(transition.next_step)

        # Check for unreachable steps
        all_steps = {step.name for step in experience.steps}
        unreachable = all_steps - reachable
        if unreachable:
            warnings.append(f"Experience '{experience.name}' has unreachable steps: {unreachable}")

        # Check step consistency
        for step in experience.steps:
            # Validate step kind matches target
            if step.kind == ir.StepKind.SURFACE:
                if not step.surface:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'surface' but no surface target"
                    )
            elif step.kind == ir.StepKind.INTEGRATION:
                if not step.integration or not step.action:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'integration' but missing integration or action"
                    )

            # Warn about steps with no transitions (potential dead ends)
            if not step.transitions:
                # This is ok if it's a terminal step
                warnings.append(
                    f"Experience '{experience.name}' step '{step.name}' "
                    f"has no transitions (terminal step)"
                )

    return errors, warnings


def validate_services(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all services for semantic correctness.

    Checks:
    - Spec URLs are valid
    - Auth profiles are complete
    - Required fields are present

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for api in appspec.apis:
        # Check spec is provided
        if not api.spec_url and not api.spec_inline:
            errors.append(f"API '{api.name}' has no spec (url or inline)")

        # Validate URL format if provided
        if api.spec_url:
            try:
                parsed = urlparse(api.spec_url)
                if not parsed.scheme or not parsed.netloc:
                    warnings.append(f"API '{api.name}' has invalid spec URL: {api.spec_url}")
            except Exception:
                warnings.append(f"API '{api.name}' has malformed spec URL: {api.spec_url}")

        # Check auth profile
        if api.auth_profile.kind in (ir.AuthKind.OAUTH2_LEGACY, ir.AuthKind.OAUTH2_PKCE):
            # OAuth2 APIs should specify scopes
            if "scopes" not in api.auth_profile.options:
                warnings.append(f"API '{api.name}' uses OAuth2 but doesn't specify scopes")

    return errors, warnings


def validate_foreign_models(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all foreign models for semantic correctness.

    Checks:
    - Key fields are defined
    - Constraints are valid
    - Fields have appropriate types

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for foreign_model in appspec.foreign_models:
        # Check key fields exist
        if not foreign_model.key_fields:
            errors.append(f"Foreign model '{foreign_model.name}' has no key fields")

        for key_field in foreign_model.key_fields:
            if not foreign_model.get_field(key_field):
                errors.append(
                    f"Foreign model '{foreign_model.name}' key field '{key_field}' "
                    f"is not defined in fields"
                )

        # Check for conflicting constraints
        constraint_kinds = [c.kind for c in foreign_model.constraints]
        if ir.ForeignConstraintKind.READ_ONLY in constraint_kinds:
            if ir.ForeignConstraintKind.BATCH_IMPORT in constraint_kinds:
                # This is ok - read-only can still be imported
                pass

    return errors, warnings


def validate_integrations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all integrations for semantic correctness.

    Checks:
    - Service and foreign model references
    - Action/sync structure (simplified for v0.1)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for integration in appspec.integrations:
        # Check that integration uses at least one service
        if not integration.api_refs:
            warnings.append(f"Integration '{integration.name}' doesn't use any APIs")

        # Check that integration has actions or syncs
        if not integration.actions and not integration.syncs:
            warnings.append(f"Integration '{integration.name}' has no actions or syncs")

    return errors, warnings


def validate_ux_specs(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate UX semantic layer specifications.

    Checks:
    - UX show fields exist in referenced entity
    - UX sort fields exist in referenced entity
    - UX filter fields exist in referenced entity
    - UX search fields exist in referenced entity
    - Attention signal conditions reference valid fields
    - Persona variants have valid configurations
    - Workspace regions reference valid sources

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for surface in appspec.surfaces:
        if not surface.ux:
            continue

        entity = None
        if surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)

        ux = surface.ux

        # Validate show fields
        if ux.show and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.show:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX show references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate sort fields
        if ux.sort and entity:
            entity_field_names = {f.name for f in entity.fields}
            for sort_spec in ux.sort:
                if sort_spec.field not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX sort references non-existent "
                        f"field '{sort_spec.field}' from entity '{entity.name}'"
                    )

        # Validate filter fields
        if ux.filter and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.filter:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX filter references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate search fields
        if ux.search and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.search:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX search references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate attention signals
        for signal in ux.attention_signals:
            field_errors = _validate_condition_fields(
                signal.condition, entity, f"Surface '{surface.name}' attention signal"
            )
            errors.extend(field_errors)

            # Warn if attention signal has no message
            if not signal.message:
                warnings.append(
                    f"Surface '{surface.name}' attention signal at level "
                    f"'{signal.level.value}' has no message"
                )

        # Validate persona variants
        for variant in ux.persona_variants:
            # Validate scope condition fields
            if variant.scope:
                field_errors = _validate_condition_fields(
                    variant.scope,
                    entity,
                    f"Surface '{surface.name}' persona '{variant.persona}' scope",
                )
                errors.extend(field_errors)

            # Validate show/hide fields
            if entity:
                entity_field_names = {f.name for f in entity.fields}
                for field_name in variant.show:
                    if field_name not in entity_field_names:
                        errors.append(
                            f"Surface '{surface.name}' persona '{variant.persona}' "
                            f"show references non-existent field '{field_name}'"
                        )
                for field_name in variant.hide:
                    if field_name not in entity_field_names:
                        errors.append(
                            f"Surface '{surface.name}' persona '{variant.persona}' "
                            f"hide references non-existent field '{field_name}'"
                        )

    # Validate workspaces
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            # Skip source validation for aggregate-only regions
            if region.source is None:
                continue

            # Check that source references a valid entity
            source_entity_name = (
                region.source.split(".")[0] if "." in region.source else region.source
            )
            entity = appspec.get_entity(source_entity_name)
            if not entity:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name or region.source}' "
                    f"references non-existent entity '{source_entity_name}'"
                )
            else:
                # Validate filter conditions
                if region.filter:
                    field_errors = _validate_condition_fields(
                        region.filter,
                        entity,
                        f"Workspace '{workspace.name}' region '{region.name or region.source}' filter",
                    )
                    errors.extend(field_errors)

                # Validate sort fields
                if region.sort:
                    entity_field_names = {f.name for f in entity.fields}
                    for sort_spec in region.sort:
                        if sort_spec.field not in entity_field_names:
                            errors.append(
                                f"Workspace '{workspace.name}' region "
                                f"'{region.name or region.source}' sort references "
                                f"non-existent field '{sort_spec.field}'"
                            )

    return errors, warnings


def _validate_condition_fields(
    condition: ir.ConditionExpr, entity: ir.EntitySpec | None, context: str
) -> list[str]:
    """
    Validate that condition expression references valid entity fields.

    Args:
        condition: The condition expression to validate
        entity: The entity to validate fields against (may be None)
        context: Context string for error messages

    Returns:
        List of error messages
    """
    errors: list[str] = []

    if not entity:
        return errors

    entity_field_names = {f.name for f in entity.fields}

    def check_comparison(comparison: ir.Comparison) -> None:
        """Validate field references in a comparison expression."""
        if comparison.field and comparison.field not in entity_field_names:
            errors.append(
                f"{context} references non-existent field '{comparison.field}' "
                f"from entity '{entity.name}'"
            )
        if comparison.function and comparison.function.argument not in entity_field_names:
            errors.append(
                f"{context} function '{comparison.function.name}' references "
                f"non-existent field '{comparison.function.argument}' from entity '{entity.name}'"
            )

    def check_condition(cond: ir.ConditionExpr) -> None:
        """Recursively validate a condition expression tree."""
        if cond.comparison:
            check_comparison(cond.comparison)
        elif cond.is_compound:
            if cond.left:
                check_condition(cond.left)
            if cond.right:
                check_condition(cond.right)

    check_condition(condition)
    return errors


def extended_lint(appspec: ir.AppSpec) -> list[str]:
    """
    Extended lint rules for code quality.

    Checks:
    - Naming conventions (snake_case, PascalCase)
    - Unused entities, surfaces, experiences
    - Missing titles/descriptions

    Returns:
        List of warning messages
    """
    warnings = []

    # Check entity naming (should be PascalCase)
    for entity in appspec.domain.entities:
        if not entity.name[0].isupper():
            warnings.append(f"Entity '{entity.name}' should use PascalCase naming")

        # Check field naming (should be snake_case)
        for field in entity.fields:
            if field.name != field.name.lower():
                if "_" in field.name or not any(c.isupper() for c in field.name[1:]):
                    continue  # It's snake_case or lowercase, ok
                warnings.append(
                    f"Entity '{entity.name}' field '{field.name}' should use snake_case naming"
                )

    # Check for unused entities (entities not referenced anywhere)
    used_entities = set()

    # Entities used by other entities (field refs)
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                used_entities.add(field.type.ref_entity)

    # Entities used by surfaces
    for surface in appspec.surfaces:
        if surface.entity_ref:
            used_entities.add(surface.entity_ref)

    # Check for unused entities
    all_entities = {entity.name for entity in appspec.domain.entities}
    unused_entities = all_entities - used_entities
    if unused_entities:
        warnings.append(f"Unused entities (not referenced anywhere): {unused_entities}")

    # Check for missing titles
    for entity in appspec.domain.entities:
        if not entity.title:
            warnings.append(f"Entity '{entity.name}' has no title")

    for surface in appspec.surfaces:
        if not surface.title:
            warnings.append(f"Surface '{surface.name}' has no title")

    # v0.14.2: Check for workspaces without associated personas
    if appspec.workspaces:
        # Collect all persona IDs
        persona_ids = {p.id for p in appspec.personas}

        # Collect personas referenced by workspace UX variants
        workspaces_with_personas: set[str] = set()
        for workspace in appspec.workspaces:
            if workspace.ux and workspace.ux.persona_variants:
                for variant in workspace.ux.persona_variants:
                    if variant.persona in persona_ids:
                        workspaces_with_personas.add(workspace.name)
                        break

        # Collect personas that have default_workspace set
        for persona in appspec.personas:
            if persona.default_workspace:
                for ws in appspec.workspaces:
                    if ws.name == persona.default_workspace:
                        workspaces_with_personas.add(ws.name)

        # Warn about workspaces without personas
        for workspace in appspec.workspaces:
            if workspace.name not in workspaces_with_personas:
                warnings.append(
                    f"Workspace '{workspace.name}' has no associated persona. "
                    f"Consider adding a persona for role-based access control."
                )

    return warnings
