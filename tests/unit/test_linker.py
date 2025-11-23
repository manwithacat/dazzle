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
