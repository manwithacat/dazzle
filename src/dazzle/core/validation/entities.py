"""Entity-level semantic validation (fields, PKs, constraints, reserved names).

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir

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


def _validate_profile_archetype(entity: ir.EntitySpec, tenancy: object, errors: list[str]) -> None:
    """``archetype: profile`` requires ``tenancy: mode: shared_schema`` (Plan 3c).

    A profile is keyed by ``(tenant_id, identity_id)`` — without shared_schema
    tenancy there is no injected ``tenant_id``, so the key (and the per-member-
    per-org uniqueness) cannot exist. Fail loud rather than emit a broken global
    unique on ``identity_id``.
    """
    is_profile = getattr(entity, "is_profile", False) or (
        entity.archetype_kind == ir.ArchetypeKind.PROFILE
    )
    if not is_profile:
        return
    isolation = getattr(tenancy, "isolation", None)
    mode = getattr(isolation, "mode", None)
    if mode != ir.TenancyMode.SHARED_SCHEMA:
        errors.append(
            f"Entity '{entity.name}': archetype: profile requires "
            "tenancy: mode: shared_schema (the profile is keyed by "
            "(tenant_id, identity_id))"
        )


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
        _validate_profile_archetype(entity, getattr(appspec, "tenancy", None), errors)
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
