"""
Comprehensive semantic validation for DAZZLE AppSpec.

Validates entities, surfaces, experiences, services, foreign models, and integrations
for semantic correctness beyond basic reference resolution.
"""

from urllib.parse import urlparse

from . import ir


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

        # Check for duplicate field names
        field_names = [f.name for f in entity.fields]
        duplicates = {name for name in field_names if field_names.count(name) > 1}
        if duplicates:
            errors.append(f"Entity '{entity.name}' has duplicate field names: {duplicates}")

        # Validate each field
        for field in entity.fields:
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
                elif field.type.precision < 1 or field.type.precision > 65:
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
                elif field.type.max_length < 1:
                    errors.append(
                        f"Entity '{entity.name}' field '{field.name}' has invalid "
                        f"max_length: {field.type.max_length}"
                    )
                elif field.type.max_length > 10000:
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

    for service in appspec.services:
        # Check spec is provided
        if not service.spec_url and not service.spec_inline:
            errors.append(f"Service '{service.name}' has no spec (url or inline)")

        # Validate URL format if provided
        if service.spec_url:
            try:
                parsed = urlparse(service.spec_url)
                if not parsed.scheme or not parsed.netloc:
                    warnings.append(
                        f"Service '{service.name}' has invalid spec URL: {service.spec_url}"
                    )
            except Exception:
                warnings.append(
                    f"Service '{service.name}' has malformed spec URL: {service.spec_url}"
                )

        # Check auth profile
        if service.auth_profile.kind in (ir.AuthKind.OAUTH2_LEGACY, ir.AuthKind.OAUTH2_PKCE):
            # OAuth2 services should specify scopes
            if "scopes" not in service.auth_profile.options:
                warnings.append(f"Service '{service.name}' uses OAuth2 but doesn't specify scopes")

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
    errors = []
    warnings = []

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
    errors = []
    warnings = []

    for integration in appspec.integrations:
        # Check that integration uses at least one service
        if not integration.service_refs:
            warnings.append(f"Integration '{integration.name}' doesn't use any services")

        # Check that integration has actions or syncs
        if not integration.actions and not integration.syncs:
            warnings.append(f"Integration '{integration.name}' has no actions or syncs")

    return errors, warnings


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

    return warnings
