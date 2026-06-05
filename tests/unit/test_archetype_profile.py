"""archetype: profile — IR + parser + expander + converter + validation (Plan 3c)."""

from dazzle.core import ir


def test_archetype_kind_has_profile() -> None:
    assert ir.ArchetypeKind.PROFILE == "profile"


def test_entityspec_has_is_profile_default_false() -> None:
    e = ir.EntitySpec(name="X", display_name="X", fields=[])
    assert e.is_profile is False


def test_expander_injects_identity_id_and_sets_is_profile() -> None:
    from dazzle.core.archetype_expander import _expand_profile_archetype

    entity = ir.EntitySpec(
        name="MemberProfile",
        display_name="Member Profile",
        archetype_kind=ir.ArchetypeKind.PROFILE,
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="display_name",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=120),
            ),
        ],
    )
    expanded = _expand_profile_archetype(entity)
    assert expanded.is_profile is True
    idf = next(f for f in expanded.fields if f.name == "identity_id")
    assert idf.type.kind == ir.FieldTypeKind.UUID
    assert idf.is_required is True
    assert idf.is_unique is True  # → tenant-scoped UNIQUE(tenant_id, identity_id)


def test_parser_maps_profile_keyword() -> None:
    from pathlib import Path

    from dazzle.core.dsl_parser_impl import parse_dsl

    src = """module m
app a "A"

entity MemberProfile "Member Profile":
  archetype: profile
  id: uuid pk
  display_name: str(120)
"""
    *_, fragment = parse_dsl(src, Path("test.dsl"))
    prof = next(e for e in fragment.entities if e.name == "MemberProfile")
    assert prof.archetype_kind == ir.ArchetypeKind.PROFILE


def test_profile_without_shared_schema_is_a_validation_error() -> None:
    from dazzle.core.validator import _validate_profile_archetype

    prof = ir.EntitySpec(
        name="MemberProfile",
        display_name="Member Profile",
        archetype_kind=ir.ArchetypeKind.PROFILE,
        is_profile=True,
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            )
        ],
    )
    errors: list[str] = []
    _validate_profile_archetype(prof, None, errors)  # no tenancy → error
    assert any("profile" in e.lower() and "shared_schema" in e.lower() for e in errors)


def test_profile_with_shared_schema_passes_validation() -> None:
    from dazzle.core.validator import _validate_profile_archetype

    prof = ir.EntitySpec(
        name="MemberProfile",
        display_name="Member Profile",
        is_profile=True,
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            )
        ],
    )
    tenancy = ir.TenancySpec(isolation=ir.TenantIsolationSpec(mode=ir.TenancyMode.SHARED_SCHEMA))
    errors: list[str] = []
    _validate_profile_archetype(prof, tenancy, errors)
    assert errors == []
