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
        # Skip if the entity already references the tenant — by the partition-key
        # field name OR by ref *target*. The by-target check matches the original
        # ``_inject_tenant_fk`` ``has_tenant_ref`` semantic: membership/archetype
        # entities (e.g. USER_MEMBERSHIP) keep their per-app-named tenant ref (e.g.
        # ``organization``) for now, so they must not also receive a second
        # ``tenant_id`` (uniformity cleanup of those refs is a later concern).
        has_tenant_ref = any(
            f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == tenant_name
            for f in entity.fields
        )
        if (
            entity.name == tenant_name
            or entity.name in excluded
            or entity.archetype_kind in (ir.ArchetypeKind.USER, ir.ArchetypeKind.SETTINGS)
            or any(f.name == partition_key for f in entity.fields)
            or has_tenant_ref
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
