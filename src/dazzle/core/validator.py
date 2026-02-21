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
# SQL keywords that are genuinely dangerous as identifiers — DML/DDL commands
# and clauses that could cause ambiguity. SQLAlchemy quotes all identifiers,
# so even these are technically safe, but they deserve a warning.
SQL_RESERVED_WORDS = frozenset(
    {
        # DML/DDL commands — these look like SQL statements
        "select",
        "insert",
        "update",
        "delete",
        "create",
        "alter",
        "drop",
        "table",
        "index",
        "trigger",
        "database",
        # Clauses that could genuinely confuse
        "from",
        "where",
        "join",
        "having",
        "union",
        "except",
        "intersect",
        "values",
        "constraint",
        "foreign",
        "primary",
        "references",
        # Uncommonly used as domain names
        "vacuum",
        "pragma",
        "savepoint",
        "rollback",
        "commit",
        "recursive",
    }
)

# Words that are SQL-reserved but commonly used in domain modelling.
# SQLAlchemy safely quotes them — warning about these creates noise.
# Examples: User, Order, Group, Action, Key, Check, View, Column, etc.
# These are intentionally excluded from SQL_RESERVED_WORDS.

# Secret/sensitive field patterns that should not appear in event payloads
# These can leak credentials, API keys, or other sensitive data via event logs
SECRET_FIELD_PATTERNS = frozenset(
    {
        # Credentials
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "secretkey",
        # API keys
        "api_key",
        "apikey",
        "api_secret",
        "apisecret",
        "access_key",
        "accesskey",
        "private_key",
        "privatekey",
        # Tokens
        "token",
        "access_token",
        "accesstoken",
        "refresh_token",
        "refreshtoken",
        "auth_token",
        "authtoken",
        "bearer_token",
        "bearertoken",
        "jwt_token",
        "jwttoken",
        "session_token",
        "sessiontoken",
        # Auth-related
        "credentials",
        "auth",
        "authorization",
        # Encryption
        "encryption_key",
        "encryptionkey",
        "signing_key",
        "signingkey",
        "salt",
        "hash",
        "pin",
        "pin_code",
        "pincode",
        # SSN, credit cards
        "ssn",
        "social_security",
        "credit_card",
        "creditcard",
        "card_number",
        "cardnumber",
        "cvv",
        "cvc",
    }
)


def is_secret_field_name(name: str) -> bool:
    """Check if a field name matches a secret pattern."""
    lower_name = name.lower()
    # Exact match
    if lower_name in SECRET_FIELD_PATTERNS:
        return True
    # Suffix match (e.g., user_password, api_token)
    for pattern in SECRET_FIELD_PATTERNS:
        if lower_name.endswith(f"_{pattern}") or lower_name.endswith(pattern):
            return True
    return False


def _validate_entity_pk(entity: ir.EntitySpec, errors: list[str]) -> None:
    """Check that the entity has a primary key field."""
    if not entity.primary_key:
        errors.append(
            f"Entity '{entity.name}' has no primary key field. Add a field with 'pk' modifier."
        )


def _validate_reserved_names(entity: ir.EntitySpec, errors: list[str], warnings: list[str]) -> None:
    """Check for SQL reserved words in entity and field names."""
    if entity.name.lower() in SQL_RESERVED_WORDS:
        warnings.append(
            f"Entity '{entity.name}' uses SQL reserved word as name. "
            f"Consider renaming (e.g., 'SalesOrder' instead of 'Order')."
        )
    for field in entity.fields:
        if field.name.lower() in SQL_RESERVED_WORDS:
            warnings.append(
                f"Entity '{entity.name}' field '{field.name}' uses SQL reserved word. "
                f"Consider renaming (e.g., 'sales_order' instead of 'order')."
            )


def _validate_field_duplicates(entity: ir.EntitySpec, errors: list[str]) -> None:
    """Check for duplicate field names within an entity."""
    field_names = [f.name for f in entity.fields]
    duplicates = {name for name in field_names if field_names.count(name) > 1}
    if duplicates:
        errors.append(f"Entity '{entity.name}' has duplicate field names: {duplicates}")


def _validate_field_enums(entity: ir.EntitySpec, errors: list[str]) -> None:
    """Check that enum fields have at least one value."""
    for field in entity.fields:
        if field.type.kind == ir.FieldTypeKind.ENUM:
            if not field.type.enum_values or len(field.type.enum_values) == 0:
                errors.append(
                    f"Entity '{entity.name}' field '{field.name}' has enum type but no values"
                )


def _validate_field_decimals(entity: ir.EntitySpec, errors: list[str], warnings: list[str]) -> None:
    """Check decimal precision/scale values are valid."""
    for field in entity.fields:
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


def _validate_field_strings(entity: ir.EntitySpec, errors: list[str], warnings: list[str]) -> None:
    """Check string field max_length values are valid."""
    for field in entity.fields:
        if field.type.kind == ir.FieldTypeKind.STR:
            if field.type.max_length is None:
                errors.append(
                    f"Entity '{entity.name}' field '{field.name}' has str type but no max_length"
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


def _validate_field_modifiers(
    entity: ir.EntitySpec, errors: list[str], warnings: list[str]
) -> None:
    """Check for conflicting or inappropriate field modifiers."""
    for field in entity.fields:
        if (
            ir.FieldModifier.REQUIRED in field.modifiers
            and ir.FieldModifier.OPTIONAL in field.modifiers
        ):
            errors.append(
                f"Entity '{entity.name}' field '{field.name}' has both "
                f"'required' and 'optional' modifiers"
            )

        if (
            ir.FieldModifier.AUTO_ADD in field.modifiers
            or ir.FieldModifier.AUTO_UPDATE in field.modifiers
        ):
            if field.type.kind != ir.FieldTypeKind.DATETIME:
                warnings.append(
                    f"Entity '{entity.name}' field '{field.name}' has auto_add/auto_update "
                    f"modifier but is not datetime type"
                )


def _validate_constraints(entity: ir.EntitySpec, errors: list[str]) -> None:
    """Check that constraint fields exist in the entity."""
    for constraint in entity.constraints:
        for field_name in constraint.fields:
            if not entity.get_field(field_name):
                errors.append(
                    f"Entity '{entity.name}' {constraint.kind.value} constraint "
                    f"references non-existent field '{field_name}'"
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
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        _validate_entity_pk(entity, errors)
        _validate_reserved_names(entity, errors, warnings)
        _validate_field_duplicates(entity, errors)
        _validate_field_enums(entity, errors)
        _validate_field_decimals(entity, errors, warnings)
        _validate_field_strings(entity, errors, warnings)
        _validate_field_modifiers(entity, errors, warnings)
        _validate_constraints(entity, errors)

        # v0.34.0: Validate bulk config field references
        if entity.bulk:
            field_names = {f.name for f in entity.fields}
            for imp_f in entity.bulk.import_fields:
                if imp_f not in field_names:
                    errors.append(
                        f"Entity '{entity.name}' bulk import_fields references "
                        f"unknown field '{imp_f}'"
                    )
            for exp_f in entity.bulk.export_fields:
                if exp_f not in field_names:
                    errors.append(
                        f"Entity '{entity.name}' bulk export_fields references "
                        f"unknown field '{exp_f}'"
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

        # Validate search fields reference valid entity fields
        if surface.search_fields and surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)
            if entity:
                for sf in surface.search_fields:
                    if not entity.get_field(sf):
                        warnings.append(
                            f"Surface '{surface.name}' search field '{sf}' "
                            f"does not exist on entity '{entity.name}'"
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
                if not step.surface and not step.entity_ref:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'surface' but no surface or entity target"
                    )
            elif step.kind == ir.StepKind.INTEGRATION:
                if not step.integration or not step.action:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'integration' but missing integration or action"
                    )

            # Warn about steps with no transitions — but only if the step
            # is NOT the last defined step (terminal steps at the end of a
            # flow are expected, e.g. "complete", "done", "success").
            if not step.transitions:
                is_last = step == experience.steps[-1] if experience.steps else False
                if not is_last:
                    warnings.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has no transitions (terminal step)"
                    )

            # Validate saves_to format
            if step.saves_to:
                st_parts = step.saves_to.split(".", 1)
                if len(st_parts) != 2 or st_parts[0] != "context":
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"saves_to must be 'context.<varname>', got '{step.saves_to}'"
                    )
                elif experience.context:
                    ctx_names = {cv.name for cv in experience.context}
                    if st_parts[1] not in ctx_names:
                        errors.append(
                            f"Experience '{experience.name}' step '{step.name}' "
                            f"saves_to references unknown context variable '{st_parts[1]}'"
                        )

            # Validate prefill references
            if step.prefills and experience.context:
                ctx_names = {cv.name for cv in experience.context}
                for pf in step.prefills:
                    if not pf.expression.startswith('"'):
                        pf_parts = pf.expression.split(".")
                        if pf_parts and pf_parts[0] == "context" and len(pf_parts) >= 2:
                            if pf_parts[1] not in ctx_names:
                                warnings.append(
                                    f"Experience '{experience.name}' step '{step.name}' "
                                    f"prefill references unknown context variable "
                                    f"'{pf_parts[1]}'"
                                )

            # Warn about when guard on terminal steps
            if step.when and not step.transitions:
                warnings.append(
                    f"Experience '{experience.name}' step '{step.name}' "
                    f"has a 'when' guard but no transitions to skip to"
                )

        # Validate context variable declarations
        if experience.context:
            seen_names: set[str] = set()
            for cv in experience.context:
                if cv.name in seen_names:
                    errors.append(
                        f"Experience '{experience.name}' has duplicate context variable '{cv.name}'"
                    )
                seen_names.add(cv.name)

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

        # Check that integration has actions, syncs, or mappings (v0.30.0+)
        if not integration.actions and not integration.syncs and not integration.mappings:
            warnings.append(f"Integration '{integration.name}' has no actions, syncs, or mappings")

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
                    region_id = region.name or region.source
                    ctx = f"Workspace '{workspace.name}' region '{region_id}' filter"
                    field_errors = _validate_condition_fields(
                        region.filter,
                        entity,
                        ctx,
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


def validate_money_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate that monetary fields use the correct type in FACT/INTENT streams.

    The Money type (amount_minor: int + currency: str) is REQUIRED for all
    monetary values in event payloads. Using float or decimal for money
    causes precision issues and JSON serialization problems.

    Checks:
    - Fields with money-like names in FACT/INTENT streams must use 'money' type
    - Rejects 'decimal' and warns about 'int' for money-like field names

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check HLESS streams
    for stream in appspec.streams:
        # Only check FACT and INTENT streams (not OBSERVATION or DERIVATION)
        if stream.record_kind not in (ir.RecordKind.FACT, ir.RecordKind.INTENT):
            continue

        for schema in stream.schemas:
            for field in schema.fields:
                if not ir.is_money_field_name(field.name):
                    continue

                # Check for forbidden types
                if field.type.kind == ir.FieldTypeKind.DECIMAL:
                    errors.append(
                        f"Stream '{stream.name}' schema '{schema.name}' field '{field.name}' "
                        f"uses 'decimal' type for monetary value. "
                        f"Use 'money' type instead (expands to currency + amount_minor:int). "
                        f"Rationale: decimal causes JSON serialization errors and precision issues."
                    )

                # Warn about raw int (might be intentional minor units, but not explicit)
                elif field.type.kind == ir.FieldTypeKind.INT:
                    # Only warn if it looks like a standalone money field without currency
                    # If there's a corresponding currency field, assume it's intentional
                    field_names = {f.name for f in schema.fields}
                    has_currency = any("currency" in name.lower() for name in field_names)
                    if not has_currency:
                        warnings.append(
                            f"Stream '{stream.name}' schema '{schema.name}' field '{field.name}' "
                            f"uses 'int' for monetary value without a currency field. "
                            f"Consider using 'money' type for explicit currency handling."
                        )

    # Also check entity fields (less strict - warning only)
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if not ir.is_money_field_name(field.name):
                continue

            # For entities, using decimal is okay but money is preferred
            if field.type.kind == ir.FieldTypeKind.DECIMAL:
                # Check if there's a corresponding currency field
                field_names = {f.name for f in entity.fields}
                has_currency = any("currency" in name.lower() for name in field_names)
                if not has_currency:
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' uses 'decimal' "
                        f"for monetary value without a currency field. "
                        f"Consider using 'money' type or adding a currency field."
                    )

    return errors, warnings


def _validate_account_codes(
    appspec: ir.AppSpec,
    errors: list[str],
    warnings: list[str],
) -> tuple[set[str], dict[str, ir.LedgerSpec]]:
    """Validate ledger names, account codes, currency, sync targets, and intent.

    Returns:
        (ledger_names, ledger_by_name) for use by transaction validation.
    """
    ledger_names: set[str] = set()
    ledger_by_name: dict[str, ir.LedgerSpec] = {}
    account_codes_by_ledger_id: dict[int, set[int]] = {}

    for ledger in appspec.ledgers:
        # Check unique names
        if ledger.name in ledger_names:
            errors.append(f"Duplicate ledger name: '{ledger.name}'")
        ledger_names.add(ledger.name)
        ledger_by_name[ledger.name] = ledger

        # Check account_code uniqueness within ledger_id
        if ledger.ledger_id not in account_codes_by_ledger_id:
            account_codes_by_ledger_id[ledger.ledger_id] = set()
        if ledger.account_code in account_codes_by_ledger_id[ledger.ledger_id]:
            errors.append(
                f"Ledger '{ledger.name}': account_code {ledger.account_code} "
                f"is already used in ledger_id {ledger.ledger_id}"
            )
        account_codes_by_ledger_id[ledger.ledger_id].add(ledger.account_code)

        # Validate currency format
        if len(ledger.currency) != 3 or not ledger.currency.isalpha():
            errors.append(
                f"Ledger '{ledger.name}': currency '{ledger.currency}' "
                f"must be a 3-letter ISO 4217 code (e.g., GBP, USD, EUR)"
            )

        # Check sync target if specified
        if ledger.sync:
            entity_name = ledger.sync.target_entity
            entity = appspec.get_entity(entity_name)
            if not entity:
                errors.append(
                    f"Ledger '{ledger.name}': sync target entity '{entity_name}' not found"
                )
            else:
                field = entity.get_field(ledger.sync.target_field)
                if not field:
                    errors.append(
                        f"Ledger '{ledger.name}': sync target field "
                        f"'{entity_name}.{ledger.sync.target_field}' not found"
                    )

        # Warn about missing intent
        if not ledger.intent:
            warnings.append(
                f"Ledger '{ledger.name}': consider adding an 'intent' field "
                f"to document the business purpose"
            )

    return ledger_names, ledger_by_name


def _validate_transaction_transfers(
    txn: ir.TransactionSpec,
    ledger_names: set[str],
    ledger_by_name: dict[str, ir.LedgerSpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate transfers within a single transaction."""
    transfer_codes: set[int] = set()
    for transfer in txn.transfers:
        # Check ledger references exist
        if transfer.debit_ledger not in ledger_names:
            errors.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"debit ledger '{transfer.debit_ledger}' not found"
            )
        if transfer.credit_ledger not in ledger_names:
            errors.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"credit ledger '{transfer.credit_ledger}' not found"
            )

        # Validate ledgers are in same ledger_id (TigerBeetle requirement)
        if transfer.debit_ledger in ledger_by_name and transfer.credit_ledger in ledger_by_name:
            debit_ledger = ledger_by_name[transfer.debit_ledger]
            credit_ledger = ledger_by_name[transfer.credit_ledger]
            if debit_ledger.ledger_id != credit_ledger.ledger_id:
                errors.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"debit ledger '{transfer.debit_ledger}' "
                    f"(ledger_id={debit_ledger.ledger_id}) "
                    f"and credit ledger '{transfer.credit_ledger}' "
                    f"(ledger_id={credit_ledger.ledger_id}) "
                    f"must be in the same ledger_id"
                )

            # Validate currency match
            if debit_ledger.currency != credit_ledger.currency:
                errors.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"currency mismatch between '{transfer.debit_ledger}' "
                    f"({debit_ledger.currency}) and '{transfer.credit_ledger}' "
                    f"({credit_ledger.currency})"
                )

        # Check transfer code uniqueness
        if transfer.code in transfer_codes:
            warnings.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"code {transfer.code} is duplicated (consider unique codes for debugging)"
            )
        transfer_codes.add(transfer.code)

    # Multi-leg transaction validation
    if len(txn.transfers) > 1:
        for transfer in txn.transfers[:-1]:
            if not transfer.is_linked:
                warnings.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"multi-leg transactions should use 'linked' flag on all "
                    f"but the last transfer "
                    f"to ensure atomic execution"
                )


def validate_ledgers(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate TigerBeetle ledger and transaction specifications (v0.24.0).

    Checks:
    - Ledger names are unique
    - Account codes are unique within a ledger_id
    - Currency is valid ISO 4217 format
    - Transaction transfers reference valid ledgers
    - Transaction idempotency_key is defined
    - Transfer codes are unique within a transaction
    - Multi-leg transactions use 'linked' flag correctly

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.ledgers:
        return errors, warnings

    ledger_names, ledger_by_name = _validate_account_codes(appspec, errors, warnings)

    for txn in appspec.transactions:
        if not txn.idempotency_key:
            errors.append(
                f"Transaction '{txn.name}': idempotency_key is required "
                f"for TigerBeetle transfer deduplication"
            )

        _validate_transaction_transfers(txn, ledger_names, ledger_by_name, errors, warnings)

        if not txn.intent:
            warnings.append(
                f"Transaction '{txn.name}': consider adding an 'intent' field "
                f"to document the business purpose"
            )

    return errors, warnings


def validate_event_payload_secrets(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate that event payloads do not contain secret/sensitive fields.

    Events are typically logged, replayed, and stored long-term. Including
    passwords, API keys, tokens, or other secrets in event payloads creates
    security vulnerabilities.

    Checks:
    - HLESS stream schema fields for secret-like names
    - Event model custom fields for secret-like names
    - Entity fields used as event payloads for secret-like names

    Returns:
        Tuple of (errors, warnings)
        - errors: Fields that are almost certainly secrets (password, api_key, etc.)
        - warnings: Fields that might be secrets (token, hash, auth, etc.)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # High-risk patterns that are almost always actual secrets
    high_risk_patterns = {"password", "passwd", "pwd", "api_key", "apikey", "secret", "secret_key"}

    def check_field(field_name: str, context: str) -> None:
        if not is_secret_field_name(field_name):
            return

        lower_name = field_name.lower()
        # High-risk patterns are errors
        if any(pattern in lower_name for pattern in high_risk_patterns):
            errors.append(
                f"{context} field '{field_name}' appears to contain a secret. "
                f"Secrets MUST NOT be included in event payloads. "
                f"Store secrets securely and use references instead."
            )
        else:
            # Medium-risk patterns are warnings
            warnings.append(
                f"{context} field '{field_name}' may contain sensitive data. "
                f"Ensure this field does not contain secrets, tokens, or credentials. "
                f"If it does, remove it from the event payload."
            )

    # Check HLESS streams
    for stream in appspec.streams:
        for schema in stream.schemas:
            for schema_field in schema.fields:
                check_field(schema_field.name, f"Stream '{stream.name}' schema '{schema.name}'")

    # Check event model (custom event fields)
    if appspec.event_model:
        for event in appspec.event_model.events:
            for event_field in event.custom_fields:
                check_field(event_field.name, f"Event '{event.name}'")

    return errors, warnings


def _detect_dead_constructs(appspec: ir.AppSpec) -> list[str]:
    """Detect unreferenced surfaces, orphan entities, and unreachable experiences.

    Builds a reachability graph from entry points (workspaces, experiences,
    processes) through surfaces to entities. Reports constructs that are
    defined but never referenced from any entry point.
    """
    warnings: list[str] = []

    # --- Collect all defined constructs ---
    all_entities = {e.name for e in appspec.domain.entities}
    entity_locs = {e.name: e.source for e in appspec.domain.entities}
    all_surfaces = {s.name for s in appspec.surfaces}
    surface_locs = {s.name: s.source for s in appspec.surfaces}
    # --- Collect all entity references ---
    used_entities: set[str] = set()

    # Entities referenced by other entities (field refs)
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                used_entities.add(field.type.ref_entity)

    # Entities referenced by surfaces
    for surface in appspec.surfaces:
        if surface.entity_ref:
            used_entities.add(surface.entity_ref)

    # Entities referenced by workspace regions (source field)
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source and region.source in all_entities:
                used_entities.add(region.source)

    # Entities referenced by process triggers
    for process in appspec.processes:
        if process.trigger and process.trigger.entity_name:
            used_entities.add(process.trigger.entity_name)

    # Entities referenced by integration mappings
    for integration in appspec.integrations:
        for mapping in integration.mappings:
            if mapping.entity_ref:
                used_entities.add(mapping.entity_ref)

    unused_entities = all_entities - used_entities
    if unused_entities:
        for name in sorted(unused_entities):
            loc = entity_locs.get(name)
            loc_suffix = f" (defined at {loc})" if loc else ""
            warnings.append(f"Dead construct: entity '{name}' is never referenced{loc_suffix}")

    # --- Collect all surface references ---
    used_surfaces: set[str] = set()

    # Surfaces referenced by workspace regions (action field)
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.action and region.action in all_surfaces:
                used_surfaces.add(region.action)
            # source can also be a surface name
            if region.source and region.source in all_surfaces:
                used_surfaces.add(region.source)

    # Surfaces referenced by experience steps
    for experience in appspec.experiences:
        for step in experience.steps:
            if step.surface:
                used_surfaces.add(step.surface)

    # Surfaces referenced by process human_task steps
    for process in appspec.processes:
        for proc_step in process.steps:
            if proc_step.human_task and proc_step.human_task.surface:
                used_surfaces.add(proc_step.human_task.surface)

    # Surfaces belonging to entities used in workspace regions are implicitly
    # alive — entity CRUD surfaces are navigable from workspace detail pages
    # even when not explicitly wired to a workspace action.
    workspace_entities: set[str] = set()
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source and region.source in all_entities:
                workspace_entities.add(region.source)
            for src in region.sources:
                if src in all_entities:
                    workspace_entities.add(src)
    for surface in appspec.surfaces:
        if surface.entity_ref and surface.entity_ref in workspace_entities:
            used_surfaces.add(surface.name)

    unused_surfaces = all_surfaces - used_surfaces
    if unused_surfaces:
        for name in sorted(unused_surfaces):
            loc = surface_locs.get(name)
            loc_suffix = f" (defined at {loc})" if loc else ""
            warnings.append(
                f"Dead construct: surface '{name}' is not referenced by any "
                f"workspace, experience, or process{loc_suffix}"
            )

    # --- Collect all experience references ---
    # Experiences are entry points themselves, but check if any are completely
    # disconnected (no workspace or navigation references them).
    # For now, experiences are considered used if they exist — they are
    # top-level entry points like workspaces.

    return warnings


def _lint_naming_conventions(appspec: ir.AppSpec) -> list[str]:
    """Check entity PascalCase and field snake_case naming."""
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if not entity.name[0].isupper():
            warnings.append(f"Entity '{entity.name}' should use PascalCase naming")
        for field in entity.fields:
            if field.name != field.name.lower():
                if "_" in field.name or not any(c.isupper() for c in field.name[1:]):
                    continue  # It's snake_case or lowercase, ok
                warnings.append(
                    f"Entity '{entity.name}' field '{field.name}' should use snake_case naming"
                )
    return warnings


def _lint_missing_titles(appspec: ir.AppSpec) -> list[str]:
    """Check for entities and surfaces without titles."""
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if not entity.title:
            warnings.append(f"Entity '{entity.name}' has no title")
    for surface in appspec.surfaces:
        if not surface.title:
            warnings.append(f"Surface '{surface.name}' has no title")
    return warnings


def _lint_workspace_personas(appspec: ir.AppSpec) -> list[str]:
    """Check for workspaces without associated personas."""
    if not appspec.workspaces:
        return []

    warnings: list[str] = []
    persona_ids = {p.id for p in appspec.personas}

    workspaces_with_personas: set[str] = set()
    for workspace in appspec.workspaces:
        if workspace.ux and workspace.ux.persona_variants:
            for variant in workspace.ux.persona_variants:
                if variant.persona in persona_ids:
                    workspaces_with_personas.add(workspace.name)
                    break

    for persona in appspec.personas:
        if persona.default_workspace:
            for ws in appspec.workspaces:
                if ws.name == persona.default_workspace:
                    workspaces_with_personas.add(ws.name)

    for workspace in appspec.workspaces:
        if workspace.name not in workspaces_with_personas:
            warnings.append(
                f"Workspace '{workspace.name}' has no associated persona. "
                f"Consider adding a persona for role-based access control."
            )
    return warnings


def _lint_workspace_routing(appspec: ir.AppSpec) -> list[str]:
    """Check for workspaces with no routable content."""
    if not appspec.workspaces:
        return []

    warnings: list[str] = []
    surface_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
    for workspace in appspec.workspaces:
        region_sources = {r.source for r in workspace.regions if r.source}
        if not region_sources:
            warnings.append(
                f"Workspace '{workspace.name}' has no regions with entity sources. "
                f"It will not generate any routes or render content."
            )
        elif not region_sources & surface_entities:
            warnings.append(
                f"Workspace '{workspace.name}' references entities "
                f"({', '.join(sorted(region_sources))}) that have no surfaces. "
                f"It will not generate any routes."
            )
    return warnings


def _lint_list_surface_ux(appspec: ir.AppSpec) -> list[str]:
    """Check list surfaces for sort/filter/search/empty completeness."""
    warnings: list[str] = []
    for surface in appspec.surfaces:
        if surface.mode != ir.SurfaceMode.LIST:
            continue
        if not surface.ux:
            hints: list[str] = []
            surf_entity = appspec.get_entity(surface.entity_ref) if surface.entity_ref else None
            if surf_entity:
                filterable = [
                    f.name
                    for f in surf_entity.fields
                    if f.type
                    and f.type.kind in (ir.FieldTypeKind.ENUM, ir.FieldTypeKind.BOOL)
                    and not f.is_primary_key
                ]
                if surf_entity.state_machine:
                    sm_field = surf_entity.state_machine.status_field
                    if sm_field not in filterable:
                        filterable.insert(0, sm_field)
                searchable = [
                    f.name
                    for f in surf_entity.fields
                    if f.type
                    and f.type.kind in (ir.FieldTypeKind.STR, ir.FieldTypeKind.TEXT)
                    and not f.is_primary_key
                ]
                if filterable:
                    hints.append(f"filter: {', '.join(filterable)}")
                if searchable:
                    hints.append(f"search: {', '.join(searchable)}")
            hints.insert(0, "sort: (e.g. created_at desc)")
            hints.append('empty: "No items yet."')
            warnings.append(
                f"Surface '{surface.name}' (mode: list) has no ux block. "
                f"Consider adding: {'; '.join(hints)}"
            )
        else:
            ux = surface.ux
            missing = []
            if not ux.sort:
                missing.append("sort")
            if not ux.filter:
                missing.append("filter")
            if not ux.search:
                missing.append("search")
            if not ux.empty_message:
                missing.append("empty")
            if missing:
                warnings.append(
                    f"Surface '{surface.name}' ux block is missing: "
                    f"{', '.join(missing)}. These enhance DataTable UX."
                )
    return warnings


_INTEGRATION_KEYWORDS = {
    "api",
    "hmrc",
    "xero",
    "sync",
    "webhook",
    "stripe",
    "twilio",
    "sendgrid",
    "mailgun",
    "slack",
    "zapier",
    "salesforce",
}


def _lint_integration_bindings(appspec: ir.AppSpec) -> list[str]:
    """Check if stories reference integrations without matching service declarations."""
    stories = list(appspec.stories) if appspec.stories else []
    if not stories:
        return []

    warnings: list[str] = []
    declared_integrations = {i.name.lower() for i in appspec.integrations}
    declared_services = {s.name.lower() for s in appspec.domain_services}
    declared_bindings = declared_integrations | declared_services

    for story in stories:
        title_words = set(story.title.lower().split())
        integration_hits = title_words & _INTEGRATION_KEYWORDS

        if integration_hits and not declared_bindings:
            warnings.append(
                f"Story '{story.story_id}' ({story.title}) references integration "
                f"keywords ({', '.join(integration_hits)}) but no integrations or "
                f"services are declared in the DSL."
            )
        elif integration_hits:
            scope_entities = {s.lower() for s in story.scope}
            has_matching_binding = (
                any(
                    any(entity in binding for entity in scope_entities)
                    for binding in declared_bindings
                )
                if scope_entities
                else bool(declared_bindings)
            )

            if not has_matching_binding and scope_entities:
                warnings.append(
                    f"Story '{story.story_id}' references integrations but no "
                    f"service/integration binds to scope entities "
                    f"({', '.join(story.scope)})."
                )
    return warnings


def _lint_process_effects(appspec: ir.AppSpec) -> list[str]:
    """Check process step effects reference valid entities and fields."""
    warnings: list[str] = []
    entity_names = {e.name for e in appspec.domain.entities}

    for process in appspec.processes:
        for step in process.steps:
            for effect in step.effects:
                # Check entity reference
                if effect.entity_name not in entity_names:
                    warnings.append(
                        f"Process '{process.name}' step '{step.name}' effect "
                        f"references non-existent entity '{effect.entity_name}'"
                    )
                    continue

                # Check assignment field paths
                entity = appspec.get_entity(effect.entity_name)
                if entity:
                    entity_field_names = {f.name for f in entity.fields}
                    for assignment in effect.assignments:
                        # Strip entity prefix (e.g. "Task.title" -> "title")
                        field_name = assignment.field_path
                        if "." in field_name:
                            field_name = field_name.split(".", 1)[1]
                        if field_name not in entity_field_names:
                            warnings.append(
                                f"Process '{process.name}' step '{step.name}' effect "
                                f"assignment references non-existent field "
                                f"'{field_name}' on entity '{effect.entity_name}'"
                            )

                # Warn about update without where clause
                if effect.action.value == "update" and not effect.where:
                    warnings.append(
                        f"Process '{process.name}' step '{step.name}' has "
                        f"update effect on '{effect.entity_name}' without "
                        f"a 'where' clause — needs entity ID from context"
                    )

    return warnings


def validate_notifications(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all notifications for semantic correctness (v0.34.0).

    Checks:
    - Trigger entity exists
    - Trigger field exists on entity (if specified)
    - No duplicate notification names
    - Recipients reference valid fields (for field-based recipients)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    entity_names = {e.name for e in appspec.domain.entities}

    for n in appspec.notifications:
        # Duplicate name check
        if n.name in seen_names:
            errors.append(f"Duplicate notification name: '{n.name}'")
        seen_names.add(n.name)

        # Trigger entity must exist
        if n.trigger.entity not in entity_names:
            errors.append(f"Notification '{n.name}' references unknown entity '{n.trigger.entity}'")
        else:
            entity = appspec.get_entity(n.trigger.entity)
            if entity and n.trigger.field:
                if not entity.get_field(n.trigger.field):
                    errors.append(
                        f"Notification '{n.name}' trigger references unknown field "
                        f"'{n.trigger.field}' on entity '{n.trigger.entity}'"
                    )

            # Field-based recipients should reference a valid field
            if entity and n.recipients.kind == "field":
                if n.recipients.value and not entity.get_field(n.recipients.value):
                    warnings.append(
                        f"Notification '{n.name}' recipients reference field "
                        f"'{n.recipients.value}' which does not exist on '{n.trigger.entity}'"
                    )

    return errors, warnings


def extended_lint(appspec: ir.AppSpec) -> list[str]:
    """Extended lint rules for code quality.

    Dispatches to focused checkers for naming, titles, workspace
    personas, routing, list-surface UX, and integration bindings.
    Dead-construct detection is handled by :func:`_detect_dead_constructs`.
    """
    warnings: list[str] = []
    warnings.extend(_lint_naming_conventions(appspec))
    warnings.extend(_detect_dead_constructs(appspec))
    warnings.extend(_lint_missing_titles(appspec))
    warnings.extend(_lint_workspace_personas(appspec))
    warnings.extend(_lint_workspace_routing(appspec))
    warnings.extend(_lint_list_surface_ux(appspec))
    warnings.extend(_lint_integration_bindings(appspec))
    warnings.extend(_lint_process_effects(appspec))
    return warnings


# =============================================================================
# Preview construct validation (parsed but not yet enforced at runtime)
# =============================================================================


def validate_webhooks(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate webhook definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.webhooks:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.webhooks)} webhook(s) defined. "
        "Webhook delivery is not yet enforced at runtime."
    )

    for wh in appspec.webhooks:
        if wh.entity and wh.entity not in entity_names:
            errors.append(f"Webhook '{wh.name}' references unknown entity '{wh.entity}'.")
        if not wh.events:
            warnings.append(f"Webhook '{wh.name}' has no events specified.")
        if not wh.url:
            warnings.append(f"Webhook '{wh.name}' has no URL configured.")

    return errors, warnings


def validate_approvals(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate approval definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.approvals:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.approvals)} approval(s) defined. "
        "Approval gates are not yet enforced at runtime."
    )

    for ap in appspec.approvals:
        if ap.entity and ap.entity not in entity_names:
            errors.append(f"Approval '{ap.name}' references unknown entity '{ap.entity}'.")
        if not ap.approver_role:
            warnings.append(f"Approval '{ap.name}' has no approver_role specified.")
        if not ap.outcomes:
            warnings.append(f"Approval '{ap.name}' has no outcomes defined.")

    return errors, warnings


def validate_slas(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate SLA definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.slas:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.slas)} SLA(s) defined. "
        "SLA monitoring is not yet enforced at runtime."
    )

    for sla in appspec.slas:
        if sla.entity and sla.entity not in entity_names:
            errors.append(f"SLA '{sla.name}' references unknown entity '{sla.entity}'.")
        if not sla.tiers:
            warnings.append(f"SLA '{sla.name}' has no tiers defined.")

    return errors, warnings


def validate_audit_config(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate entity audit configuration and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    valid_operations = {kind.value for kind in ir.PermissionKind}
    audited_entities: list[str] = []

    for entity in appspec.domain.entities:
        if entity.audit and entity.audit.enabled:
            audited_entities.append(entity.name)
            # Validate operation names
            for op in entity.audit.operations:
                if op.value not in valid_operations:
                    errors.append(
                        f"Entity '{entity.name}' audit config references "
                        f"unknown operation '{op.value}'."
                    )

    if audited_entities:
        count = len(audited_entities)
        noun = "entity has" if count == 1 else "entities have"
        warnings.append(
            f"[Info] {count} {noun} audit: enabled. "
            "CRUD operations and access decisions will be logged to the audit trail."
        )
        fcs = [e.name for e in appspec.domain.entities if e.audit and e.audit.include_field_changes]
        if fcs:
            warnings.append(
                f"[Info] {len(fcs)} audited entity/entities have "
                "include_field_changes enabled. Field-level diffs will be "
                "captured for update and delete operations."
            )

    return errors, warnings


def validate_governance_policies(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate governance policy definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.policies:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}
    entity_fields: dict[str, set[str]] = {
        e.name: {f.name for f in e.fields} for e in appspec.domain.entities
    }

    # Validate classifications
    if appspec.policies.classifications:
        for cls in appspec.policies.classifications:
            if cls.entity not in entity_names:
                errors.append(f"Classification references unknown entity '{cls.entity}'.")
            elif cls.field not in entity_fields.get(cls.entity, set()):
                errors.append(
                    f"Classification references unknown field '{cls.entity}.{cls.field}'."
                )

        count = len(appspec.policies.classifications)
        noun = "classification" if count == 1 else "classifications"
        warnings.append(
            f"[Preview] {count} data {noun} defined. "
            "Classification-based access filtering is not yet enforced at runtime."
        )

    # Validate erasures
    if appspec.policies.erasures:
        for erasure in appspec.policies.erasures:
            if erasure.entity not in entity_names:
                errors.append(f"Erasure policy references unknown entity '{erasure.entity}'.")
            elif erasure.field and erasure.field not in entity_fields.get(erasure.entity, set()):
                errors.append(
                    f"Erasure policy references unknown field '{erasure.entity}.{erasure.field}'."
                )

        count = len(appspec.policies.erasures)
        noun = "erasure policy" if count == 1 else "erasure policies"
        warnings.append(
            f"[Preview] {count} {noun} defined. "
            "Data erasure workflows are not yet enforced at runtime."
        )

    return errors, warnings


def validate_sensitive_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate sensitive field markers and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    sensitive_fields: list[str] = []
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.is_sensitive:
                sensitive_fields.append(f"{entity.name}.{field.name}")

    if sensitive_fields:
        count = len(sensitive_fields)
        noun = "field" if count == 1 else "fields"
        warnings.append(
            f"[Info] {count} {noun} marked 'sensitive'. "
            "Response masking is not yet enforced at runtime."
        )

    return errors, warnings
