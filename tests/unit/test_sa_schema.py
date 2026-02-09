"""
Tests for EntitySpec -> SQLAlchemy MetaData bridge.

Verifies type mapping, FK handling, self-references, and topological ordering.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, Text

from dazzle_back.runtime.sa_schema import (
    _field_type_to_sa,
    _scalar_type_to_sa,
    build_metadata,
)
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# =============================================================================
# Helpers
# =============================================================================


def _entity(name: str, fields: list[FieldSpec]) -> EntitySpec:
    """Shorthand for creating an EntitySpec."""
    return EntitySpec(name=name, fields=fields)


def _field(name: str, kind: str = "scalar", scalar_type: ScalarType | None = None, **kwargs):
    """Shorthand for creating a FieldSpec."""
    ft_kwargs = {"kind": kind}
    if scalar_type:
        ft_kwargs["scalar_type"] = scalar_type
    ft_kwargs.update({k: v for k, v in kwargs.items() if k in ("ref_entity", "enum_values")})
    field_kwargs = {k: v for k, v in kwargs.items() if k not in ("ref_entity", "enum_values")}
    return FieldSpec(name=name, type=FieldType(**ft_kwargs), **field_kwargs)


# =============================================================================
# Type Mapping Tests
# =============================================================================


class TestScalarTypeMapping:
    """Test DSL scalar type -> SA type mapping."""

    def test_str_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.STR), Text)

    def test_int_maps_to_integer(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.INT), Integer)

    def test_decimal_maps_to_float(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.DECIMAL), Float)

    def test_bool_maps_to_boolean(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.BOOL), Boolean)

    def test_date_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.DATE), Text)

    def test_datetime_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.DATETIME), Text)

    def test_uuid_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.UUID), Text)

    def test_email_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.EMAIL), Text)

    def test_json_maps_to_text(self):
        assert isinstance(_scalar_type_to_sa(ScalarType.JSON), Text)


class TestFieldTypeMapping:
    """Test FieldType -> SA type mapping."""

    def test_enum_maps_to_text(self):
        ft = FieldType(kind="enum", enum_values=["a", "b"])
        assert isinstance(_field_type_to_sa(ft), Text)

    def test_ref_maps_to_text(self):
        ft = FieldType(kind="ref", ref_entity="Foo")
        assert isinstance(_field_type_to_sa(ft), Text)

    def test_scalar_str(self):
        ft = FieldType(kind="scalar", scalar_type=ScalarType.STR)
        assert isinstance(_field_type_to_sa(ft), Text)


# =============================================================================
# build_metadata Tests
# =============================================================================


class TestBuildMetadata:
    """Test build_metadata() output."""

    def test_single_entity_creates_table(self):
        entities = [
            _entity(
                "Task",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("title", scalar_type=ScalarType.STR, required=True),
                ],
            )
        ]
        metadata = build_metadata(entities)
        assert "Task" in metadata.tables
        table = metadata.tables["Task"]
        col_names = {c.name for c in table.columns}
        assert "id" in col_names
        assert "title" in col_names

    def test_auto_id_column_when_missing(self):
        entities = [
            _entity(
                "Note",
                [
                    _field("content", scalar_type=ScalarType.TEXT),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Note"]
        col_names = {c.name for c in table.columns}
        assert "id" in col_names
        # The auto-added id should be a primary key
        id_col = table.c.id
        assert id_col.primary_key

    def test_primary_key_on_id_field(self):
        entities = [
            _entity(
                "Task",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Task"]
        assert table.c.id.primary_key

    def test_required_field_is_not_nullable(self):
        entities = [
            _entity(
                "Task",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("title", scalar_type=ScalarType.STR, required=True),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Task"]
        assert table.c.title.nullable is False

    def test_optional_field_is_nullable(self):
        entities = [
            _entity(
                "Task",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("notes", scalar_type=ScalarType.TEXT),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Task"]
        assert table.c.notes.nullable is True

    def test_unique_field(self):
        entities = [
            _entity(
                "User",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("email", scalar_type=ScalarType.EMAIL, unique=True),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["User"]
        assert table.c.email.unique is True


# =============================================================================
# Foreign Key Tests
# =============================================================================


class TestForeignKeys:
    """Test FK constraint generation."""

    def test_ref_field_creates_foreign_key(self):
        entities = [
            _entity("Client", [_field("id", scalar_type=ScalarType.UUID)]),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="Client"),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Invoice"]
        fks = list(table.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "Client.id"

    def test_self_reference_uses_use_alter(self):
        entities = [
            _entity(
                "Employee",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("manager", kind="ref", ref_entity="Employee"),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Employee"]
        fks = list(table.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "Employee.id"
        assert fks[0].use_alter is True

    def test_ref_to_unknown_entity_no_fk(self):
        """A ref to an entity not in the list should not create a FK constraint."""
        entities = [
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="UnknownEntity"),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Invoice"]
        fks = list(table.foreign_keys)
        assert len(fks) == 0


# =============================================================================
# Topological Ordering Tests
# =============================================================================


class TestTopologicalOrdering:
    """Test that sorted_tables respects FK dependencies."""

    def test_sorted_tables_parent_before_child(self):
        """Parent table should come before child in sorted order."""
        entities = [
            # Intentionally put child first
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="Client"),
                ],
            ),
            _entity(
                "Client",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("name", scalar_type=ScalarType.STR),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        sorted_names = [t.name for t in metadata.sorted_tables]
        assert sorted_names.index("Client") < sorted_names.index("Invoice")

    def test_sorted_tables_multi_level(self):
        """Multi-level dependencies: A -> B -> C should sort C, B, A."""
        entities = [
            _entity(
                "LineItem",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("invoice", kind="ref", ref_entity="Invoice"),
                ],
            ),
            _entity(
                "Invoice",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("client", kind="ref", ref_entity="Client"),
                ],
            ),
            _entity(
                "Client",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        sorted_names = [t.name for t in metadata.sorted_tables]
        assert sorted_names.index("Client") < sorted_names.index("Invoice")
        assert sorted_names.index("Invoice") < sorted_names.index("LineItem")

    def test_independent_tables_all_present(self):
        """Tables with no FK deps should all appear in sorted output."""
        entities = [
            _entity("Alpha", [_field("id", scalar_type=ScalarType.UUID)]),
            _entity("Beta", [_field("id", scalar_type=ScalarType.UUID)]),
            _entity("Gamma", [_field("id", scalar_type=ScalarType.UUID)]),
        ]
        metadata = build_metadata(entities)
        sorted_names = [t.name for t in metadata.sorted_tables]
        assert set(sorted_names) == {"Alpha", "Beta", "Gamma"}

    def test_self_reference_does_not_break_sort(self):
        """Self-referencing entity should still appear in sorted output."""
        entities = [
            _entity(
                "Category",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("parent", kind="ref", ref_entity="Category"),
                ],
            ),
        ]
        metadata = build_metadata(entities)
        sorted_names = [t.name for t in metadata.sorted_tables]
        assert "Category" in sorted_names


# =============================================================================
# Enum Field Tests
# =============================================================================


class TestEnumFields:
    """Test enum field handling."""

    def test_enum_field_maps_to_text_column(self):
        entities = [
            _entity(
                "Task",
                [
                    _field("id", scalar_type=ScalarType.UUID),
                    _field("status", kind="enum", enum_values=["pending", "done"]),
                ],
            )
        ]
        metadata = build_metadata(entities)
        table = metadata.tables["Task"]
        assert isinstance(table.c.status.type, Text)
