"""Unit tests for framework-owned partition-key injection (RLS tenancy Phase A)."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.tenancy_inject import inject_partition_key


def _entity(
    name: str,
    *fields: ir.FieldSpec,
    is_tenant_root: bool = False,
    archetype: ir.ArchetypeKind | None = None,
    domain: str | None = None,
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
        domain=domain,
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


def test_skips_membership_archetype_with_tenant_ref_under_different_name() -> None:
    # A USER_MEMBERSHIP archetype keeps its per-app-named tenant ref (e.g. `org`)
    # and must NOT get a second tenant_id injected. #1461: this by-target skip is
    # scoped to USER_MEMBERSHIP — it must NOT apply to plain data entities (see
    # test_injects_on_leaf_entity_with_direct_tenant_ref below).
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("Membership", _ref("org", "Workspace"), archetype=ir.ArchetypeKind.USER_MEMBERSHIP),
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


def test_injects_on_leaf_entity_with_direct_tenant_ref() -> None:
    # #1461 regression: a plain (non-membership) data entity that declares a DIRECT
    # `ref <TenantRoot>` must STILL get tenant_id injected — a direct root ref is
    # just another path to root, not a reason to leave the entity unfenced. The old
    # over-broad `has_tenant_ref` skip silently left such entities unfenced (no
    # tenant_id, RLS off) → cross-tenant exposure.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("Agreement", _ref("workspace", "Workspace")),  # CUSTOM leaf, direct root ref
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    agreement = next(e for e in out if e.name == "Agreement")
    # tenant_id injected as the first field (so it IS fenced downstream)
    assert agreement.fields[0].name == "tenant_id"
    assert agreement.fields[0].type.ref_entity == "Workspace"
    # the author's own direct ref is preserved alongside it
    assert any(f.name == "workspace" for f in agreement.fields)


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


def test_injects_on_profile_archetype() -> None:
    # PROFILE is per-member, tenant-scoped (its archetype docstring states Phase A
    # injects tenant_id) — it MUST receive the discriminator so the downstream
    # UNIQUE(tenant_id, identity_id) + RLS fence hold. #1461: the narrowed skip
    # predicate (USER_MEMBERSHIP-only) must NOT skip PROFILE.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("MemberProfile", archetype=ir.ArchetypeKind.PROFILE),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    profile = next(e for e in out if e.name == "MemberProfile")
    assert profile.fields[0].name == "tenant_id"
    assert profile.fields[0].type.ref_entity == "Workspace"


def test_skips_platform_domain_entities() -> None:
    # Framework/platform entities (AIJob, AuditEntry, admin, …) are cross-tenant
    # by design and managed by the framework — they must never be auto-fenced,
    # while ordinary user-domain entities still get tenant_id.
    entities = [
        _entity("Workspace", is_tenant_root=True),
        _entity("AuditEntry", domain="platform"),
        _entity("Task"),
    ]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    by_name = {e.name: e for e in out}
    assert all(f.name != "tenant_id" for f in by_name["AuditEntry"].fields)
    assert by_name["Task"].fields[0].name == "tenant_id"
