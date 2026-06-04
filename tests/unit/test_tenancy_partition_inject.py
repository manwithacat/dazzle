"""Unit tests for framework-owned partition-key injection (RLS tenancy Phase A)."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.tenancy_inject import inject_partition_key


def _entity(
    name: str,
    *fields: ir.FieldSpec,
    is_tenant_root: bool = False,
    archetype: ir.ArchetypeKind | None = None,
) -> ir.EntitySpec:
    base = [
        ir.FieldSpec(
            name="id",
            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
            modifiers=[ir.FieldModifier.PK],
        )
    ]
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=base + list(fields),
        is_tenant_root=is_tenant_root,
        archetype_kind=archetype,
    )


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
        modifiers=[ir.FieldModifier.REQUIRED],
    )


def _shared_schema_tenancy(excluded: list[str] | None = None) -> ir.TenancySpec:
    return ir.TenancySpec(
        isolation=ir.TenantIsolationSpec(
            mode=ir.TenancyMode.SHARED_SCHEMA, partition_key="tenant_id"
        ),
        entities_excluded=excluded or [],
    )


def test_injects_uniform_tenant_id_on_scoped_entities() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Project"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    by_name = {e.name: e for e in out}
    # tenant root itself is NOT scoped
    assert all(f.name != "tenant_id" for f in by_name["Workspace"].fields)
    # every other entity gets a uniform tenant_id ref to the tenant entity, first
    for n in ("Project", "Task"):
        tid = by_name[n].fields[0]
        assert tid.name == "tenant_id"
        assert tid.type.kind == ir.FieldTypeKind.REF
        assert tid.type.ref_entity == "Workspace"
        assert ir.FieldModifier.REQUIRED in tid.modifiers


def test_respects_entities_excluded() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Currency"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy(excluded=["Currency"]))
    by_name = {e.name: e for e in out}
    assert all(f.name != "tenant_id" for f in by_name["Currency"].fields)
    assert by_name["Task"].fields[0].name == "tenant_id"


def test_skips_if_already_declared() -> None:
    # invoice_ops back-compat: author already hand-declared tenant_id.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("Task", _ref("tenant_id", "Workspace")),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    task = next(e for e in out if e.name == "Task")
    assert sum(1 for f in task.fields if f.name == "tenant_id") == 1


def test_skips_user_and_settings_archetypes() -> None:
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("Member", archetype=ir.ArchetypeKind.USER),
        _entity("Config", archetype=ir.ArchetypeKind.SETTINGS),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    by_name = {e.name: e for e in out}
    assert all(f.name != "tenant_id" for f in by_name["Member"].fields)
    assert all(f.name != "tenant_id" for f in by_name["Config"].fields)


def test_noop_when_not_shared_schema() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Task")]
    single = ir.TenancySpec(isolation=ir.TenantIsolationSpec(mode=ir.TenancyMode.SINGLE))
    out = inject_partition_key(entities, single)
    assert all(f.name != "tenant_id" for e in out for f in e.fields if e.name == "Task")


def test_noop_when_no_tenant_entity() -> None:
    entities = [_entity("Project"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    assert out == entities  # nothing to anchor to; left untouched


def test_skips_if_tenant_ref_under_different_name() -> None:
    # An entity that already references the tenant entity under a DIFFERENT field
    # name (e.g. membership/archetype entities keep their per-app-named ref) must
    # NOT get a second tenant_id injected — skip is by ref target, not just name.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("Membership", _ref("org", "Workspace")),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    membership = next(e for e in out if e.name == "Membership")
    tenant_refs = [
        f
        for f in membership.fields
        if f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == "Workspace"
    ]
    assert len(tenant_refs) == 1
    assert tenant_refs[0].name == "org"
    assert all(f.name != "tenant_id" for f in membership.fields)


def test_injects_on_tenant_settings_archetype() -> None:
    # TENANT_SETTINGS is per-tenant — it SHOULD receive the injected tenant_id
    # (unlike SETTINGS, which is system-wide). When it carries no pre-existing
    # tenant ref, exactly one tenant_id ref is injected.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("OrgSettings", archetype=ir.ArchetypeKind.TENANT_SETTINGS),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    org_settings = next(e for e in out if e.name == "OrgSettings")
    tid = org_settings.fields[0]
    assert tid.name == "tenant_id"
    assert tid.type.kind == ir.FieldTypeKind.REF
    assert tid.type.ref_entity == "Workspace"
    tenant_refs = [
        f
        for f in org_settings.fields
        if f.type.kind == ir.FieldTypeKind.REF and f.type.ref_entity == "Workspace"
    ]
    assert len(tenant_refs) == 1
