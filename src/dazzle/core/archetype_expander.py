"""
Archetype expansion for DAZZLE.

Expands semantic archetypes (settings, tenant, tenant_settings, user, user_membership)
into concrete IR, merges fields from extended archetypes, and generates auto-surfaces.

v0.10.3: Initial implementation (settings, tenant, tenant_settings)
v0.10.4: Added user and user_membership archetypes
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
    5. Applies user archetype (auth fields, admin access)
    6. Applies user_membership archetype (tenant-user-persona relationship)
    7. Injects tenant FK into non-settings/non-user entities

    Args:
        entities: List of entity specifications
        symbols: Symbol table with all archetypes

    Returns:
        List of modified entity specifications
    """
    # First pass: merge archetype fields into entities
    expanded = [_merge_archetype_fields(entity, symbols) for entity in entities]

    # Second pass: apply semantic archetype expansions (inject fields)
    expanded = [_apply_semantic_archetype(entity, expanded) for entity in expanded]

    # Third pass: inject tenant FK if there's a tenant entity
    tenant_entity = _find_tenant_entity(expanded)
    if tenant_entity:
        expanded = _inject_tenant_fk(expanded, tenant_entity)

    return expanded


def generate_archetype_surfaces(
    entities: list[ir.EntitySpec],
    existing_surfaces: list[ir.SurfaceSpec],
) -> list[ir.SurfaceSpec]:
    """
    Generate auto-surfaces for semantic archetypes.

    Generates:
    - Settings surface for each settings entity (admin-only, edit mode)
    - Tenant management surface for tenant entity (admin-only, list mode)
    - Tenant settings surface for tenant_settings entities (admin-only, edit mode)
    - User management surfaces for user entity (full CRUD: list, view, create, edit)
    - User membership surfaces for user_membership entity (list, edit)

    Skips generation if a surface with the same name already exists
    (allowing DSL override).

    Args:
        entities: List of expanded entity specifications
        existing_surfaces: List of existing surface specifications

    Returns:
        List of auto-generated surfaces (to be appended to existing)
    """
    existing_names = {s.name for s in existing_surfaces}
    generated: list[ir.SurfaceSpec] = []

    # Find user entity for membership surfaces
    user_entity = _find_user_entity(entities)

    for entity in entities:
        if not entity.archetype_kind:
            continue

        if entity.archetype_kind == ir.ArchetypeKind.SETTINGS:
            surface = _generate_settings_surface(entity)
            if surface.name not in existing_names:
                generated.append(surface)

        elif entity.archetype_kind == ir.ArchetypeKind.TENANT:
            surface = _generate_tenant_admin_surface(entity)
            if surface.name not in existing_names:
                generated.append(surface)

        elif entity.archetype_kind == ir.ArchetypeKind.TENANT_SETTINGS:
            surface = _generate_tenant_settings_surface(entity)
            if surface.name not in existing_names:
                generated.append(surface)

        elif entity.archetype_kind == ir.ArchetypeKind.USER:
            # Generate full CRUD surfaces for user management
            surfaces = _generate_user_management_surfaces(entity)
            for surface in surfaces:
                if surface.name not in existing_names:
                    generated.append(surface)
                    existing_names.add(surface.name)  # Prevent duplicates

        elif entity.archetype_kind == ir.ArchetypeKind.USER_MEMBERSHIP:
            # Generate membership management surfaces
            surfaces = _generate_membership_surfaces(entity, user_entity)
            for surface in surfaces:
                if surface.name not in existing_names:
                    generated.append(surface)
                    existing_names.add(surface.name)

    return generated


def _generate_settings_surface(entity: ir.EntitySpec) -> ir.SurfaceSpec:
    """
    Generate admin settings surface for a settings entity.

    Creates an edit-mode surface with:
    - All non-PK fields in a single section
    - Admin-only access
    - Route: /admin/settings/{entity_snake_name}

    Args:
        entity: Settings entity

    Returns:
        Auto-generated settings surface
    """
    snake_name = _to_snake_case(entity.name)

    # Create elements for all non-PK fields
    elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if not f.is_primary_key
    ]

    section = ir.SurfaceSection(
        name="settings",
        title=entity.title or f"{entity.name} Settings",
        elements=elements,
    )

    access = ir.SurfaceAccessSpec(
        require_auth=True,
        allow_personas=["admin"],
    )

    return ir.SurfaceSpec(
        name=f"{snake_name}_settings",
        title=entity.title or f"{entity.name} Settings",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.EDIT,
        sections=[section],
        actions=[],
        access=access,
    )


def _generate_tenant_admin_surface(entity: ir.EntitySpec) -> ir.SurfaceSpec:
    """
    Generate tenant management surface for site admins.

    Creates a list-mode surface with:
    - Key fields for tenant identification
    - Admin-only access
    - Route: /admin/tenants

    Args:
        entity: Tenant root entity

    Returns:
        Auto-generated tenant management surface
    """
    snake_name = _to_snake_case(entity.name)

    # Create elements for key fields (name, slug, etc. - non-PK, non-FK)
    elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if not f.is_primary_key and f.type.kind != ir.FieldTypeKind.REF
    ]

    section = ir.SurfaceSection(
        name="tenants",
        title=f"{entity.title or entity.name} List",
        elements=elements,
    )

    access = ir.SurfaceAccessSpec(
        require_auth=True,
        allow_personas=["admin"],
    )

    return ir.SurfaceSpec(
        name=f"{snake_name}_admin",
        title=f"Manage {entity.title or entity.name}s",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.LIST,
        sections=[section],
        actions=[],
        access=access,
    )


def _generate_tenant_settings_surface(entity: ir.EntitySpec) -> ir.SurfaceSpec:
    """
    Generate per-tenant settings surface.

    Creates an edit-mode surface with:
    - All non-PK, non-FK fields
    - Admin-only access (tenant admin at runtime)
    - Route: /settings/{entity_snake_name}

    Args:
        entity: Tenant settings entity

    Returns:
        Auto-generated tenant settings surface
    """
    snake_name = _to_snake_case(entity.name)

    # Create elements for non-PK, non-FK fields
    elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if not f.is_primary_key and f.type.kind != ir.FieldTypeKind.REF
    ]

    section = ir.SurfaceSection(
        name="settings",
        title=entity.title or f"{entity.name}",
        elements=elements,
    )

    access = ir.SurfaceAccessSpec(
        require_auth=True,
        allow_personas=["admin"],
    )

    return ir.SurfaceSpec(
        name=f"{snake_name}_settings",
        title=entity.title or f"{entity.name}",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.EDIT,
        sections=[section],
        actions=[],
        access=access,
    )


def _to_snake_case(name: str) -> str:
    """
    Convert PascalCase to snake_case.

    Args:
        name: PascalCase name (e.g., "AppSettings")

    Returns:
        snake_case name (e.g., "app_settings")
    """
    import re

    # Insert underscore before uppercase letters (except first)
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


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


def _apply_semantic_archetype(
    entity: ir.EntitySpec,
    all_entities: list[ir.EntitySpec],
) -> ir.EntitySpec:
    """
    Apply semantic archetype transformations.

    Args:
        entity: Entity to transform
        all_entities: All entities (for finding related entities like User)

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
    elif entity.archetype_kind == ir.ArchetypeKind.USER:
        return _expand_user_archetype(entity)
    elif entity.archetype_kind == ir.ArchetypeKind.USER_MEMBERSHIP:
        user_entity = _find_user_entity(all_entities)
        tenant_entity = _find_tenant_entity(all_entities)
        return _expand_user_membership_archetype(entity, user_entity, tenant_entity)

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
    - Entities with archetype: user (users are system-wide)
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

        # Skip user entities (users are system-wide, membership handles tenant scope)
        if entity.archetype_kind == ir.ArchetypeKind.USER:
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


# =============================================================================
# User Archetype Functions (v0.10.4)
# =============================================================================


def _find_user_entity(entities: list[ir.EntitySpec]) -> ir.EntitySpec | None:
    """
    Find the user entity (if any).

    Args:
        entities: List of entities

    Returns:
        User entity or None
    """
    for entity in entities:
        if entity.archetype_kind == ir.ArchetypeKind.USER:
            return entity
    return None


def _expand_user_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """
    Expand user archetype:
    - Inject auth-related fields if not present
    - Add admin-only access rules if not present

    Auto-injected fields:
    - password_hash: str(255) - For local auth
    - email_verified: bool = false
    - email_verify_token: str(100)
    - password_reset_token: str(100)
    - password_reset_expires: datetime
    - is_active: bool = true
    - last_login: datetime
    - auth_provider: enum[local,google,apple,github] = local
    - auth_provider_id: str(255) - External provider user ID
    - created_at: datetime auto_add

    Args:
        entity: User entity

    Returns:
        Expanded entity with auth fields and admin access
    """
    existing_field_names = {f.name for f in entity.fields}

    # Define auth fields to inject
    auth_fields = _get_user_auth_fields()

    # Filter out fields that already exist
    fields_to_inject = [f for f in auth_fields if f.name not in existing_field_names]

    # Append auth fields to entity fields
    new_fields = list(entity.fields) + fields_to_inject

    # Generate admin-only access rules if none exist
    access = entity.access
    if not access:
        access = _create_admin_only_access()

    return entity.model_copy(
        update={
            "fields": new_fields,
            "access": access,
        }
    )


def _get_user_auth_fields() -> list[ir.FieldSpec]:
    """
    Get the list of auth-related fields to inject into user entity.

    Returns:
        List of FieldSpec for auth fields
    """
    return [
        # Local authentication
        ir.FieldSpec(
            name="password_hash",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=255),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        ir.FieldSpec(
            name="email_verified",
            type=ir.FieldType(kind=ir.FieldTypeKind.BOOL),
            default=False,
        ),
        ir.FieldSpec(
            name="email_verify_token",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        ir.FieldSpec(
            name="password_reset_token",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        ir.FieldSpec(
            name="password_reset_expires",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        # Account status
        ir.FieldSpec(
            name="is_active",
            type=ir.FieldType(kind=ir.FieldTypeKind.BOOL),
            default=True,
        ),
        ir.FieldSpec(
            name="last_login",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        # OAuth/SSO support
        ir.FieldSpec(
            name="auth_provider",
            type=ir.FieldType(
                kind=ir.FieldTypeKind.ENUM,
                enum_values=["local", "google", "apple", "github"],
            ),
            default="local",
        ),
        ir.FieldSpec(
            name="auth_provider_id",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=255),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
        # Timestamps
        ir.FieldSpec(
            name="created_at",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.AUTO_ADD],
        ),
    ]


def _expand_user_membership_archetype(
    entity: ir.EntitySpec,
    user_entity: ir.EntitySpec | None,
    tenant_entity: ir.EntitySpec | None,
) -> ir.EntitySpec:
    """
    Expand user_membership archetype:
    - Inject user ref if not present
    - Inject tenant ref if not present (and tenant exists)
    - Inject personas field if not present
    - Inject membership metadata fields
    - Add appropriate access rules

    Auto-injected fields:
    - user: ref User required
    - {tenant}: ref {Tenant} required (if tenant entity exists)
    - personas: json = [] (list of persona names)
    - is_primary: bool = false
    - invited_by: ref User optional
    - invited_at: datetime auto_add
    - accepted_at: datetime optional

    Args:
        entity: User membership entity
        user_entity: User entity (if found)
        tenant_entity: Tenant entity (if found)

    Returns:
        Expanded entity with membership fields
    """
    existing_field_names = {f.name for f in entity.fields}
    fields_to_inject: list[ir.FieldSpec] = []

    # Inject user ref if not present
    if user_entity and "user" not in existing_field_names:
        has_user_ref = any(
            f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == user_entity.name
            for f in entity.fields
        )
        if not has_user_ref:
            fields_to_inject.append(
                ir.FieldSpec(
                    name="user",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity=user_entity.name,
                    ),
                    modifiers=[ir.FieldModifier.REQUIRED],
                )
            )

    # Inject tenant ref if not present (and tenant exists)
    if tenant_entity:
        tenant_field_name = tenant_entity.name[0].lower() + tenant_entity.name[1:]
        has_tenant_ref = any(
            f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == tenant_entity.name
            for f in entity.fields
        )
        if not has_tenant_ref and tenant_field_name not in existing_field_names:
            fields_to_inject.append(
                ir.FieldSpec(
                    name=tenant_field_name,
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity=tenant_entity.name,
                    ),
                    modifiers=[ir.FieldModifier.REQUIRED],
                )
            )

    # Inject membership fields
    membership_fields = _get_membership_fields(user_entity)
    for field in membership_fields:
        if field.name not in existing_field_names:
            fields_to_inject.append(field)

    # Prepend injected fields (user/tenant refs first)
    new_fields = fields_to_inject + list(entity.fields)

    # Generate admin-only access rules if none exist
    access = entity.access
    if not access:
        access = _create_admin_only_access()

    return entity.model_copy(
        update={
            "fields": new_fields,
            "access": access,
        }
    )


def _get_membership_fields(user_entity: ir.EntitySpec | None) -> list[ir.FieldSpec]:
    """
    Get the list of membership-related fields to inject.

    Args:
        user_entity: User entity (for invited_by ref)

    Returns:
        List of FieldSpec for membership fields
    """
    fields = [
        # Personas (roles within tenant)
        ir.FieldSpec(
            name="personas",
            type=ir.FieldType(kind=ir.FieldTypeKind.JSON),
            default="[]",  # Empty JSON array
        ),
        # Primary membership flag
        ir.FieldSpec(
            name="is_primary",
            type=ir.FieldType(kind=ir.FieldTypeKind.BOOL),
            default=False,
        ),
        # Invitation tracking
        ir.FieldSpec(
            name="invited_at",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.AUTO_ADD],
        ),
        ir.FieldSpec(
            name="accepted_at",
            type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
            modifiers=[ir.FieldModifier.OPTIONAL],
        ),
    ]

    # Add invited_by ref if user entity exists
    if user_entity:
        fields.insert(
            2,  # After personas, before is_primary
            ir.FieldSpec(
                name="invited_by",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.REF,
                    ref_entity=user_entity.name,
                ),
                modifiers=[ir.FieldModifier.OPTIONAL],
            ),
        )

    return fields


def _generate_user_management_surfaces(entity: ir.EntitySpec) -> list[ir.SurfaceSpec]:
    """
    Generate user management surfaces (full CRUD).

    Generates:
    - user_list: List all users (admin view)
    - user_view: View user details
    - user_create: Create new user
    - user_edit: Edit user

    Args:
        entity: User entity

    Returns:
        List of auto-generated surfaces
    """
    snake_name = _to_snake_case(entity.name)

    # Identify display fields (non-sensitive, non-PK)
    sensitive_fields = {
        "password_hash",
        "email_verify_token",
        "password_reset_token",
        "password_reset_expires",
        "auth_provider_id",
    }

    display_fields = [
        f for f in entity.fields if not f.is_primary_key and f.name not in sensitive_fields
    ]

    # List surface (admin)
    list_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in display_fields
        if f.name in {"email", "name", "is_active", "last_login", "auth_provider"}
    ]

    list_surface = ir.SurfaceSpec(
        name=f"{snake_name}_list",
        title=f"Manage {entity.title or entity.name}s",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="users",
                title=f"{entity.title or entity.name} List",
                elements=list_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    # View surface
    view_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in display_fields
        if f.name not in sensitive_fields
    ]

    view_surface = ir.SurfaceSpec(
        name=f"{snake_name}_view",
        title=f"{entity.title or entity.name} Details",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(
                name="details",
                title=f"{entity.title or entity.name} Information",
                elements=view_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    # Create surface
    create_fields = {"email", "name"}  # Minimal fields for user creation
    create_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if f.name in create_fields
    ]

    create_surface = ir.SurfaceSpec(
        name=f"{snake_name}_create",
        title=f"Create {entity.title or entity.name}",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.CREATE,
        sections=[
            ir.SurfaceSection(
                name="new_user",
                title="New User",
                elements=create_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    # Edit surface
    edit_fields = {"email", "name", "is_active", "email_verified"}
    edit_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if f.name in edit_fields
    ]

    edit_surface = ir.SurfaceSpec(
        name=f"{snake_name}_edit",
        title=f"Edit {entity.title or entity.name}",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.EDIT,
        sections=[
            ir.SurfaceSection(
                name="edit_user",
                title="Edit User",
                elements=edit_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    return [list_surface, view_surface, create_surface, edit_surface]


def _generate_membership_surfaces(
    entity: ir.EntitySpec,
    user_entity: ir.EntitySpec | None,
) -> list[ir.SurfaceSpec]:
    """
    Generate user membership management surfaces.

    Generates:
    - {entity}_list: List memberships (for managing user-tenant assignments)
    - {entity}_edit: Edit membership (assign personas)

    Args:
        entity: User membership entity
        user_entity: User entity (for display)

    Returns:
        List of auto-generated surfaces
    """
    snake_name = _to_snake_case(entity.name)

    # Display fields for list (non-PK, non-FK identity fields)
    list_fields = {"personas", "is_primary", "invited_at", "accepted_at"}
    list_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if f.name in list_fields or f.type.kind == ir.FieldTypeKind.REF
    ]

    list_surface = ir.SurfaceSpec(
        name=f"{snake_name}_list",
        title=f"Manage {entity.title or 'User Memberships'}",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="memberships",
                title="User Memberships",
                elements=list_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    # Edit surface for managing personas
    edit_fields = {"personas", "is_primary"}
    edit_elements = [
        ir.SurfaceElement(
            field_name=f.name,
            label=f.name.replace("_", " ").title(),
        )
        for f in entity.fields
        if f.name in edit_fields
    ]

    edit_surface = ir.SurfaceSpec(
        name=f"{snake_name}_edit",
        title=f"Edit {entity.title or 'Membership'}",
        entity_ref=entity.name,
        mode=ir.SurfaceMode.EDIT,
        sections=[
            ir.SurfaceSection(
                name="edit_membership",
                title="Edit Membership",
                elements=edit_elements,
            )
        ],
        actions=[],
        access=ir.SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin"],
        ),
    )

    return [list_surface, edit_surface]
