#!/usr/bin/env python3
"""Test linker implementation."""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.errors import LinkError
from dazzle.core.linker_impl import build_symbol_table, resolve_dependencies, validate_references


def test_dependency_resolution():
    """Test basic dependency resolution."""
    print("Testing dependency resolution...")

    # Create modules: A, B (uses A), C (uses B, A)
    mod_a = ir.ModuleIR(
        name="mod.a",
        file=Path("a.dsl"),
        uses=[],
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="EntityA",
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                            modifiers=[ir.FieldModifier.PK],
                        )
                    ],
                )
            ]
        ),
    )

    mod_b = ir.ModuleIR(
        name="mod.b",
        file=Path("b.dsl"),
        uses=["mod.a"],
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="EntityB",
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                            modifiers=[ir.FieldModifier.PK],
                        ),
                        ir.FieldSpec(
                            name="ref_a",
                            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="EntityA"),
                            modifiers=[ir.FieldModifier.REQUIRED],
                        ),
                    ],
                )
            ]
        ),
    )

    mod_c = ir.ModuleIR(
        name="mod.c", file=Path("c.dsl"), uses=["mod.a", "mod.b"], fragment=ir.ModuleFragment()
    )

    # Resolve dependencies
    sorted_mods = resolve_dependencies([mod_c, mod_b, mod_a])

    # Should be in order: A, B, C
    assert sorted_mods[0].name == "mod.a"
    assert sorted_mods[1].name == "mod.b"
    assert sorted_mods[2].name == "mod.c"

    print("  ✓ Dependencies resolved correctly")


def test_circular_dependency_detection():
    """Test circular dependency detection."""
    print("Testing circular dependency detection...")

    # Create circular dependency: A uses B, B uses A
    mod_a = ir.ModuleIR(
        name="mod.a", file=Path("a.dsl"), uses=["mod.b"], fragment=ir.ModuleFragment()
    )

    mod_b = ir.ModuleIR(
        name="mod.b", file=Path("b.dsl"), uses=["mod.a"], fragment=ir.ModuleFragment()
    )

    try:
        resolve_dependencies([mod_a, mod_b])
        raise AssertionError("Should have detected circular dependency")
    except LinkError as e:
        assert "Circular dependency" in str(e)
        print("  ✓ Circular dependency detected")


def test_missing_module_detection():
    """Test missing module detection."""
    print("Testing missing module detection...")

    mod_a = ir.ModuleIR(
        name="mod.a", file=Path("a.dsl"), uses=["mod.nonexistent"], fragment=ir.ModuleFragment()
    )

    try:
        resolve_dependencies([mod_a])
        raise AssertionError("Should have detected missing module")
    except LinkError as e:
        assert "not defined" in str(e)
        print("  ✓ Missing module detected")


def test_duplicate_detection():
    """Test duplicate entity detection."""
    print("Testing duplicate detection...")

    mod_a = ir.ModuleIR(
        name="mod.a",
        file=Path("a.dsl"),
        uses=[],
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="User",
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                            modifiers=[ir.FieldModifier.PK],
                        )
                    ],
                )
            ]
        ),
    )

    mod_b = ir.ModuleIR(
        name="mod.b",
        file=Path("b.dsl"),
        uses=[],
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="User",  # Duplicate!
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                            modifiers=[ir.FieldModifier.PK],
                        )
                    ],
                )
            ]
        ),
    )

    try:
        build_symbol_table([mod_a, mod_b])
        raise AssertionError("Should have detected duplicate entity")
    except LinkError as e:
        assert "Duplicate entity" in str(e)
        print("  ✓ Duplicate entity detected")


def test_reference_validation():
    """Test cross-reference validation."""
    print("Testing reference validation...")

    from dazzle.core.linker_impl import SymbolTable

    symbols = SymbolTable()

    # Add entities
    symbols.add_entity(
        ir.EntitySpec(
            name="User",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                )
            ],
        ),
        "mod.a",
    )

    symbols.add_entity(
        ir.EntitySpec(
            name="Post",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="author",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="NonExistent"),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
            ],
        ),
        "mod.b",
    )

    errors = validate_references(symbols)
    assert len(errors) == 1
    assert "NonExistent" in errors[0]
    print("  ✓ Invalid reference detected")


def test_domain_services_propagated_to_appspec():
    """Domain services declared in any module must reach appspec.domain_services (#1070)."""
    from dazzle.core.linker import build_appspec

    services_mod = ir.ModuleIR(
        name="app.services",
        file=Path("services.dsl"),
        uses=[],
        fragment=ir.ModuleFragment(
            domain_services=[
                ir.DomainServiceSpec(name="calc_workload", kind="domain_logic"),
                ir.DomainServiceSpec(name="send_email", kind="integration"),
            ],
        ),
    )
    root_mod = ir.ModuleIR(
        name="app.core",
        file=Path("app.dsl"),
        uses=[],
        fragment=ir.ModuleFragment(),
    )

    appspec = build_appspec([root_mod, services_mod], "app.core")
    names = {s.name for s in appspec.domain_services}
    assert names == {"calc_workload", "send_email"}, (
        f"Expected both services to reach appspec, got {names}. "
        "Regression of #1070: linker dropped domain_services during merge."
    )
    print("  ✓ Domain services propagated through linker (#1070)")


def test_all_shared_fragment_fields_propagated_to_appspec():
    """Every field on both ModuleFragment AND AppSpec must round-trip through build_appspec (#1075).

    Generalises test_domain_services_propagated_to_appspec to catch the
    full systemic-drops class: any field that exists on both types but
    isn't propagated by the linker pipeline is a silent dropper bug
    (the validator/scorer/renderer reads `[]` or `None` regardless of DSL).
    """
    from dazzle.core.linker import build_appspec

    appspec_fields = set(ir.AppSpec.model_fields.keys())
    fragment_fields = set(ir.ModuleFragment.model_fields.keys())
    shared = appspec_fields & fragment_fields

    # Shape-check: every shared field must appear as `merged_fragment.<field>`
    # in `build_appspec`'s `AppSpec(...)` construction. A grep-based check
    # is sufficient here — the runtime end-to-end is covered by the cycle 121
    # canary test_domain_services_propagated_to_appspec which exercises one
    # real construct against the full parser+linker pipeline.
    import inspect

    build_appspec_src = inspect.getsource(build_appspec)
    missing = []
    for field_name in sorted(shared):
        if f"merged_fragment.{field_name}" not in build_appspec_src:
            missing.append(field_name)

    # These are computed/replaced fields, not direct fragment maps:
    # - entities (extended with auto-generated AIJob / AuditEntry)
    # - surfaces (extended with admin surfaces + auto-archetype surfaces)
    # - workspaces (resolved via navs)
    # - triples (computed)
    # All shared with ModuleFragment but legitimately overridden.
    legitimate_overrides = {"entities", "surfaces", "workspaces"}
    real_drops = [f for f in missing if f not in legitimate_overrides]

    assert not real_drops, (
        f"Linker drops the following shared ModuleFragment/AppSpec fields "
        f"during build_appspec: {real_drops}. Each is silently lost — "
        f"every consumer of AppSpec.{{field}} reads [] or None regardless "
        f"of DSL content. Cycle 128 audit found this; #1075 tracks the fix. "
        f"Add `{{field}}=merged_fragment.{{field}}` to the AppSpec(...) "
        f"construction in src/dazzle/core/linker.py:194 (and the matching "
        f"merge_fragments return in linker_impl.py:1444) for each missing field."
    )
    print(
        f"  ✓ All {len(shared) - len(legitimate_overrides)} shared fields propagated through linker (#1075)"
    )


def main():
    """Run all linker tests."""
    print("=" * 60)
    print("Stage 3: Linker Tests")
    print("=" * 60)
    print()

    try:
        test_dependency_resolution()
        test_circular_dependency_detection()
        test_missing_module_detection()
        test_duplicate_detection()
        test_reference_validation()

        print()
        print("=" * 60)
        print("✅ All Stage 3 linker tests passed!")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Test failed!")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
