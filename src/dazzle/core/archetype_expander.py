"""
Archetype expansion for DAZZLE.

Expands semantic archetypes (settings, tenant, tenant_settings) into concrete IR,
merges fields from extended archetypes, and generates auto-surfaces.

v0.10.3: Initial implementation
"""

from __future__ import annotations

from . import ir
from .linker_impl import SymbolTable


def expand_archetypes(
    entities: list[ir.EntitySpec],
    symbols: SymbolTable,
) -> list[ir.EntitySpec]:
    """
    Expand semantic archetypes into concrete IR modifications.

    This function:
    1. Merges fields from `extends:` archetypes into entities
    2. Applies settings archetype (singleton, admin access)
    3. Applies tenant archetype (marks tenant root)
    4. Applies tenant_settings archetype (per-tenant singleton)
    5. Injects tenant FK into non-settings entities

    Args:
        entities: List of entity specifications
        symbols: Symbol table with all archetypes

    Returns:
        List of modified entity specifications
    """
    # First pass: merge archetype fields into entities
    expanded = [_merge_archetype_fields(entity, symbols) for entity in entities]

    # Second pass: apply semantic archetype expansions
    expanded = [_apply_semantic_archetype(entity) for entity in expanded]

    # Third pass: inject tenant FK if there's a tenant entity
    tenant_entity = _find_tenant_entity(expanded)
    if tenant_entity:
        expanded = _inject_tenant_fk(expanded, tenant_entity)

    return expanded


def _merge_archetype_fields(
    entity: ir.EntitySpec,
    symbols: SymbolTable,
) -> ir.EntitySpec:
    """
    Merge fields, computed_fields, and invariants from extended archetypes.

    Archetype fields are prepended to entity fields (archetype fields first).
    If an entity defines a field with the same name as an archetype field,
    the entity's field takes precedence.

    Args:
        entity: Entity to expand
        symbols: Symbol table with archetypes

    Returns:
        Entity with merged fields
    """
    if not entity.extends:
        return entity

    # Collect fields from all archetypes (in order)
    archetype_fields: list[ir.FieldSpec] = []
    archetype_computed: list[ir.ComputedFieldSpec] = []
    archetype_invariants: list[ir.InvariantSpec] = []

    # Get existing field names to avoid duplicates
    existing_field_names = {f.name for f in entity.fields}

    for archetype_name in entity.extends:
        archetype = symbols.archetypes.get(archetype_name)
        if not archetype:
            # Validation should have caught this, but be defensive
            continue

        # Add archetype fields (skip if entity already has field with same name)
        for field in archetype.fields:
            if field.name not in existing_field_names:
                archetype_fields.append(field)
                existing_field_names.add(field.name)

        # Add computed fields (skip duplicates)
        existing_computed_names = {f.name for f in entity.computed_fields}
        for computed in archetype.computed_fields:
            if computed.name not in existing_computed_names:
                archetype_computed.append(computed)
                existing_computed_names.add(computed.name)

        # Add invariants (all are included - may have different expressions)
        archetype_invariants.extend(archetype.invariants)

    # Merge: archetype fields come first, then entity fields
    merged_fields = archetype_fields + list(entity.fields)
    merged_computed = archetype_computed + list(entity.computed_fields)
    merged_invariants = archetype_invariants + list(entity.invariants)

    return entity.model_copy(
        update={
            "fields": merged_fields,
            "computed_fields": merged_computed,
            "invariants": merged_invariants,
        }
    )


def _apply_semantic_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """
    Apply semantic archetype transformations (settings, tenant, tenant_settings).

    Args:
        entity: Entity to transform

    Returns:
        Transformed entity
    """
    if not entity.archetype_kind:
        return entity

    if entity.archetype_kind == ir.ArchetypeKind.SETTINGS:
        return _expand_settings_archetype(entity)
    elif entity.archetype_kind == ir.ArchetypeKind.TENANT:
        return _expand_tenant_archetype(entity)
    elif entity.archetype_kind == ir.ArchetypeKind.TENANT_SETTINGS:
        return _expand_tenant_settings_archetype(entity)

    return entity


def _expand_settings_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """
    Expand settings archetype:
    - Set is_singleton = True
    - Add admin-only access rules if not present

    Args:
        entity: Settings entity

    Returns:
        Expanded entity with singleton flag and admin access
    """
    # Generate admin-only access rules if none exist
    access = entity.access
    if not access:
        access = _create_admin_only_access()

    return entity.model_copy(
        update={
            "is_singleton": True,
            "access": access,
        }
    )


def _expand_tenant_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """
    Expand tenant archetype:
    - Set is_tenant_root = True

    Args:
        entity: Tenant root entity

    Returns:
        Expanded entity with tenant root flag
    """
    return entity.model_copy(
        update={
            "is_tenant_root": True,
        }
    )


def _expand_tenant_settings_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """
    Expand tenant_settings archetype:
    - Set is_singleton = True (per-tenant singleton)
    - Add tenant admin access rules if not present

    Args:
        entity: Tenant settings entity

    Returns:
        Expanded entity with singleton flag and tenant admin access
    """
    # For tenant settings, we use is_singleton but scoped to tenant
    # Access rules should allow tenant admins, not just site admins
    access = entity.access
    if not access:
        # For now, use admin-only access (tenant admin logic handled at runtime)
        access = _create_admin_only_access()

    return entity.model_copy(
        update={
            "is_singleton": True,
            "access": access,
        }
    )


def _create_admin_only_access() -> ir.AccessSpec:
    """
    Create admin-only access specification.

    Returns:
        AccessSpec with admin role requirement for all operations
    """
    admin_role_check = ir.RoleCheck(role_name="admin")
    admin_condition = ir.ConditionExpr(role_check=admin_role_check)

    visibility_rules = [
        ir.VisibilityRule(
            context=ir.AuthContext.AUTHENTICATED,
            condition=admin_condition,
        )
    ]

    permission_rules = [
        ir.PermissionRule(
            operation=ir.PermissionKind.CREATE,
            require_auth=True,
            condition=admin_condition,
        ),
        ir.PermissionRule(
            operation=ir.PermissionKind.UPDATE,
            require_auth=True,
            condition=admin_condition,
        ),
        ir.PermissionRule(
            operation=ir.PermissionKind.DELETE,
            require_auth=True,
            condition=admin_condition,
        ),
    ]

    return ir.AccessSpec(
        visibility=visibility_rules,
        permissions=permission_rules,
    )


def _find_tenant_entity(entities: list[ir.EntitySpec]) -> ir.EntitySpec | None:
    """
    Find the tenant root entity (if any).

    Args:
        entities: List of entities

    Returns:
        Tenant entity or None
    """
    for entity in entities:
        if entity.is_tenant_root or entity.archetype_kind == ir.ArchetypeKind.TENANT:
            return entity
    return None


def _inject_tenant_fk(
    entities: list[ir.EntitySpec],
    tenant_entity: ir.EntitySpec,
) -> list[ir.EntitySpec]:
    """
    Inject tenant FK into all entities that don't already have one.

    Skips:
    - The tenant entity itself
    - Entities with archetype: settings (system-wide, not tenant-scoped)
    - Entities that already have a ref to the tenant entity

    Args:
        entities: List of entities
        tenant_entity: The tenant root entity

    Returns:
        List of entities with tenant FK injected
    """
    tenant_name = tenant_entity.name
    # Use lowercase entity name as field name (e.g., Company -> company)
    tenant_field_name = tenant_name[0].lower() + tenant_name[1:]

    result = []
    for entity in entities:
        # Skip the tenant entity itself
        if entity.name == tenant_name:
            result.append(entity)
            continue

        # Skip settings entities (system-wide, not tenant-scoped)
        if entity.archetype_kind == ir.ArchetypeKind.SETTINGS:
            result.append(entity)
            continue

        # Check if entity already has a reference to the tenant
        has_tenant_ref = any(
            f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == tenant_name
            for f in entity.fields
        )

        if has_tenant_ref:
            result.append(entity)
            continue

        # Inject tenant FK field
        tenant_field = ir.FieldSpec(
            name=tenant_field_name,
            type=ir.FieldType(
                kind=ir.FieldTypeKind.REF,
                ref_entity=tenant_name,
            ),
            modifiers=[ir.FieldModifier.REQUIRED],
        )

        # Prepend tenant field to entity fields
        new_fields = [tenant_field] + list(entity.fields)
        result.append(entity.model_copy(update={"fields": new_fields}))

    return result
