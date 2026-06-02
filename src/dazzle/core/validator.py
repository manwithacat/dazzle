"""
Comprehensive semantic validation for DAZZLE AppSpec.

Validates entities, surfaces, experiences, services, foreign models, and integrations
for semantic correctness beyond basic reference resolution.
"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from . import ir
from .access import workspace_allowed_personas

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
    """Check that the entity has a primary key field.

    Subtype children (#1217 Phase 3e) MUST NOT declare their own primary key —
    the linker enforces this (E_SUBTYPE_CHILD_HAS_PK) and the DDL builder
    derives the child's id as a FK to the base's id with ON DELETE CASCADE.
    Skip the pk check for them.
    """
    if entity.subtype_of is not None:
        return
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

        # #1223 Phase 3a.v: validate latest_one field declarations.
        # Target entity must exist, declare `temporal:`, and have the
        # named FK column pointing back at this entity.
        entity_map = {e.name: e for e in appspec.domain.entities}
        for field in entity.fields:
            if field.type.kind != ir.FieldTypeKind.LATEST_ONE:
                continue
            target_name = field.type.ref_entity
            via_field = field.type.via_field
            if target_name is None or via_field is None:
                errors.append(
                    f"Entity '{entity.name}': field '{field.name}' has "
                    f"latest_one but is missing ref_entity or via_field."
                )
                continue
            target = entity_map.get(target_name)
            if target is None:
                errors.append(
                    f"Entity '{entity.name}': latest_one '{field.name}' "
                    f"references unknown entity '{target_name}'."
                )
                continue
            if target.temporal is None:
                errors.append(
                    f"Entity '{entity.name}': latest_one '{field.name}' "
                    f"targets entity '{target_name}' but '{target_name}' has no "
                    f"`temporal:` block. latest_one only works against temporal entities."
                )
            target_field_map = {f.name: f for f in target.fields}
            target_fk = target_field_map.get(via_field)
            if target_fk is None:
                errors.append(
                    f"Entity '{entity.name}': latest_one '{field.name}' "
                    f"via='{via_field}' references unknown field on '{target_name}'."
                )
            elif (
                target_fk.type.kind != ir.FieldTypeKind.REF
                or target_fk.type.ref_entity != entity.name
            ):
                errors.append(
                    f"Entity '{entity.name}': latest_one '{field.name}' "
                    f"via='{via_field}' on '{target_name}' is not a `ref {entity.name}` "
                    f"field — latest_one requires the via field to be a FK back to this entity."
                )

        # #1227 Phase 3b: validate descendants_of / ancestors_of declarations.
        # The traversal walks rows of the host entity itself, so the via
        # field must resolve to a FK whose REF target is the host entity.
        # Two via shapes:
        #   - bare `via fk_field` → fk_field is on the host entity, ref host
        #   - `via Junction.fk_field` → junction entity exists, has BOTH a
        #     FK to host (named after the dot) and a "child" FK to host
        for field in entity.fields:
            if field.type.kind not in (
                ir.FieldTypeKind.DESCENDANTS_OF,
                ir.FieldTypeKind.ANCESTORS_OF,
            ):
                continue
            kw = field.type.kind.value
            via_field = field.type.via_field
            via_entity_name = field.type.via_entity
            if via_field is None:
                errors.append(
                    f"Entity '{entity.name}': field '{field.name}' has "
                    f"{kw} but is missing via_field."
                )
                continue
            if via_entity_name is None:
                # Self-ref FK on host: must be `ref <entity.name>`
                host_field_map = {f.name: f for f in entity.fields}
                fk = host_field_map.get(via_field)
                if fk is None:
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via='{via_field}' is not a field on this entity."
                    )
                elif fk.type.kind != ir.FieldTypeKind.REF or fk.type.ref_entity != entity.name:
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via='{via_field}' is not a `ref {entity.name}` "
                        f"field — recursive traversal needs a self-referencing FK."
                    )
            else:
                # Junction-qualified path: the junction must exist and have
                # at least two FKs back to the host entity (one acting as
                # "parent", named after the dot, plus at least one other).
                junction = entity_map.get(via_entity_name)
                if junction is None:
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via='{via_entity_name}.{via_field}' references "
                        f"unknown entity '{via_entity_name}'."
                    )
                    continue
                jmap = {f.name: f for f in junction.fields}
                parent_fk = jmap.get(via_field)
                if parent_fk is None:
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via='{via_entity_name}.{via_field}' — junction "
                        f"'{via_entity_name}' has no field '{via_field}'."
                    )
                    continue
                if (
                    parent_fk.type.kind != ir.FieldTypeKind.REF
                    or parent_fk.type.ref_entity != entity.name
                ):
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via='{via_entity_name}.{via_field}' is not a "
                        f"`ref {entity.name}` field on '{via_entity_name}'."
                    )
                other_fks = [
                    f
                    for f in junction.fields
                    if f.name != via_field
                    and f.type.kind == ir.FieldTypeKind.REF
                    and f.type.ref_entity == entity.name
                ]
                if not other_fks:
                    errors.append(
                        f"Entity '{entity.name}': {kw} '{field.name}' "
                        f"via junction '{via_entity_name}' needs a second "
                        f"`ref {entity.name}` field to name the child set "
                        f"(only '{via_field}' was found)."
                    )

        # #1223 Phase 3a.i: validate temporal: block field references.
        # The named start/end/key fields must exist on the entity, and
        # end_field must NOT be `required` (NULL = currently active).
        if entity.temporal:
            field_map = {f.name: f for f in entity.fields}
            t = entity.temporal
            for slot, fname in (
                ("start_field", t.start_field),
                ("end_field", t.end_field),
                ("key_field", t.key_field),
            ):
                if fname not in field_map:
                    errors.append(
                        f"Entity '{entity.name}' temporal.{slot} = '{fname}' "
                        f"references a field that doesn't exist on the entity."
                    )
            # If both start/end exist, end must be optional (i.e. not required)
            # so the framework can use NULL as the 'currently active' sentinel.
            end_field = field_map.get(t.end_field)
            if end_field is not None and ir.FieldModifier.REQUIRED in (end_field.modifiers or []):
                errors.append(
                    f"Entity '{entity.name}' temporal.end_field = '{t.end_field}' "
                    f"must NOT be `required` — NULL is the 'currently active' "
                    f"sentinel that the framework reads."
                )

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

        # v0.45.0: Entities with permit: blocks must also have scope: blocks (#595).
        # Without scope: blocks, the API list endpoint default-denies all rows.
        # Use `scope: all as: *` for intentionally public entities (`as:`
        # renamed from `for:` in #998).
        # Skip framework-generated entities (e.g. AIJob) — users can't add scope
        # blocks to them, and their access rules are set by the framework.
        is_system = "system" in (getattr(entity, "patterns", None) or [])
        access = getattr(entity, "access", None)
        if access is not None and not is_system:
            has_permits = bool(getattr(access, "permissions", None))
            has_scopes = bool(getattr(access, "scopes", None))
            if has_permits and not has_scopes:
                warnings.append(
                    f"Entity '{entity.name}' has permit: rules but no scope: blocks — "
                    f"API list endpoint will default-deny (return 0 rows). "
                    f"Add scope: blocks or use 'scope: all as: *' for public access."
                )

    return errors, warnings


def validate_surfaces(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all surfaces for semantic correctness.

    Checks:
    - Entity references exist (already done by linker, but check fields)
    - Surface fields match entity fields when entity_ref is set
    - `source=<pack>.<op>` field options resolve to a known API pack
      (#996 — fuzz-sweep caught fieldtest_hub referencing
      `companies_house_lookup.search_companies` with no pack declared;
      runtime silently swallowed the resolution failure and the
      autocomplete just rendered as a plain text input)
    - Actions have valid outcomes
    - Modes are appropriate for the surface structure

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    # Pre-resolve API pack metadata once. The list_packs() discovery
    # walks the api-kb directory, so do it lazily and cache. Empty
    # mapping on ImportError keeps validate functional in slim
    # installs (gate self-disables — typo-detection is best-effort).
    pack_ops_cache: dict[str, set[str]] | None = None

    def _resolve_pack_ops() -> dict[str, set[str]]:
        nonlocal pack_ops_cache
        if pack_ops_cache is None:
            try:
                from dazzle.api_kb import list_packs

                pack_ops_cache = {
                    p.name: {getattr(op, "name", str(op)) for op in p.operations}
                    for p in list_packs()
                }
            except Exception:
                pack_ops_cache = {}
        return pack_ops_cache

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

        # Validate field source= references resolve to a known API pack
        # AND a known operation on that pack. #996 — typos and dropped
        # packs would fail silently at runtime; the autocomplete just
        # rendered as a plain text input.
        for section in surface.sections:
            for element in section.elements:
                source_ref = element.options.get("source") if element.options else None
                if not source_ref or "." not in source_ref:
                    continue
                pack_name, op_name = source_ref.rsplit(".", 1)
                packs = _resolve_pack_ops()
                if not packs:
                    continue  # api_kb unavailable — skip the gate
                if pack_name not in packs:
                    errors.append(
                        f"Surface '{surface.name}' field '{element.field_name}' "
                        f"references source '{source_ref}' but no API pack "
                        f"named '{pack_name}' is declared. "
                        f"Known packs: {sorted(packs)}"
                    )
                elif op_name not in packs[pack_name]:
                    errors.append(
                        f"Surface '{surface.name}' field '{element.field_name}' "
                        f"references source '{source_ref}' but operation "
                        f"'{op_name}' is not defined on pack '{pack_name}'. "
                        f"Known ops: {sorted(packs[pack_name])}"
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

        # Warn if no sections — unless the surface is intentionally headless
        # (e.g. a framework-generated API-only surface whose UI lives in a
        # client-side widget).
        if not surface.sections and not getattr(surface, "headless", False):
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
                signal.condition,
                entity,
                f"Surface '{surface.name}' attention signal",
                appspec=appspec,
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
                    appspec=appspec,
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
                        appspec=appspec,
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


def validate_persona_nav_refs(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate that each persona's `uses nav <name>` resolves (#1324).

    A persona binds a single sidebar via ``uses nav <name>`` (parsed into
    ``PersonaSpec.nav_ref``). The referenced name MUST match a declared
    top-level ``nav <name>:`` block (collected into ``AppSpec.navs``).
    An unresolved reference is a validation ERROR.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    declared_navs = {nav.name for nav in appspec.navs}
    for persona in appspec.personas:
        if persona.nav_ref is None:
            continue
        if persona.nav_ref not in declared_navs:
            errors.append(
                f"persona '{persona.id}' uses nav '{persona.nav_ref}', but no "
                f"`nav {persona.nav_ref}:` is declared"
            )

    return errors, warnings


def validate_workspace_primary_actions(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate that each workspace `primary_actions:` target resolves (#1324 FR-5).

    An authored heading-CTA action references a declared SURFACE or WORKSPACE
    by name (parsed into ``WorkspaceSpec.primary_actions``). When
    ``target_kind == "surface"`` the target MUST match a declared surface
    name (``appspec.surfaces``); when ``"workspace"``, a declared workspace
    name (``appspec.workspaces``). An unresolved target is a validation ERROR.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    declared_surfaces = {s.name for s in appspec.surfaces}
    declared_workspaces = {ws.name for ws in appspec.workspaces}

    for ws in appspec.workspaces:
        for action in ws.primary_actions:
            if action.target_kind == "surface":
                if action.target not in declared_surfaces:
                    errors.append(
                        f"workspace '{ws.name}' primary action \"{action.label}\" "
                        f"targets surface '{action.target}', but no such surface "
                        f"is declared"
                    )
            elif action.target_kind == "workspace":
                if action.target not in declared_workspaces:
                    errors.append(
                        f"workspace '{ws.name}' primary action \"{action.label}\" "
                        f"targets workspace '{action.target}', but no such workspace "
                        f"is declared"
                    )

    return errors, warnings


def validate_nav_curation(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Lint per-persona-global navigation curation (#1324 FR-6).

    All three diagnostics are WARNINGS (the errors list is always empty):

    1. **Auto-discovery reliance** — a persona with no ``uses nav`` binding
       gets an auto-discovered sidebar; warn so the author can make it
       explicit.
    2. **Dead curated nav item** — a ``nav`` lists an entity/workspace that
       NO persona bound to that nav can reach (entity: matrix LIST denied for
       all bound personas; workspace: not allowed for any bound persona), so
       the runtime access-filter drops it (dead link). Also warns when an
       item resolves to neither an entity nor a workspace, and once when a
       declared nav has no bound persona at all (then skips its item checks).
    3. **Ignored workspace nav_groups** — author-declared (non ``_``-prefixed)
       workspace ``nav_groups`` are framework-internal now and ignored for the
       author-facing sidebar.

    Returns:
        Tuple of (errors, warnings) — errors is always empty.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Diagnostic 1: auto-discovery reliance -------------------------------
    for persona in appspec.personas:
        if persona.nav_ref is None:
            warnings.append(
                f"persona '{persona.id}' has no explicit nav (uses nav) — its "
                f"sidebar is auto-discovered; bind one with `uses nav <name>` "
                f"to make navigation explicit."
            )

    # --- Diagnostic 2: dead curated nav item ---------------------------------
    # Compute the RBAC matrix once (reused exactly as the other validators do).
    matrix = None
    try:
        from dazzle.rbac.matrix import PolicyDecision, generate_access_matrix

        matrix = generate_access_matrix(appspec)
    except ImportError:
        matrix = None
    except Exception:
        # Matrix generation can fail on incomplete AppSpecs during early
        # development; degrade gracefully rather than blocking lint.
        matrix = None

    entity_names = {e.name for e in appspec.domain.entities}
    workspaces_by_name = {ws.name: ws for ws in appspec.workspaces}

    for nav in appspec.navs:
        bound = [p for p in appspec.personas if p.nav_ref == nav.name]
        if not bound:
            warnings.append(
                f"nav '{nav.name}' is not used by any persona (no `uses nav {nav.name}`)."
            )
            continue

        bound_ids = ", ".join(p.id for p in bound)
        for group in nav.groups:
            for item in group.items:
                target = item.entity
                if target in entity_names:
                    # Dead if NO bound persona can LIST the entity.
                    if matrix is not None and all(
                        matrix.get(p.effective_role, target, "list") == PolicyDecision.DENY
                        for p in bound
                    ):
                        warnings.append(
                            f"nav '{nav.name}' lists entity '{target}', but no "
                            f"persona using it ({bound_ids}) can LIST it — it "
                            f"will be filtered out (dead link)."
                        )
                elif target in workspaces_by_name:
                    ws = workspaces_by_name[target]
                    allowed = workspace_allowed_personas(ws, appspec.personas)
                    # None means "everyone allowed". Dead if no bound persona
                    # is in the allowed set.
                    if allowed is not None and not any(p.id in allowed for p in bound):
                        warnings.append(
                            f"nav '{nav.name}' lists workspace '{target}', but no "
                            f"persona using it ({bound_ids}) can reach it — it "
                            f"will be filtered out (dead link)."
                        )
                else:
                    warnings.append(
                        f"nav '{nav.name}' item '{target}' does not match any entity or workspace."
                    )

    # --- Diagnostic 3: ignored author-declared workspace nav_groups ----------
    # Discriminator: framework admin-platform workspaces are named with a
    # leading underscore (`_platform_admin`, `_tenant_admin` — built by
    # core/admin_builder._build_admin_workspaces). This is the same #824
    # reserved-name convention every other workspace lint rule uses, so reuse
    # `_is_framework_synthetic_name`. Author workspaces have no such prefix;
    # their nav_groups are framework-internal now and ignored for the sidebar.
    for ws in appspec.workspaces:
        if ws.nav_groups and not _is_framework_synthetic_name(ws.name):
            warnings.append(
                f"workspace '{ws.name}' declares nav_groups, but author-facing "
                f"navigation is per-persona now (`persona X: uses nav Y`); these "
                f"nav_groups are ignored for the sidebar. (Workspace nav_groups "
                f"are framework-internal.)"
            )

    return errors, warnings


def _validate_condition_fields(
    condition: ir.ConditionExpr,
    entity: ir.EntitySpec | None,
    context: str,
    appspec: ir.AppSpec | None = None,
) -> list[str]:
    """
    Validate that condition expression references valid entity fields.

    Supports FK traversal: ``assessment_event.department`` resolves
    ``assessment_event`` as a ref field on *entity*, then checks
    ``department`` exists on the referenced entity. Multi-hop paths
    like ``mark_scheme.subject.department`` are also supported.

    Args:
        condition: The condition expression to validate
        entity: The entity to validate fields against (may be None)
        context: Context string for error messages
        appspec: Full app spec, needed to resolve FK traversal paths

    Returns:
        List of error messages
    """
    errors: list[str] = []

    if not entity:
        return errors

    entity_field_names = {f.name for f in entity.fields}
    entity_fields_by_name = {f.name: f for f in entity.fields}

    def _resolve_fk_path(field_path: str) -> str | None:
        """Resolve a dotted FK path. Returns an error message or None if valid."""
        parts = field_path.split(".")
        current_entity = entity
        current_fields = entity_fields_by_name

        for i, part in enumerate(parts):
            if part not in current_fields:
                source = current_entity.name if current_entity else "?"
                return (
                    f"{context} references non-existent field '{field_path}' from entity '{source}'"
                )

            # If there are more segments, this part must be a ref field
            if i < len(parts) - 1:
                field_spec = current_fields[part]
                if field_spec.type.kind != ir.FieldTypeKind.REF or not field_spec.type.ref_entity:
                    return (
                        f"{context} field '{'.'.join(parts[: i + 1])}' is not a "
                        f"reference field on entity '{current_entity.name if current_entity else '?'}', "
                        f"cannot traverse to '{'.'.join(parts[i + 1 :])}'"
                    )
                if not appspec:
                    return None  # Can't resolve further without appspec; assume valid
                ref_entity = appspec.get_entity(field_spec.type.ref_entity)
                if not ref_entity:
                    return (
                        f"{context} field '{'.'.join(parts[: i + 1])}' references "
                        f"entity '{field_spec.type.ref_entity}' which does not exist"
                    )
                current_entity = ref_entity
                current_fields = {f.name: f for f in ref_entity.fields}

        return None  # Valid

    def check_comparison(comparison: ir.Comparison) -> None:
        """Validate field references in a comparison expression."""
        if comparison.field:
            if "." in comparison.field:
                err = _resolve_fk_path(comparison.field)
                if err:
                    errors.append(err)
            elif comparison.field not in entity_field_names:
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
    # Framework-synthetic platform entities (SystemMetric, SystemHealth,
    # AIJob, FeedbackReport, etc. — `domain == "platform"`) are injected by
    # the framework and may be gated off in MINIMAL security profile,
    # leaving them unreferenced by app code. They aren't dead code — they
    # come back the moment security.profile flips to STANDARD. They remain
    # in `all_entities` so surface-reachability cascades still see them,
    # but they're excluded from the dead-entity warning below.
    platform_entities = {
        e.name for e in appspec.domain.entities if getattr(e, "domain", None) == "platform"
    }
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

    unused_entities = all_entities - used_entities - platform_entities
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
    # Entities listed in nav_groups are also navigable via entity nav routes
    # (e.g. /app/trust, /app/trust/create) even without a workspace region.
    workspace_entities: set[str] = set()
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source and region.source in all_entities:
                workspace_entities.add(region.source)
            for src in region.sources:
                if src in all_entities:
                    workspace_entities.add(src)
        for nav_group in workspace.nav_groups:
            for nav_item in nav_group.items:
                if nav_item.entity in all_entities:
                    workspace_entities.add(nav_item.entity)
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


def _validate_persona_backed_by(appspec: ir.AppSpec) -> list[str]:
    """Validate ``backed_by`` / ``link_via`` on persona declarations.

    Cycle 248 (closes EX-045). When a persona declares ``backed_by: Entity``,
    the linker verifies:

    1. The named entity exists in ``appspec.domain.entities``.
    2. The entity has a field matching ``link_via`` (default ``"email"``).
    3. No two personas claim the same ``backed_by`` entity (ambiguous).

    Returns a list of error strings (not warnings — a misconfigured
    ``backed_by`` is a hard error that will break scope-rule evaluation
    at runtime if left undetected).
    """
    errors: list[str] = []
    entity_names = {e.name for e in appspec.domain.entities}
    entity_fields: dict[str, set[str]] = {}
    for e in appspec.domain.entities:
        entity_fields[e.name] = {f.name for f in e.fields}

    seen_backed: dict[str, str] = {}  # entity_name → persona_id
    for persona in appspec.personas:
        if not persona.backed_by:
            continue

        ent_name = persona.backed_by
        link_field = persona.link_via

        # Check 1: entity exists
        if ent_name not in entity_names:
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"but entity '{ent_name}' does not exist."
            )
            continue

        # Check 2: link_via field exists on the entity
        if link_field not in entity_fields.get(ent_name, set()):
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"with link_via: {link_field}, but entity '{ent_name}' "
                f"has no field named '{link_field}'."
            )

        # Check 3: no duplicate backed_by
        if ent_name in seen_backed:
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"but persona '{seen_backed[ent_name]}' already claims it. "
                f"Each entity can back at most one persona."
            )
        else:
            seen_backed[ent_name] = persona.id

    return errors


def _is_framework_synthetic_name(name: str) -> bool:
    """Reserved-name convention (#824): entries whose name begins with
    an underscore are framework-synthesised (admin workspace and its
    surfaces, internal platform constructs). Adopters can't fix lint
    warnings about them from their own DSL, so every workspace/surface
    lint rule skips these names."""
    return name.startswith("_")


def _lint_workspace_personas(appspec: ir.AppSpec) -> list[str]:
    """Check for workspaces without associated personas.

    Skips framework-synthesised workspaces (names starting with `_`)
    which are auto-generated with correct access specs; see #824.
    """
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

        # `access: persona(admin, manager)` is a first-class persona
        # binding — no need to also require a default_workspace entry
        # or ux.persona_variants block to silence this lint.
        access = getattr(workspace, "access", None)
        allow_personas = getattr(access, "allow_personas", None) if access else None
        if allow_personas:
            if any(p in persona_ids for p in allow_personas):
                workspaces_with_personas.add(workspace.name)

    for persona in appspec.personas:
        if persona.default_workspace:
            for ws in appspec.workspaces:
                if ws.name == persona.default_workspace:
                    workspaces_with_personas.add(ws.name)

    for workspace in appspec.workspaces:
        if _is_framework_synthetic_name(workspace.name):
            continue
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


def _lint_workspace_access_declarations(appspec: ir.AppSpec) -> list[str]:
    """Warn when a workspace has no access: declaration and personas are defined.

    When personas exist but a workspace carries no explicit ``access:`` block,
    all authenticated users can reach that workspace regardless of their role.
    This is almost never intentional, so we surface it as a lint warning.

    A workspace is considered *declared* if it has an explicit ``access:``
    block with at least one ``allow_personas`` entry, OR if at least one
    persona lists it as its ``default_workspace`` (in which case the runtime
    infers the restriction automatically).
    """
    if not appspec.workspaces or not appspec.personas:
        return []

    # Workspaces claimed by at least one persona's default_workspace
    claimed_by_default: set[str] = {
        p.default_workspace for p in appspec.personas if p.default_workspace
    }

    warnings: list[str] = []
    for workspace in appspec.workspaces:
        if _is_framework_synthetic_name(workspace.name):
            # Framework-synthesised workspace (#824) — auto-generated
            # with correct access spec. Adopters can't add `access:` to
            # something they don't declare, so skip this lint.
            continue
        ws_access = getattr(workspace, "access", None)
        has_explicit_access = bool(ws_access and ws_access.allow_personas)
        if not has_explicit_access and workspace.name not in claimed_by_default:
            warnings.append(
                f"Workspace '{workspace.name}' has no access: declaration and no persona "
                f"lists it as default_workspace. All authenticated users can access it. "
                f"Add 'access: allow_personas [<persona_id>]' or set default_workspace "
                f"on the relevant persona(s)."
            )
    return warnings


def _lint_list_surface_ux(appspec: ir.AppSpec) -> list[str]:
    """Check list surfaces for sort/filter/search/empty completeness.

    Skips framework-synthesised surfaces (names starting with `_`) —
    adopters can't fix missing-ux warnings on surfaces they don't
    declare. See #824.
    """
    warnings: list[str] = []
    for surface in appspec.surfaces:
        if surface.mode != ir.SurfaceMode.LIST:
            continue
        if _is_framework_synthetic_name(surface.name):
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


_INTEGRATION_KEYWORDS = frozenset(
    {
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
)


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


_GOD_ENTITY_FIELD_THRESHOLD = 15
_SOFT_DELETE_NAMES = frozenset({"is_deleted", "deleted", "deleted_at", "archived_at"})


def _lint_modeling_anti_patterns(appspec: ir.AppSpec) -> list[str]:
    """Detect common modeling anti-patterns and emit warnings."""
    warnings: list[str] = []
    entity_names = {e.name.lower() for e in appspec.domain.entities}
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        # Framework-synthetic platform entities (FeedbackReport, AIJob, etc.)
        # are code-generated and cannot be decomposed by the app author.
        # Skip modeling anti-pattern warnings on them.
        if getattr(entity, "domain", None) == "platform":
            continue
        field_map = {f.name: f for f in entity.fields}

        # 1. Polymorphic key pairs: *_type (enum) + *_id (uuid)
        for field in entity.fields:
            if field.name.endswith("_type") and field.type.kind == ir.FieldTypeKind.ENUM:
                prefix = field.name.removesuffix("_type")
                sibling_name = f"{prefix}_id"
                sibling = field_map.get(sibling_name)
                if sibling and sibling.type.kind == ir.FieldTypeKind.UUID:
                    # Diagnostic code is the first token so downstream
                    # tooling can grep by code. Alternatives ordered by
                    # cost: separate refs first (cheap, common case),
                    # subtype_of: second (heavier, only when truly IS-A).
                    warnings.append(
                        f"W_LOOKS_POLYMORPHIC: Entity '{entity.name}': fields "
                        f"'{field.name}' + '{sibling_name}' look like a "
                        f"polymorphic key pair. Prefer (in order): "
                        f"1. Separate nullable refs — `post: ref Post` + "
                        f"`photo: ref Photo` — when the set is small + closed. "
                        f"2. subtype_of: — declare a base entity + subtypes "
                        f"if these really form an IS-A hierarchy. "
                        f"Polymorphic key pairs break referential integrity "
                        f"and linker validation."
                    )

        # 1b. Subtype overreach (#1217 Phase 3e.vi): child entity declares
        # subtype_of: but adds <=1 specific field. That shape is almost
        # always cheaper as a flat entity with a discriminator enum.
        # Polymorphism is the escape hatch, not the default — see ADR-0026.
        if entity.subtype_of is not None:
            specific_count = sum(
                1
                for f in entity.fields
                if f.name != "id" and ir.FieldModifier.PK not in (f.modifiers or [])
            )
            if specific_count <= 1:
                warnings.append(
                    f"W_SUBTYPE_OF_OVERREACH: Entity '{entity.name}' subtypes "
                    f"'{entity.subtype_of}' but only adds {specific_count} "
                    f"field(s). Consider modelling as a flat entity with a "
                    f"discriminator enum instead."
                )

        # 2. God entities: too many fields
        meaningful_fields = [
            f
            for f in entity.fields
            if f.name not in ("id", "created_at", "updated_at")
            and ir.FieldModifier.PK not in (f.modifiers or [])
        ]
        if len(meaningful_fields) > _GOD_ENTITY_FIELD_THRESHOLD:
            warnings.append(
                f"Entity '{entity.name}' has {len(meaningful_fields)} fields "
                f"— consider decomposing into smaller entities connected by refs."
            )

        # 3. Soft-delete flags without state machine
        if entity.state_machine is None:
            for field in entity.fields:
                if field.name in _SOFT_DELETE_NAMES:
                    warnings.append(
                        f"Entity '{entity.name}': field '{field.name}' is a soft-delete "
                        f"flag. Prefer a state machine with a terminal state "
                        f"(e.g., 'archived')."
                    )

        # 4. Stringly-typed refs: <entity>_name or <entity>_email
        for field in entity.fields:
            if field.type.kind not in (ir.FieldTypeKind.STR, ir.FieldTypeKind.EMAIL):
                continue
            for suffix in ("_name", "_email"):
                if field.name.endswith(suffix):
                    prefix = field.name.removesuffix(suffix)
                    if prefix.lower() in entity_names and prefix.lower() != entity.name.lower():
                        target = next(
                            (
                                e.name
                                for e in appspec.domain.entities
                                if e.name.lower() == prefix.lower()
                            ),
                            prefix,
                        )
                        warnings.append(
                            f"Entity '{entity.name}': field '{field.name}' looks like "
                            f"a string copy of {target}.{suffix.lstrip('_')}. "
                            f"Use 'ref {target}' instead — the runtime auto-includes related data."
                        )

        # 5. Duplicated ref fields: ref X + x_<field> where <field> exists on X
        for field in entity.fields:
            if field.type.kind != ir.FieldTypeKind.REF or not field.type.ref_entity:
                continue
            target_entity = entity_map.get(field.type.ref_entity)
            if target_entity is None:
                continue  # ref target not found — skip silently
            target_field_names = {f.name for f in target_entity.fields if f.name != "id"}
            ref_lower = field.name.lower()
            for sibling in entity.fields:
                if sibling is field:
                    continue
                if sibling.name.startswith(f"{ref_lower}_"):
                    attr = sibling.name[len(ref_lower) + 1 :]
                    if attr in target_field_names:
                        warnings.append(
                            f"Entity '{entity.name}': field '{sibling.name}' may "
                            f"duplicate {field.type.ref_entity}.{attr} — the ref "
                            f"already provides access via auto-include."
                        )

    return warnings


_GRAPH_EDGE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "source",
        "target",
        "from",
        "to",
        "parent",
        "child",
        "start",
        "end",
        "predecessor",
        "successor",
    }
)

# Audit-metadata token vocabulary (#823). A field that contains any of
# these tokens is almost always a who-did-what audit record — NOT a
# graph-edge endpoint. Fields with BOTH an edge token AND an audit token
# (e.g. `assigned_to`, `reported_from`) are resolved as audit fields and
# excluded from edge candidacy. This catches the false-positive class
# observed by AegisMark where mixed-vocabulary field names — and in
# particular `assigned_to`, `sent_to`, `returned_from` — were flagged as
# graph edges despite being workflow/routing metadata.
_AUDIT_METADATA_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "created",
        "updated",
        "deleted",
        "modified",
        "reviewed",
        "reported",
        "approved",
        "rejected",
        "closed",
        "assigned",
        "reopened",
        "sent",
        "returned",
        "archived",
        "published",
        "signed",
        "acknowledged",
    }
)


def _lint_graph_edge_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_edge: for entities that pair two graph-edge-shaped refs
    to the same target entity.

    Entities with creator + assignee / requester + approver / parent + owner
    are NOT graph edges — those are domain fields that happen to share a
    ref target. Only flag when the field names match the graph-edge
    vocabulary (source/target, from/to, parent/child, ...) AND do not
    overlap with the audit-metadata vocabulary (created, updated, assigned,
    reported, ...) — fields like `assigned_to` that have both an edge token
    and an audit token resolve as audit metadata and are excluded (#823).
    """
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            continue
        # Group ref fields by target entity, and remember which fields
        # landed under each target.
        ref_fields_by_target: dict[str, list[str]] = {}
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                ref_fields_by_target.setdefault(field.type.ref_entity, []).append(field.name)
        for target, field_names in ref_fields_by_target.items():
            if len(field_names) < 2:
                continue

            # A field matches the graph-edge vocabulary if any of its
            # underscore-delimited tokens is a recognised edge term
            # (source_node, target_id, from_station, parent_node, ...)
            # AND none of its tokens is an audit-metadata term (#823:
            # `assigned_to`, `sent_to`, `reported_from` all resolve as
            # audit fields despite carrying an edge token).
            def _is_edge_field(name: str) -> bool:
                tokens = name.lower().split("_")
                has_edge = any(tok in _GRAPH_EDGE_FIELD_NAMES for tok in tokens)
                has_audit = any(tok in _AUDIT_METADATA_FIELD_NAMES for tok in tokens)
                return has_edge and not has_audit

            matches = [n for n in field_names if _is_edge_field(n)]
            if len(matches) >= 2:
                warnings.append(
                    f"Entity '{entity.name}' looks like a graph edge — "
                    f"has {len(field_names)} ref fields to '{target}' "
                    f"({', '.join(sorted(field_names))}). "
                    f"Consider adding graph_edge:"
                )
                break
    return warnings


def _lint_graph_node_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_node: for entities targeted by graph_edge: declarations."""
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}
    # Track which entities we've already warned about
    warned: set[str] = set()
    for entity in appspec.domain.entities:
        if entity.graph_edge is None:
            continue
        field_map = {f.name: f for f in entity.fields}
        for field_name in (entity.graph_edge.source, entity.graph_edge.target):
            field = field_map.get(field_name)
            if field and field.type.ref_entity:
                target_ent = entity_map.get(field.type.ref_entity)
                if target_ent and target_ent.graph_node is None and target_ent.name not in warned:
                    warnings.append(
                        f"'{entity.name}' targets '{target_ent.name}' — "
                        f"consider adding graph_node: for discoverability"
                    )
                    warned.add(target_ent.name)
    return warnings


def _lint_fk_targets_missing_display_field(appspec: ir.AppSpec) -> list[str]:
    """Warn when FK-target entities lack display_field (#652).

    Entities referenced by ``ref`` fields on other entities should declare
    ``display_field:`` so that FK references render as human-readable text
    instead of raw UUIDs. Junction entities (2+ required ref fields, no
    str/text fields) are skipped since they rarely have a meaningful name.
    """
    warnings: list[str] = []
    entities_by_name: dict[str, ir.EntitySpec] = {e.name: e for e in appspec.domain.entities}

    # Build map: entity_name → list of "Entity.field" references
    fk_refs: dict[str, list[str]] = {}
    for entity in appspec.domain.entities:
        for field in entity.fields:
            kind = getattr(field.type, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind)  # type: ignore[union-attr]
            ref_target = getattr(field.type, "ref_entity", None)
            if kind_val in ("ref", "belongs_to") and ref_target:
                fk_refs.setdefault(ref_target, []).append(f"{entity.name}.{field.name}")

    for target_name, refs in sorted(fk_refs.items()):
        target = entities_by_name.get(target_name)
        if target is None:
            continue
        if target.display_field:
            continue

        # Skip junction entities: 2+ required ref fields, no str/text fields
        ref_count = 0
        has_text_field = False
        for f in target.fields:
            fk = getattr(f.type, "kind", None)
            fk_val = fk.value if hasattr(fk, "value") else str(fk)  # type: ignore[union-attr]
            if fk_val in ("ref", "belongs_to") and f.is_required:
                ref_count += 1
            scalar = getattr(f.type, "scalar_type", None)
            if scalar and str(scalar) in ("str", "text", "ScalarType.STR", "ScalarType.TEXT"):
                has_text_field = True
        if ref_count >= 2 and not has_text_field:
            continue

        # Suggest a candidate field
        candidate = None
        for name in ("name", "title", "label"):
            if any(f.name == name for f in target.fields):
                candidate = name
                break
        if candidate is None:
            for f in target.fields:
                scalar = getattr(f.type, "scalar_type", None)
                if scalar and str(scalar) in ("str", "ScalarType.STR"):
                    candidate = f.name
                    break

        ref_list = ", ".join(refs[:5])
        if len(refs) > 5:
            ref_list += f", ... ({len(refs)} total)"
        msg = (
            f"Entity '{target_name}' is referenced as FK by {len(refs)} field(s) "
            f"but has no display_field."
        )
        if candidate:
            msg += f"\n  Suggested: display_field: {candidate}"
        msg += f"\n  FK references: {ref_list}"
        warnings.append(msg)

    return warnings


def _lint_nav_group_icon_consistency(appspec: ir.AppSpec) -> list[str]:
    """Warn when a nav_group mixes items with and without `icon:`.

    A nav_group with some items that declare `icon:` and some that don't
    renders as a visually inconsistent list — iconed items have a flush
    icon + label, iconless items have a blank gutter where the icon
    would be. Pick one: either every item in the group carries an
    icon, or none do. Asked for in issue #796.
    """
    warnings: list[str] = []
    for workspace in appspec.workspaces:
        for group in workspace.nav_groups:
            if not group.items:
                continue
            iconed = [it for it in group.items if it.icon]
            iconless = [it for it in group.items if not it.icon]
            if iconed and iconless:
                iconless_names = ", ".join(it.entity for it in iconless)
                warnings.append(
                    f"Workspace '{workspace.name}' nav_group '{group.label}' "
                    f"mixes iconed and iconless items — {iconless_names} "
                    f"have no icon while siblings do. Add `icon:` to all items "
                    f"in the group, or remove it from all, for consistent "
                    f"sidebar alignment."
                )
    return warnings


def validate_workspace_region_actions(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Error when a region `action:` on a cross-entity surface has no valid FK path (#861).

    When a region sourced from entity A declares `action: some_surface` and
    `some_surface` is bound to a different entity B, the runtime looks for a
    single FK field on A that references B to thread the row ID through to
    the action URL. If zero or multiple FK candidates exist, the action URL
    silently misfires at runtime. Flag both conditions at validate time.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not appspec.workspaces:
        return errors, warnings

    surfaces_by_name: dict[str, ir.SurfaceSpec] = {s.name: s for s in appspec.surfaces}
    entities_by_name: dict[str, ir.EntitySpec] = {e.name: e for e in appspec.domain.entities}

    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.action or not region.source:
                continue
            action_surface = surfaces_by_name.get(region.action)
            if action_surface is None:
                continue  # unknown surface is caught elsewhere
            target_entity = action_surface.entity_ref
            if not target_entity or target_entity == region.source:
                continue  # same-entity action — no FK needed
            source_entity = entities_by_name.get(region.source)
            if source_entity is None:
                continue  # region sourced from a surface, not an entity
            fk_candidates: list[str] = []
            for f in source_entity.fields:
                kind = getattr(f.type, "kind", None)
                kind_val = kind.value if hasattr(kind, "value") else str(kind)  # type: ignore[union-attr]
                if kind_val in ("ref", "belongs_to"):
                    ref_target = getattr(f.type, "ref_entity", None)
                    if ref_target == target_entity:
                        fk_candidates.append(f.name)
            if len(fk_candidates) == 0:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name}' declares "
                    f"`action: {region.action}` targeting entity '{target_entity}', "
                    f"but source entity '{region.source}' has no FK field referencing "
                    f"'{target_entity}'. Add a `ref {target_entity}` field or change "
                    f"the action to a surface on '{region.source}'."
                )
            elif len(fk_candidates) > 1:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name}' declares "
                    f"`action: {region.action}` targeting entity '{target_entity}', "
                    f"but source entity '{region.source}' has multiple FK fields "
                    f"referencing '{target_entity}' ({', '.join(fk_candidates)}). "
                    f"Ambiguous FK — the runtime cannot pick one automatically."
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
    warnings.extend(_validate_persona_backed_by(appspec))
    warnings.extend(_lint_workspace_personas(appspec))
    warnings.extend(_lint_workspace_routing(appspec))
    warnings.extend(_lint_workspace_access_declarations(appspec))
    warnings.extend(_lint_list_surface_ux(appspec))
    warnings.extend(_lint_nav_group_icon_consistency(appspec))
    warnings.extend(_lint_integration_bindings(appspec))
    warnings.extend(_lint_process_effects(appspec))
    warnings.extend(_lint_modeling_anti_patterns(appspec))
    warnings.extend(_lint_graph_edge_suggestions(appspec))
    warnings.extend(_lint_graph_node_suggestions(appspec))
    warnings.extend(_lint_fk_targets_missing_display_field(appspec))
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


def validate_atomic_flows(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate atomic-flow declarations (#1228 Phase 3c).

    Checks that each flow:
      - has at least one create
      - has unique input names
      - has unique entity targets across creates (one create per entity in MVP)
      - every create targets a known entity
      - every assignment field exists on the target entity
      - every ``input.X`` reference names a declared input
      - every ``above.E.F`` reference points at an entity created earlier
        in this flow (no forward refs) and the field is ``id`` (the only
        always-derivable field at this slice)
      - permit_execute is non-empty
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.atomic_flows:
        return errors, warnings

    warnings.append(
        f"[Preview] {len(appspec.atomic_flows)} atomic flow(s) defined. "
        "`create` + `update` steps execute in a single transaction with per-step "
        "scope enforcement (#1313, ADR-0029). Pending: in-transaction audit + "
        "matrix/conformance/specs visibility."
    )

    entity_map = {e.name: e for e in appspec.domain.entities}

    for flow in appspec.atomic_flows:
        prefix = f"atomic flow '{flow.name}'"

        if not flow.steps:
            errors.append(f"{prefix}: must declare at least one `create` or `update` step.")
        if not flow.permit_execute:
            errors.append(f"{prefix}: must declare `permit: execute: role(...)`.")

        # Input uniqueness
        input_names: set[str] = set()
        for inp in flow.inputs:
            if inp.name in input_names:
                errors.append(f"{prefix}: duplicate input '{inp.name}'.")
            input_names.add(inp.name)

        # Track entities created so far (left-to-right) for above-ref validation.
        seen_entities: set[str] = set()

        def _check_ref(
            value: ir.FlowFieldValue,
            ctx: str,
            _seen: set[str],
            _prefix: str,
            _inputs: set[str],
        ) -> None:
            """Validate an input/above reference inside a step.

            ``_prefix`` / ``_inputs`` are passed explicitly (not closed over)
            so the helper doesn't bind the enclosing loop variables.
            """
            if value.kind == ir.FlowFieldValueKind.INPUT_REF:
                if value.input_name not in _inputs:
                    errors.append(
                        f"{_prefix}: {ctx} references undeclared input '{value.input_name}'."
                    )
            elif value.kind == ir.FlowFieldValueKind.ABOVE_REF:
                if value.above_entity not in _seen:
                    errors.append(
                        f"{_prefix}: {ctx} references above.{value.above_entity}."
                        f"{value.above_field} but '{value.above_entity}' is not "
                        f"created earlier in this flow."
                    )
                if value.above_field != "id":
                    errors.append(
                        f"{_prefix}: {ctx} uses above.{value.above_entity}."
                        f"{value.above_field}; only '.id' is supported in this release."
                    )

        # #1315 — validate `above`-ref resolution against the EXECUTION order
        # (the FK-derived order when set, else declared). A create-DAG the author
        # wrote out-of-order is reordered parent-before-child by the linker, so
        # its forward `above`-refs are legal; a flow with no derived order is
        # checked in declared order (an `above`-ref to a not-yet-created entity
        # is still an error there).
        if flow.derived_step_order is not None:
            ordered_steps = [flow.steps[i] for i in flow.derived_step_order]
        else:
            ordered_steps = list(flow.steps)
        for step in ordered_steps:
            is_update = isinstance(step, ir.FlowUpdate)
            kind = "update" if is_update else "create"

            # One create per entity per flow (MVP). Updates may target an
            # entity freely (incl. one a create also touches), so they are
            # exempt from the uniqueness check.
            if not is_update and step.entity in seen_entities:
                errors.append(
                    f"{prefix}: create target '{step.entity}' appears more than once "
                    f"(one create per entity per flow in this release)."
                )

            target = entity_map.get(step.entity)
            if target is None:
                errors.append(f"{prefix}: {kind} targets unknown entity '{step.entity}'.")
                if not is_update:
                    seen_entities.add(step.entity)
                continue

            # An update's target row-selector must resolve to an existing row.
            # (Direct isinstance so the type-checker narrows `step` to FlowUpdate.)
            if isinstance(step, ir.FlowUpdate):
                _check_ref(
                    step.target, f"update {step.entity} target", seen_entities, prefix, input_names
                )

            target_fields = {f.name for f in target.fields}
            for field_name, value in step.assignments.items():
                if field_name not in target_fields:
                    errors.append(
                        f"{prefix}: {kind} {step.entity} assigns to unknown field '{field_name}'."
                    )
                _check_ref(
                    value, f"{kind} {step.entity}.{field_name}", seen_entities, prefix, input_names
                )

            if not is_update:
                seen_entities.add(step.entity)

        # #1318 / ADR-0031 — flow-level aggregate invariants. Each invariant
        # asserts `<agg_fn>(<entity>.<field> where <filter>) <op> <rhs>` at
        # commit; here we statically check its references resolve and that it
        # names a lockable anchor row.
        _NUMERIC_KINDS = {
            ir.FieldTypeKind.INT,
            ir.FieldTypeKind.FLOAT,
            ir.FieldTypeKind.DECIMAL,
            ir.FieldTypeKind.MONEY,
        }
        for inv in flow.invariants:
            inv_prefix = f"{prefix}: invariant {inv.agg_fn}({inv.entity}...)"

            target = entity_map.get(inv.entity)
            if target is None:
                errors.append(f"{inv_prefix}: unknown entity '{inv.entity}'.")
                continue

            target_field_map = {f.name: f for f in target.fields}

            # sum requires an existing numeric field; count takes no field.
            if inv.agg_fn == ir.FlowAggregateFn.SUM:
                fld = target_field_map.get(inv.field) if inv.field else None
                if fld is None:
                    errors.append(
                        f"{inv_prefix}: sum field '{inv.field}' does not exist on '{inv.entity}'."
                    )
                elif fld.type.kind not in _NUMERIC_KINDS:
                    errors.append(
                        f"{inv_prefix}: sum field '{inv.field}' on '{inv.entity}' is "
                        f"not numeric (got {fld.type.kind})."
                    )

            # The load-bearing rejection: an aggregate with no lockable anchor.
            if inv.anchor_entity is None or inv.anchor_input is None:
                errors.append(
                    f"{inv_prefix}: unanchored aggregate invariant: needs a "
                    f"`<fk> = input.<name>` filter term naming a lockable anchor "
                    f"row (see ADR-0031)."
                )
            elif inv.anchor_input not in input_names:
                errors.append(
                    f"{inv_prefix}: anchor references undeclared input '{inv.anchor_input}'."
                )

            # Filter columns must exist on the target entity (allow the `_id`
            # FK-suffix spelling, matching the column-naming convention).
            for column, _kind, _value in inv.raw_filter:
                if column not in target_field_map and (column + "_id") not in target_field_map:
                    errors.append(
                        f"{inv_prefix}: filter references unknown column '{column}' "
                        f"on '{inv.entity}'."
                    )

            # RHS: literal needs no check; the field form must resolve to a
            # numeric field on the named input's referenced entity.
            rhs = inv.rhs
            if rhs.anchor_input is not None:
                rhs_input = next((i for i in flow.inputs if i.name == rhs.anchor_input), None)
                if rhs_input is None:
                    errors.append(
                        f"{inv_prefix}: RHS references undeclared input '{rhs.anchor_input}'."
                    )
                else:
                    rhs_entity_name = rhs_input.type.ref_entity
                    rhs_entity = entity_map.get(rhs_entity_name) if rhs_entity_name else None
                    if rhs_entity is None:
                        errors.append(
                            f"{inv_prefix}: RHS input '{rhs.anchor_input}' does not "
                            f"reference a known entity."
                        )
                    else:
                        rhs_field_map = {f.name: f for f in rhs_entity.fields}
                        rhs_field = (
                            rhs_field_map.get(rhs.anchor_field) if rhs.anchor_field else None
                        )
                        if rhs_field is None:
                            errors.append(
                                f"{inv_prefix}: RHS field '{rhs.anchor_field}' does not "
                                f"exist on '{rhs_entity.name}'."
                            )
                        elif rhs_field.type.kind not in _NUMERIC_KINDS:
                            errors.append(
                                f"{inv_prefix}: RHS field '{rhs.anchor_field}' on "
                                f"'{rhs_entity.name}' is not numeric "
                                f"(got {rhs_field.type.kind})."
                            )
            elif rhs.literal is None:
                errors.append(f"{inv_prefix}: invariant RHS is empty.")

    return errors, warnings


def validate_transition_invocations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate transition ``invoke <flow>(...)`` cross-references (#1319, ADR-0032).

    Slice A surface checks (the shared-transaction runtime wiring is Slice B):

    - the invoked flow exists in ``appspec.atomic_flows``;
    - every binding names a real input of that flow;
    - every *required* flow input is bound;
    - a ``self`` binding targets a flow input that is a ``ref`` to the entity that
      owns the state machine (a light shape check — the transitioning row is what
      ``self`` resolves to).
    """
    errors: list[str] = []
    warnings: list[str] = []

    flows_by_name = {f.name: f for f in (appspec.atomic_flows or [])}

    for entity in appspec.domain.entities or []:
        sm = entity.state_machine
        if sm is None:
            continue
        for t in sm.transitions:
            inv = t.invoke_flow
            if inv is None:
                continue
            prefix = (
                f"entity '{entity.name}' transition {t.from_state} -> {t.to_state}: "
                f"invoke {inv.flow_name}"
            )
            # v1 limit (ADR-0032 Slice B): the shared-tx path reads the row back on
            # the flow connection with a plain SELECT, which does not reproduce the
            # soft-delete / temporal / subtype-JOIN logic the normal read applies.
            # Reject invoke on those entity types until the shared read handles them.
            if getattr(entity, "soft_delete", None) or getattr(entity, "temporal", None):
                errors.append(
                    f"{prefix} on a soft-delete/temporal entity is not supported in this "
                    "release (transition invoke is v1-limited to plain entities)."
                )
            if getattr(entity, "subtype_of", None) or getattr(entity, "subtypes", None):
                errors.append(
                    f"{prefix} on a subtype-polymorphic entity is not supported in this "
                    "release (transition invoke is v1-limited to plain entities)."
                )
            # A guarded effect needs a principal; an `auto` (scheduled/system)
            # transition has none, so reject `invoke` on it at validate time
            # (ADR-0032 — the service-principal story for system transitions is
            # deferred). A manual (user-triggered) transition carries the PUT caller.
            if t.trigger == ir.TransitionTrigger.AUTO:
                errors.append(
                    f"{prefix} on an `auto` transition: a transition-invoked atomic flow "
                    "needs an authenticated principal, which an auto/scheduled transition "
                    "lacks (ADR-0032 — use a manual transition)."
                )
            flow = flows_by_name.get(inv.flow_name)
            if flow is None:
                errors.append(f"{prefix} references unknown atomic flow '{inv.flow_name}'.")
                continue

            flow_inputs = {fi.name: fi for fi in flow.inputs}
            bound = {b.flow_input for b in inv.bindings}

            for b in inv.bindings:
                if b.flow_input not in flow_inputs:
                    errors.append(
                        f"{prefix} binds unknown input '{b.flow_input}' "
                        f"(flow '{inv.flow_name}' has {sorted(flow_inputs)})."
                    )
                elif b.source_kind == ir.InvokeSourceKind.SELF:
                    # `self` is the transitioning row → the bound input should be a
                    # ref to this entity.
                    fi = flow_inputs[b.flow_input]
                    ref_entity = getattr(fi.type, "ref_entity", None)
                    if ref_entity is not None and ref_entity != entity.name:
                        errors.append(
                            f"{prefix} binds `self` to input '{b.flow_input}', which is a "
                            f"ref {ref_entity}, not ref {entity.name} (the transitioning entity)."
                        )
                elif b.source_kind == ir.InvokeSourceKind.INPUT and not b.source_name:
                    # An `input.<name>` binding must carry the transition input name
                    # (the runtime resolves the value from it in Slice B).
                    errors.append(
                        f"{prefix} binds input '{b.flow_input}' from a transition input "
                        "but names no source (expected `input.<name>`)."
                    )

            for name, fi in flow_inputs.items():
                if fi.required and name not in bound:
                    errors.append(f"{prefix} does not bind required input '{name}'.")

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


_VISIBILITY_BOOL_FIELD_NAMES = frozenset(
    {"is_internal", "is_private", "internal_only", "internal", "private"}
)


def _condition_field_references(condition: Any) -> set[str]:
    """Collect every entity field name referenced by a ConditionExpr tree.

    Walks Comparison.field plus FunctionCall.argument on leaves and
    recurses through compound `left`/`right` branches.
    """
    if condition is None:
        return set()
    refs: set[str] = set()
    comparison = getattr(condition, "comparison", None)
    if comparison is not None:
        if comparison.field:
            refs.add(comparison.field)
        if comparison.function and comparison.function.argument:
            refs.add(comparison.function.argument)
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None:
        refs.update(_condition_field_references(left))
    if right is not None:
        refs.update(_condition_field_references(right))
    return refs


def validate_visibility_bool_field_scope_coverage(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when an entity has a likely-visibility bool field but no scope filter.

    An entity carrying a bool field named `is_internal`, `is_private`,
    `internal_only`, etc. is signalling intent that some rows should be
    invisible to certain personas. If the entity is exposed to multiple
    personas via an unfiltered `all` scope (condition=None) and no scope
    rule references that field's name, the field is decoration — rows
    leak across personas regardless of its value.

    Caught by /fuzz on examples/support_tickets where Comment.is_internal
    was leaking to the `customer` persona (#1062).
    """
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue

        bool_visibility_fields = [
            f.name
            for f in entity.fields
            if f.name in _VISIBILITY_BOOL_FIELD_NAMES and f.type.kind == ir.FieldTypeKind.BOOL
        ]
        if not bool_visibility_fields:
            continue

        # Collect every persona named by any scope rule on this entity.
        all_personas: set[str] = set()
        for rule in entity.access.scopes:
            all_personas.update(rule.personas)

        if len(all_personas) < 2:
            # Single-persona exposure: no leak surface.
            continue

        referenced_fields: set[str] = set()
        for rule in entity.access.scopes:
            referenced_fields.update(_condition_field_references(rule.condition))

        unreferenced = [name for name in bool_visibility_fields if name not in referenced_fields]
        if not unreferenced:
            continue

        for field_name in unreferenced:
            warnings.append(
                f"Entity '{entity.name}': bool field '{field_name}' looks "
                f"like a visibility gate but no scope rule references it — "
                f"all {len(all_personas)} personas ({', '.join(sorted(all_personas))}) "
                f"see rows regardless of '{field_name}' value. Add a "
                f"`scope: list: {field_name} = false as: <persona>` rule "
                f"or rename the field if visibility wasn't the intent."
            )

    return errors, warnings


def validate_scope_predicates(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate scope predicates against the FK graph (belt-and-suspenders).

    The linker already compiles scope predicates and catches many errors during
    ``build_scope_predicate``.  This validator provides a second layer that
    walks the *compiled* predicate trees and verifies:

    - ColumnCheck.field exists on the entity
    - PathCheck.path resolves through the FK graph
    - ExistsCheck.target_entity exists
    - No role/grant checks leak into scope rules (already blocked by the
      predicate builder, but verified here for defense-in-depth)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    fk_graph = appspec.fk_graph
    if fk_graph is None:
        return errors, warnings

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue

        entity_field_names = {f.name for f in entity.fields}

        for rule in entity.access.scopes:
            predicate = rule.predicate
            if predicate is None:
                continue

            ctx = f"Entity '{entity.name}' scope rule"
            _validate_predicate_node(
                predicate,
                entity.name,
                entity_field_names,
                fk_graph,
                appspec,
                ctx,
                errors,
                warnings,
            )

    return errors, warnings


def _validate_predicate_node(
    node: object,
    entity_name: str,
    entity_field_names: set[str],
    fk_graph: Any,
    appspec: ir.AppSpec,
    ctx: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Recursively validate a single predicate node against the FK graph."""
    # Import here to avoid circular imports at module level
    from .ir.predicates import (
        BoolComposite,
        ColumnCheck,
        Contradiction,
        ExistsCheck,
        PathCheck,
        Tautology,
        UserAttrCheck,
    )

    if isinstance(node, (Tautology, Contradiction)):
        return

    if isinstance(node, ColumnCheck):
        if node.field not in entity_field_names:
            errors.append(
                f"{ctx}: ColumnCheck references non-existent field "
                f"'{node.field}' on entity '{entity_name}'"
            )
        return

    if isinstance(node, UserAttrCheck):
        if node.field not in entity_field_names:
            errors.append(
                f"{ctx}: UserAttrCheck references non-existent field "
                f"'{node.field}' on entity '{entity_name}'"
            )
        return

    if isinstance(node, PathCheck):
        if not node.path:
            errors.append(f"{ctx}: PathCheck has empty path")
            return
        # Validate FK hops for all segments except the last, then check
        # the terminal field exists on the final entity.
        path_str = ".".join(node.path)
        current = entity_name
        for i, segment in enumerate(node.path):
            is_last = i == len(node.path) - 1
            if is_last:
                # Terminal segment: must be a plain field on current entity
                if not fk_graph.field_exists(current, segment):
                    errors.append(
                        f"{ctx}: PathCheck path '{path_str}' — terminal field "
                        f"'{segment}' does not exist on entity '{current}'"
                    )
            else:
                # Intermediate segment: must be an FK hop
                try:
                    _, target = fk_graph.resolve_segment(current, segment)
                    current = target
                except (ValueError, AttributeError) as exc:
                    errors.append(f"{ctx}: PathCheck path '{path_str}' — {exc}")
                    break  # Cannot continue resolving after a broken hop
        return

    if isinstance(node, ExistsCheck):
        if not appspec.get_entity(node.target_entity):
            errors.append(
                f"{ctx}: ExistsCheck references non-existent entity '{node.target_entity}'"
            )
            return
        # Dotted junction-field paths (#858): walk segments through the FK
        # graph starting from the junction. All but the last must resolve
        # as FK hops; the last is a column on the tail entity.
        for binding in node.bindings:
            if "." not in binding.junction_field:
                continue
            segments = binding.junction_field.split(".")
            current = node.target_entity
            for i, segment in enumerate(segments):
                is_last = i == len(segments) - 1
                if is_last:
                    if not fk_graph.field_exists(current, segment):
                        errors.append(
                            f"{ctx}: via binding '{binding.junction_field}' — "
                            f"terminal field '{segment}' does not exist on '{current}'"
                        )
                else:
                    try:
                        _, target = fk_graph.resolve_segment(current, segment)
                        current = target
                    except (ValueError, AttributeError) as exc:
                        errors.append(f"{ctx}: via binding '{binding.junction_field}' — {exc}")
                        break
        return

    if isinstance(node, BoolComposite):
        for child in node.children:
            _validate_predicate_node(
                child,
                entity_name,
                entity_field_names,
                fk_graph,
                appspec,
                ctx,
                errors,
                warnings,
            )
        return


# =============================================================================
# Graph semantics validation (v0.46.0 — #619)
# =============================================================================

# Numeric field types for graph weight validation
_NUMERIC_FIELD_TYPES = frozenset(
    {
        ir.FieldTypeKind.INT,
        ir.FieldTypeKind.DECIMAL,
        ir.FieldTypeKind.FLOAT,
    }
)


def validate_graph_declarations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate graph_edge: and graph_node: declarations.

    Checks field references, types, and cross-entity consistency.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            _validate_graph_edge(entity, entity_map, errors, warnings)
        if entity.graph_node is not None:
            _validate_graph_node(entity, entity_map, errors, warnings)

    return errors, warnings


def _validate_graph_edge(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_edge: block."""
    ge = entity.graph_edge
    assert ge is not None
    field_map = {f.name: f for f in entity.fields}

    # source field
    if ge.source not in field_map:
        errors.append(f"graph_edge source '{ge.source}' is not a field on {entity.name}")
    else:
        src_field = field_map[ge.source]
        if src_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge source must be a ref field, got '{src_field.type.kind.value}'"
            )

    # target field
    if ge.target not in field_map:
        errors.append(f"graph_edge target '{ge.target}' is not a field on {entity.name}")
    else:
        tgt_field = field_map[ge.target]
        if tgt_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge target must be a ref field, got '{tgt_field.type.kind.value}'"
            )

    # type_field (optional)
    if ge.type_field is not None:
        if ge.type_field not in field_map:
            errors.append(f"graph_edge type '{ge.type_field}' is not a field on {entity.name}")

    # weight_field (optional)
    if ge.weight_field is not None:
        if ge.weight_field not in field_map:
            errors.append(f"graph_edge weight '{ge.weight_field}' is not a field on {entity.name}")
        else:
            wf = field_map[ge.weight_field]
            if wf.type.kind not in _NUMERIC_FIELD_TYPES:
                errors.append("graph_edge weight must be int, decimal, or float")

    # Warnings: heterogeneous graph
    if ge.source in field_map and ge.target in field_map:
        src_ref = field_map[ge.source].type.ref_entity
        tgt_ref = field_map[ge.target].type.ref_entity
        if src_ref and tgt_ref and src_ref != tgt_ref:
            warnings.append(f"Heterogeneous graph: source refs {src_ref}, target refs {tgt_ref}")

    # Warning: no access control on edge entity
    if entity.access is None or not entity.access.permissions:
        warnings.append(f"Edge entity '{entity.name}' has no access control")

    # Warning: acyclic only detectable in seed data
    if ge.acyclic:
        warnings.append("acyclic declared but cycles only detected in seed data")


def _validate_graph_node(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_node: block."""
    gn = entity.graph_node
    assert gn is not None

    if gn.edge_entity not in entity_map:
        errors.append(f"graph_node edges '{gn.edge_entity}' is not a defined entity")
    else:
        edge_ent = entity_map[gn.edge_entity]
        if edge_ent.graph_edge is None:
            errors.append(f"graph_node edges '{gn.edge_entity}' does not declare graph_edge:")

    field_map = {f.name: f for f in entity.fields}
    if gn.display is not None:
        if gn.display not in field_map:
            errors.append(f"graph_node display '{gn.display}' is not a field on {entity.name}")
    else:
        warnings.append("graph_node has no display field — labels use default fallback")

    # parent_field must reference a real ref field (#781)
    if gn.parent_field is not None:
        parent_spec = field_map.get(gn.parent_field)
        if parent_spec is None:
            errors.append(f"graph_node parent '{gn.parent_field}' is not a field on {entity.name}")
        elif (
            parent_spec.type.kind.value not in ("ref", "belongs_to")
            or not parent_spec.type.ref_entity
        ):
            errors.append(
                f"graph_node parent '{gn.parent_field}' on {entity.name} must be a ref field"
            )


def validate_lifecycles(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate entity lifecycle: declarations (ADR-0020).

    Checks:
    - status_field references a real field on the entity
    - status_field is an enum-typed field
    - Every state name matches one of the enum's declared values
    - Order values are unique across states
    - Every transition from_state/to_state references a declared state
    - Evidence predicates, when present, are non-empty strings

    Note: The evidence predicate's internal syntax is NOT validated here
    (deferred to v1.1). This check only guards the structural invariants
    of the lifecycle block itself. The lifecycle: block is treated as
    orthogonal to the existing state_machine: block — both may coexist.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        lc = entity.lifecycle
        if lc is None:
            continue

        prefix = f"Entity '{entity.name}' lifecycle:"
        field_map = {f.name: f for f in entity.fields}

        # 1. status_field must reference a real field
        status_field = field_map.get(lc.status_field)
        if status_field is None:
            errors.append(
                f"{prefix} status_field '{lc.status_field}' is not a field on "
                f"entity '{entity.name}'"
            )
            enum_values: set[str] = set()
        elif status_field.type.kind != ir.FieldTypeKind.ENUM:
            errors.append(
                f"{prefix} status_field '{lc.status_field}' must be an enum field, "
                f"got '{status_field.type.kind.value}'"
            )
            enum_values = set()
        else:
            enum_values = set(status_field.type.enum_values or [])

        # 2. State names must match the enum's declared values
        #    (only when we were able to resolve the enum)
        if enum_values:
            for state in lc.states:
                if state.name not in enum_values:
                    errors.append(
                        f"{prefix} state '{state.name}' is not a declared value of "
                        f"enum field '{lc.status_field}' "
                        f"(expected one of: {sorted(enum_values)})"
                    )

        # 3. Order values must be unique across states
        orders_seen: dict[int, str] = {}
        for state in lc.states:
            if state.order in orders_seen:
                errors.append(
                    f"{prefix} duplicate order {state.order} on states "
                    f"'{orders_seen[state.order]}' and '{state.name}' — "
                    f"order values must be unique"
                )
            else:
                orders_seen[state.order] = state.name

        # 4. Transition from/to must reference declared states
        declared_states = {s.name for s in lc.states}
        for idx, tr in enumerate(lc.transitions):
            if tr.from_state not in declared_states:
                errors.append(
                    f"{prefix} transition #{idx} from_state '{tr.from_state}' "
                    f"is not a declared state"
                )
            if tr.to_state not in declared_states:
                errors.append(
                    f"{prefix} transition #{idx} to_state '{tr.to_state}' is not a declared state"
                )

            # 5. Evidence, when present, must be a non-empty string
            if tr.evidence is not None and not tr.evidence.strip():
                errors.append(
                    f"{prefix} transition {tr.from_state} -> {tr.to_state} "
                    f"has empty evidence predicate — omit the evidence clause "
                    f"if none is required"
                )

        # Optional: warn if both state_machine and lifecycle are present
        # with mismatched state lists. Treated as orthogonal, so this is
        # advisory only.
        if entity.state_machine is not None:
            sm_states = {(s if isinstance(s, str) else s.name) for s in entity.state_machine.states}
            if sm_states and sm_states != declared_states:
                warnings.append(
                    f"{prefix} state_machine states {sorted(sm_states)} "
                    f"differ from lifecycle states {sorted(declared_states)} — "
                    f"these blocks are orthogonal but the mismatch may indicate "
                    f"they are out of sync"
                )

    return errors, warnings


def validate_fitness_repr_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Warn if any entity lacks fitness.repr_fields.

    Part of the Agent-Led Fitness v1 methodology. v1 ships as a warning;
    v1.1 will promote this to an error. Entities without repr_fields are
    skipped by the fitness evaluator.

    Framework-synthetic entities (``domain == "platform"``, e.g. SystemHealth,
    AIJob, FeedbackReport) are exempt — they are code-generated and cannot
    carry a user-authored fitness block.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        # Skip framework-synthetic platform entities (generated from code)
        if entity.domain == "platform":
            continue
        if entity.fitness is None or not entity.fitness.repr_fields:
            warnings.append(
                f"Entity {entity.name!r}: no fitness.repr_fields declared — "
                f"fitness evaluation will skip this entity. Add a "
                f"`fitness:\n  repr_fields: [...]` block with domain-essential "
                f"fields."
            )
    return errors, warnings


def validate_storage_refs(
    appspec: ir.AppSpec,
    storage_defs: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    """Validate that every `field foo: file storage=<name>` reference
    resolves to a `[storage.<name>]` block declared in dazzle.toml (#932).

    Also warns when `storage=<name>` is set on a non-`file` field —
    the binding is ignored everywhere else but it's a clear authoring
    mistake.

    Takes ``storage_defs`` separately because the AppSpec is built
    from DSL alone — the manifest is loaded by a different layer.
    Runtime call site is `dazzle_back.runtime.server` startup, where
    both surfaces are available.

    Returns:
        Tuple of (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []
    declared = set(storage_defs)
    for entity in appspec.domain.entities:
        for field_spec in entity.fields:
            refs: tuple[str, ...] = getattr(field_spec, "storage", ()) or ()
            if not refs:
                continue
            for ref in refs:
                if ref not in declared:
                    hint = (
                        f" Available: {sorted(declared)}"
                        if declared
                        else " (no [storage.*] blocks declared in dazzle.toml)"
                    )
                    errors.append(
                        f"Entity {entity.name!r} field {field_spec.name!r}: "
                        f"storage={ref!r} does not resolve to a declared "
                        f"[storage.{ref}] block.{hint}"
                    )
            if field_spec.type.kind != ir.FieldTypeKind.FILE:
                rendered = "|".join(refs)
                warnings.append(
                    f"Entity {entity.name!r} field {field_spec.name!r}: "
                    f"storage={rendered!r} only applies to `file` typed fields; "
                    f"got type={field_spec.type.kind.value}. The binding "
                    f"will be ignored at runtime."
                )
    return errors, warnings


# =============================================================================
# Validator hardening — closes #1061
# =============================================================================
#
# Four blindspots that `dazzle validate` silently allowed before #1061:
#   1. `role(<name>)` in permit clauses that doesn't match any User.role
#      enum value (dead permissions — never matches any user).
#   2. `tenancy.partition_key` naming a field that no entity declares
#      (multi-tenancy silently broken).
#   3. Service refs inside `process` step `service:` clauses that don't
#      resolve to a declared `domain_service`.
#   4. RBAC matrix `PolicyWarning`s (redundant_forbid, orphan_role) that
#      `generate_access_matrix` produces but no validator surfaced.
#
# All four are warnings (not errors) so existing CI stays green; promote
# to errors in a future minor once downstream apps have absorbed them.


def _walk_role_names(condition: Any) -> set[str]:
    """Recursively collect role names from a ConditionExpr tree."""
    if condition is None:
        return set()
    roles: set[str] = set()
    if condition.role_check is not None:
        roles.add(condition.role_check.role_name)
    if condition.is_compound:
        roles.update(_walk_role_names(condition.left))
        roles.update(_walk_role_names(condition.right))
    return roles


def _find_user_role_enum(appspec: ir.AppSpec) -> tuple[str, set[str]] | None:
    """Locate the User entity's enum-typed `role` field and return its values.

    Returns (entity_name, enum_values) or None if no User entity / no role
    field with enum values is found. Prefers the explicit USER archetype
    but falls back to "any entity named User with an enum role field" so
    fixtures that don't tag the archetype still get checked.
    """
    candidates: list[ir.EntitySpec] = []
    for entity in appspec.domain.entities:
        if entity.archetype_kind == ir.ArchetypeKind.USER:
            candidates.insert(0, entity)
        elif entity.name in {"User", "Account"}:
            candidates.append(entity)
    for entity in candidates:
        for field in entity.fields:
            if field.name != "role":
                continue
            if field.type.kind == ir.FieldTypeKind.ENUM and field.type.enum_values:
                return entity.name, set(field.type.enum_values)
    return None


def validate_role_references_against_enum(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when a `role(<name>)` check references a value not in User.role.

    A common /fuzz finding (shapes_validation #530): a permit clause
    `role(guardian)` silently never matches because `guardian` is a
    persona name, not a value in the User.role enum.
    """
    errors: list[str] = []
    warnings: list[str] = []

    user_info = _find_user_role_enum(appspec)
    if user_info is None:
        return errors, warnings
    user_entity_name, enum_values = user_info

    for entity in appspec.domain.entities:
        if entity.access is None:
            continue
        seen: set[tuple[str, str]] = set()
        for rule in entity.access.permissions:
            for role_name in _walk_role_names(rule.condition):
                if role_name in enum_values:
                    continue
                key = (entity.name, role_name)
                if key in seen:
                    continue
                seen.add(key)
                warnings.append(
                    f"Entity '{entity.name}': permit references "
                    f"role({role_name!r}) which is not in {user_entity_name}.role "
                    f"enum ({sorted(enum_values)}). The check will never "
                    f"match — rule is dead."
                )

    return errors, warnings


def validate_tenancy_partition_key(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Verify `tenancy.partition_key` names a field on at least one entity.

    A `tenancy: partition_key: tenant_id` block silently produces an
    un-partitioned runtime if no entity carries that field (found in
    support_tickets during /fuzz).
    """
    errors: list[str] = []
    warnings: list[str] = []

    tenancy = appspec.tenancy
    if tenancy is None or tenancy.isolation is None:
        return errors, warnings
    partition_key = tenancy.isolation.partition_key
    if not partition_key:
        return errors, warnings
    # SHARED_SCHEMA mode is the only one that needs the column to exist on
    # tenanted entities; single-tenant mode has no partition key in use.
    if tenancy.isolation.mode == ir.TenancyMode.SINGLE:
        return errors, warnings

    has_partition_field = any(
        field.name == partition_key for entity in appspec.domain.entities for field in entity.fields
    )
    if not has_partition_field:
        warnings.append(
            f"tenancy.partition_key={partition_key!r} but no entity "
            f"declares a field with that name. Multi-tenancy is "
            f"effectively disabled — data is not partitioned."
        )
    return errors, warnings


def validate_admin_personas_scope_conflict(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Reject a persona that is both a tenancy admin and bound to a scope rule.

    A persona listed in `tenancy.admin_personas` bypasses the tenant filter at
    runtime (#957). If the same persona is also named in a `scope: ... as:`
    rule, that rule is dead for that persona — its grants ignore the row
    filter — so the apparent partitioning is a silent cross-tenant leak (#1184).
    """
    errors: list[str] = []
    warnings: list[str] = []

    tenancy = appspec.tenancy
    if tenancy is None or not tenancy.admin_personas:
        return errors, warnings
    admin = set(tenancy.admin_personas)

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue
        conflicting: set[str] = set()
        for rule in entity.access.scopes:
            conflicting |= admin.intersection(rule.personas)
        for persona in sorted(conflicting):
            errors.append(
                f"Entity '{entity.name}': persona '{persona}' is in "
                f"`tenancy.admin_personas` (bypasses the tenant filter) and "
                f"also bound to a `scope:` rule via `as:`. The scope rule is "
                f"dead for that persona — remove '{persona}' from one side."
            )
    return errors, warnings


def validate_process_step_service_refs(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when a process step references a service that doesn't exist.

    Found in examples/pra during /fuzz: `service: auto_assign_task` on a
    process step where no such domain_service is declared.
    """
    errors: list[str] = []
    warnings: list[str] = []

    domain_service_names = {s.name for s in appspec.domain_services}
    for process in appspec.processes:
        for step in process.steps:
            if step.kind != ir.ProcessStepKind.SERVICE:
                continue
            if step.service and step.service not in domain_service_names:
                warnings.append(
                    f"Process {process.name!r} step {step.name!r}: "
                    f"service {step.service!r} is not declared in "
                    f"`domain_services`. The step will fail at runtime."
                )
    return errors, warnings


def validate_rbac_matrix_diagnostics(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Surface PolicyWarnings from `generate_access_matrix`.

    The RBAC matrix already detects redundant_forbid and orphan_role
    patterns at link-time, but no validator was surfacing them — they
    were silently discarded. This wires them into `dazzle validate`.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        from dazzle.rbac.matrix import generate_access_matrix
    except ImportError:
        return errors, warnings

    try:
        matrix = generate_access_matrix(appspec)
    except Exception:
        # Matrix generation can fail on incomplete AppSpecs during early
        # development; don't block validation.
        return errors, warnings

    for warning in matrix.warnings:
        warnings.append(f"[RBAC {warning.kind}] {warning.message}")

    return errors, warnings


# =============================================================================
# tenant_host: validator rules (#1289)
# =============================================================================


def _get_entities(appspec_or_fragment: object) -> list[Any]:
    """Return the entity list from either an AppSpec or a ModuleFragment."""
    entities = getattr(appspec_or_fragment, "entities", None)
    if entities is not None:
        return list(entities)
    domain = getattr(appspec_or_fragment, "domain", None)
    if domain is not None:
        return list(domain.entities)
    return []


def validate_tenant_host_blocks(
    appspec_or_fragment: object,
) -> tuple[list[str], list[str]]:
    """Hard-error rules for tenant_host: blocks (#1289).

    Rules 1-6 from docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md.
    Returns (errors, warnings).
    """
    import importlib.util
    import re

    errors: list[str] = []
    warnings: list[str] = []

    entities = _get_entities(appspec_or_fragment)
    entity_names: set[str] = {e.name for e in entities}

    by_domain: dict[str, list[tuple[int, Any]]] = {}

    for idx, entity in enumerate(entities):
        th = getattr(entity, "tenant_host", None)
        if th is None:
            continue

        # Rule 1: slug_field must name a slug-typed field on the same entity
        match = next((f for f in entity.fields if f.name == th.slug_field), None)
        if match is None:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field "
                f"{th.slug_field!r} does not match any field on the entity."
            )
        elif getattr(match.type, "kind", None) != ir.FieldTypeKind.SLUG:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field {th.slug_field!r} "
                f"must point at a `slug:` typed field (got {match.type.kind})."
            )

        # Rule 2: domain must look like a host
        if "." not in th.domain or " " in th.domain:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.domain {th.domain!r} "
                "is not a syntactically valid host."
            )

        # Rule 4: history_entity must exist
        if th.history_entity and th.history_entity not in entity_names:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.history_entity "
                f"{th.history_entity!r} is not declared in this AppSpec."
            )

        # Rule 5: dotted-path templates must resolve to an importable module.
        # We use importlib.util.find_spec (metadata-only, no module execution)
        # after validating that the path is a safe dotted-identifier shape.
        # This avoids dynamic import of user-controlled strings while still
        # catching genuinely missing module paths at validate time.
        _DOTTED_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
        for attr, label in (
            (th.not_found_template, "not_found_template"),
            (th.expired_template, "expired_template"),
        ):
            if attr is None:
                continue
            if ":" not in attr:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} must be in 'module.path:symbol' format."
                )
                continue
            mod_name, _, sym = attr.partition(":")
            if not _DOTTED_IDENT.match(mod_name) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", sym):
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} contains invalid characters in module path or symbol name."
                )
                continue
            try:
                spec = importlib.util.find_spec(mod_name)
                if spec is None:
                    errors.append(
                        f"Entity {entity.name!r}: tenant_host.{label} "
                        f"{attr!r} could not be imported: No module named {mod_name!r}"
                    )
            except (ModuleNotFoundError, ValueError) as exc:
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} could not be imported: {exc}"
                )

        by_domain.setdefault(th.domain, []).append((idx, entity))

    # Rule 3: when 2+ entities share a domain, each MUST carry distinct order:
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        orders = [e.tenant_host.order for _, e in items]
        if any(o is None for o in orders) or len(set(orders)) != len(orders):
            errors.append(
                f"Domain {domain!r}: 2+ entities declare tenant_host on this "
                "domain; each must carry a distinct `order: N` sub-field. "
                f"Entities involved: {[e.name for _, e in items]}."
            )

    # Rule 6: domain-level sub-fields must agree across entities sharing a domain
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        for shared in ("cookie_scope", "super_admin_role", "canonical_hosts"):
            values = {
                tuple(getattr(e.tenant_host, shared))
                if shared == "canonical_hosts"
                else getattr(e.tenant_host, shared)
                for _, e in items
            }
            if len(values) > 1:
                errors.append(
                    f"Domain {domain!r}: entities {[e.name for _, e in items]} "
                    f"disagree on tenant_host.{shared} {values!r}; values must be "
                    "identical across all entities sharing the same domain."
                )

    # Warning: print resolution order for multi-entity domains
    for domain, items in by_domain.items():
        if len(items) >= 2:
            ordered = sorted(items, key=lambda t: t[1].tenant_host.order or 0)
            chain = " -> ".join(e.name for _, e in ordered)
            warnings.append(f"Domain {domain!r} resolution order: {chain}")

    # Warning: multiple domains declared — slugs not globally unique
    if len(by_domain) >= 2:
        warnings.append(
            "Multiple tenant_host domains declared "
            f"({sorted(by_domain.keys())}); slugs are not unique across domains."
        )

    return errors, warnings


def validate_appspec(appspec_or_fragment: object) -> list[str]:
    """Validate a fragment or AppSpec for tenant_host hard-error rules.

    Suitable for direct use from tests and CLI commands that only need
    the error list.  Returns a flat list of error strings.
    """
    errors, _warnings = validate_tenant_host_blocks(appspec_or_fragment)
    return errors
