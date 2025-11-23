"""Test the 4 quick win implementations from gap analysis."""

import pytest
from pathlib import Path

from dazzle.core import ir
from dazzle.core import patterns
from dazzle.core.linker_impl import validate_module_access, build_symbol_table


def test_type_catalog():
    """Test type_catalog property on AppSpec."""
    # Create simple AppSpec with entities
    entity1 = ir.EntitySpec(
        name="User",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="name", type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200)),
            ir.FieldSpec(name="created_at", type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME)),
        ]
    )

    entity2 = ir.EntitySpec(
        name="Post",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200)),
            ir.FieldSpec(name="created_at", type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME)),
        ]
    )

    appspec = ir.AppSpec(
        name="test_app",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[entity1, entity2]),
    )

    catalog = appspec.type_catalog

    assert "id" in catalog, "Should have 'id' field"
    assert "name" in catalog, "Should have 'name' field"
    assert "title" in catalog, "Should have 'title' field"
    assert "created_at" in catalog, "Should have 'created_at' field"

    # Check that id has UUID type
    id_types = catalog["id"]
    assert len(id_types) == 1, "id should have 1 type"
    assert id_types[0].kind == ir.FieldTypeKind.UUID, "id should be UUID"

    # Check conflicts
    conflicts = appspec.get_field_type_conflicts()
    assert len(conflicts) == 0, "Should have no conflicts (all fields consistent)"
    assert len(catalog) == 4  # id, name, title, created_at


def test_type_catalog_detects_conflicts():
    """Test that type_catalog detects conflicting field types."""
    entity1 = ir.EntitySpec(
        name="User",
        fields=[
            ir.FieldSpec(name="status", type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=50)),
        ]
    )

    entity2 = ir.EntitySpec(
        name="Task",
        fields=[
            ir.FieldSpec(name="status", type=ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=["todo", "done"])),
        ]
    )

    appspec = ir.AppSpec(
        name="test_app",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[entity1, entity2]),
    )

    # Type catalog should show both types for 'status'
    catalog = appspec.type_catalog
    assert "status" in catalog
    assert len(catalog["status"]) == 2  # STR and ENUM

    # Should detect conflict
    conflicts = appspec.get_field_type_conflicts()
    assert len(conflicts) > 0, "Should detect type conflict for 'status' field"
    # Conflicts is a list of error strings, check if any mention 'status'
    assert any("status" in err for err in conflicts), "Conflict message should mention 'status'"


def test_module_access_validation():
    """Test stricter use validation."""
    # Create modules with references
    module1 = ir.ModuleIR(
        name="app.core",
        file=Path("app.dsl"),
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(name="User", fields=[])
            ]
        )
    )

    module2 = ir.ModuleIR(
        name="app.posts",
        file=Path("posts.dsl"),
        uses=["app.core"],  # Explicitly uses app.core
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="Post",
                    fields=[
                        ir.FieldSpec(
                            name="author",
                            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User")
                        )
                    ]
                )
            ]
        )
    )

    # Build symbol table
    symbols = build_symbol_table([module1, module2])

    # Validate module access - should pass since module2 uses module1
    errors = validate_module_access([module1, module2], symbols)
    assert len(errors) == 0, f"Should have no errors with proper use declaration, got: {errors}"


def test_module_access_validation_detects_missing_use():
    """Test that module access validation detects missing use declarations."""
    # Create modules where module2 references module1 WITHOUT declaring 'use'
    module1 = ir.ModuleIR(
        name="app.core",
        file=Path("app.dsl"),
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(name="User", fields=[])
            ]
        )
    )

    module2 = ir.ModuleIR(
        name="app.posts",
        file=Path("posts.dsl"),
        uses=[],  # NOT using app.core
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="Post",
                    fields=[
                        ir.FieldSpec(
                            name="author",
                            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User")
                        )
                    ]
                )
            ]
        )
    )

    # Build symbol table
    symbols = build_symbol_table([module1, module2])

    # Validate module access - should fail since module2 doesn't declare 'use app.core'
    errors = validate_module_access([module1, module2], symbols)
    assert len(errors) > 0, "Should detect missing 'use' declaration"
    assert "app.core" in errors[0], "Error should mention app.core module"


def test_pattern_detection_crud():
    """Test CRUD pattern detection."""
    # Create AppSpec with complete CRUD pattern
    task_entity = ir.EntitySpec(name="Task", fields=[])

    appspec = ir.AppSpec(
        name="test_app",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[task_entity]),
        surfaces=[
            ir.SurfaceSpec(name="task_list", entity_ref="Task", mode=ir.SurfaceMode.LIST),
            ir.SurfaceSpec(name="task_create", entity_ref="Task", mode=ir.SurfaceMode.CREATE),
            ir.SurfaceSpec(name="task_detail", entity_ref="Task", mode=ir.SurfaceMode.VIEW),
            ir.SurfaceSpec(name="task_edit", entity_ref="Task", mode=ir.SurfaceMode.EDIT),
        ]
    )

    # Detect CRUD patterns
    crud_patterns = patterns.detect_crud_patterns(appspec)

    assert len(crud_patterns) == 1, "Should detect 1 CRUD pattern"
    assert crud_patterns[0].entity_name == "Task", "Pattern should be for Task entity"
    assert crud_patterns[0].is_complete, "CRUD pattern should be complete"
    assert crud_patterns[0].has_list, "Should have list surface"
    assert crud_patterns[0].has_create, "Should have create surface"
    assert crud_patterns[0].has_detail, "Should have detail surface"
    assert crud_patterns[0].has_edit, "Should have edit surface"


def test_pattern_detection_incomplete_crud():
    """Test detection of incomplete CRUD patterns."""
    task_entity = ir.EntitySpec(name="Task", fields=[])

    appspec = ir.AppSpec(
        name="test_app",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[task_entity]),
        surfaces=[
            ir.SurfaceSpec(name="task_list", entity_ref="Task", mode=ir.SurfaceMode.LIST),
            ir.SurfaceSpec(name="task_detail", entity_ref="Task", mode=ir.SurfaceMode.VIEW),
            # Missing create and edit
        ]
    )

    crud_patterns = patterns.detect_crud_patterns(appspec)

    assert len(crud_patterns) == 1, "Should still detect partial CRUD pattern"
    assert not crud_patterns[0].is_complete, "CRUD pattern should be incomplete"
    assert crud_patterns[0].has_list, "Should have list surface"
    assert not crud_patterns[0].has_create, "Should not have create surface"


def test_pattern_analysis():
    """Test comprehensive pattern analysis."""
    task_entity = ir.EntitySpec(name="Task", fields=[])

    appspec = ir.AppSpec(
        name="test_app",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[task_entity]),
        surfaces=[
            ir.SurfaceSpec(name="task_list", entity_ref="Task", mode=ir.SurfaceMode.LIST),
            ir.SurfaceSpec(name="task_create", entity_ref="Task", mode=ir.SurfaceMode.CREATE),
            ir.SurfaceSpec(name="task_detail", entity_ref="Task", mode=ir.SurfaceMode.VIEW),
            ir.SurfaceSpec(name="task_edit", entity_ref="Task", mode=ir.SurfaceMode.EDIT),
        ]
    )

    # Analyze all patterns
    all_patterns = patterns.analyze_patterns(appspec)

    assert "crud" in all_patterns, "Should have CRUD patterns"
    assert "integrations" in all_patterns, "Should have integration patterns"
    assert "experiences" in all_patterns, "Should have experience patterns"

    # Test report formatting
    report = patterns.format_pattern_report(all_patterns)
    assert "Task" in report, "Report should mention Task entity"
    assert "Complete CRUD" in report, "Report should show complete CRUD"
