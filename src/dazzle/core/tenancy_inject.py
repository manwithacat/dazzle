"""Framework-owned tenant-discriminator injection (RLS tenancy Phase A).

Under `tenancy: mode: shared_schema`, every tenant-scoped entity gets a uniform
`partition_key` (default `tenant_id`) ``ref <TenantEntity> required`` injected as
its first field — making the discriminator framework-owned rather than
author-declared. Honors `tenancy.entities_excluded`; skips the tenant entity,
USER/SETTINGS archetypes, and entities that already declare the column (so apps
that hand-declared `tenant_id` keep working). Pure IR transform — no DB, no SQL.
"""

from __future__ import annotations

from dazzle.core import ir


def _find_tenant_entity(entities: list[ir.EntitySpec]) -> ir.EntitySpec | None:
    for entity in entities:
        if entity.is_tenant_root or entity.archetype_kind == ir.ArchetypeKind.TENANT:
            return entity
    return None


def inject_partition_key(
    entities: list[ir.EntitySpec],
    tenancy: ir.TenancySpec | None,
) -> list[ir.EntitySpec]:
    """Inject the uniform partition-key ref on tenant-scoped entities.

    Returns the entity list unchanged unless ``tenancy.isolation.mode`` is
    SHARED_SCHEMA and a tenant entity exists.
    """
    if tenancy is None or tenancy.isolation.mode != ir.TenancyMode.SHARED_SCHEMA:
        return entities

    tenant_entity = _find_tenant_entity(entities)
    if tenant_entity is None:
        return entities

    partition_key = tenancy.isolation.partition_key
    excluded = set(tenancy.entities_excluded)
    tenant_name = tenant_entity.name

    result: list[ir.EntitySpec] = []
    for entity in entities:
        # Skip a USER_MEMBERSHIP entity that keeps its own per-app-named tenant ref
        # (e.g. ``organization``): it must not also receive a second ``tenant_id``
        # (uniformity cleanup of those refs is a later concern). #1461: this check
        # was previously applied to ANY entity with a ref to the tenant root — which
        # silently skipped *leaf data entities* that declare a direct ``ref <Tenant>``
        # (e.g. ``trust: ref Trust``) from injection AND left them unfenced (no
        # tenant_id, RLS off) → cross-tenant exposure. A direct root ref is just
        # another path to root; only membership archetypes get the by-target skip.
        has_membership_tenant_ref = (
            entity.archetype_kind == ir.ArchetypeKind.USER_MEMBERSHIP
            and any(
                f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == tenant_name
                for f in entity.fields
            )
        )
        if (
            entity.name == tenant_name
            or entity.name in excluded
            or entity.archetype_kind in (ir.ArchetypeKind.USER, ir.ArchetypeKind.SETTINGS)
            # Framework/platform entities (AIJob, AuditEntry, admin, …) are
            # cross-tenant by design and managed by the framework — never auto-fenced.
            or entity.domain == "platform"
            or any(f.name == partition_key for f in entity.fields)
            or has_membership_tenant_ref
        ):
            result.append(entity)
            continue

        field = ir.FieldSpec(
            name=partition_key,
            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=tenant_name),
            modifiers=[ir.FieldModifier.REQUIRED],
        )
        result.append(entity.model_copy(update={"fields": [field, *entity.fields]}))

    return result
