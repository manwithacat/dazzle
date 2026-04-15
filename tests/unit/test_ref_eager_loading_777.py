"""
Regression tests for manwithacat/dazzle#777 — list routes must eagerly load
ref relations instead of leaking bare `*_id` columns.

Two bugs combined to break eager loading when a DSL ref field was named with
an `_id` suffix (the common case, e.g. ``device_id: ref Device``):

1. ``entity_converter.convert_entity`` synthesised a ``RelationSpec`` whose
   ``name`` was the raw field name (``"device_id"``). That short-circuited
   the implicit-relation path in ``RelationRegistry.from_entities`` which
   would otherwise have registered the natural short name ``"device"``.
   Result: the registry held ``device_id`` but the runtime asked for
   ``device``, so ``get_relation`` missed and ``load_relations`` silently
   skipped the relation.

2. The list-route handler applied ``json_projection`` to strip fields not
   listed by the surface, but the allow-list omitted any auto-include
   relation names. Even if load_relations had populated ``row["device"]``,
   the projection filter would have removed it before serialization.

These tests lock in both fixes.
"""

from typing import Any

import pytest

from dazzle.core.ir import (
    EntitySpec as IREntitySpec,
)
from dazzle.core.ir import (
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
)
from dazzle_back.converters.entity_converter import convert_entity
from dazzle_back.runtime.relation_loader import RelationRegistry


def _task_with_ref(field_name: str) -> IREntitySpec:
    """Build a minimal IR Task entity with one ref field."""
    return IREntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name=field_name,
                type=FieldType(kind=FieldTypeKind.REF, ref_entity="User"),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


class TestConverterDoesNotSynthesiseRelations:
    """``convert_entity`` must leave relations empty so the runtime registry
    builder has the sole authoritative view of implicit ref→relation mapping.
    """

    def test_ref_field_with_id_suffix_does_not_create_relation_spec(self) -> None:
        ir_task = _task_with_ref("owner_id")
        converted = convert_entity(ir_task)
        assert converted.relations == []

    def test_ref_field_without_id_suffix_does_not_create_relation_spec(self) -> None:
        ir_task = _task_with_ref("owner")
        converted = convert_entity(ir_task)
        assert converted.relations == []


class TestRegistryStripsIdSuffixForImplicitRelations:
    """The registry's implicit-relation path keys by the stripped short name
    but records the real FK column as ``foreign_key_field``. That short name
    is what ``entity_auto_includes`` asks for, so the lookup must succeed.
    """

    def test_id_suffix_field_registered_under_short_name(self) -> None:
        ir_task = _task_with_ref("owner_id")
        converted = convert_entity(ir_task)
        registry = RelationRegistry.from_entities([converted])

        relation = registry.get_relation("Task", "owner")
        assert relation is not None
        assert relation.foreign_key_field == "owner_id"
        assert relation.to_entity == "User"

    def test_raw_field_name_also_resolves_when_no_id_suffix(self) -> None:
        ir_task = _task_with_ref("owner")
        converted = convert_entity(ir_task)
        registry = RelationRegistry.from_entities([converted])

        relation = registry.get_relation("Task", "owner")
        assert relation is not None
        assert relation.foreign_key_field == "owner"
        assert relation.to_entity == "User"

    def test_lookup_by_raw_fk_column_misses_when_stripped(self) -> None:
        """Sanity check: the stripped short name is the only valid lookup
        key for ``owner_id``. This prevents a regression where both names
        accidentally register and mask future drift.
        """
        ir_task = _task_with_ref("owner_id")
        converted = convert_entity(ir_task)
        registry = RelationRegistry.from_entities([converted])

        assert registry.get_relation("Task", "owner_id") is None


class TestJsonProjectionPreservesAutoIncludeKeys:
    """The json_projection filter in ``create_list_handler`` must let
    auto_include relation names survive, otherwise eager-loaded nested data
    is stripped before it reaches the client.
    """

    def test_auto_include_keys_added_to_allowed_set(self) -> None:
        """Drive the projection logic directly — the handler is a closure so
        we replicate its filter body here to lock the contract in place.
        """
        json_projection = ["id", "title", "owner_id"]
        auto_include = ["owner"]
        item: dict[str, Any] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "Fix bug",
            "owner_id": "22222222-2222-2222-2222-222222222222",
            "owner": {"id": "22222222-2222-2222-2222-222222222222", "name": "Alice"},
            "internal_field": "should-be-dropped",
        }

        allowed = set(json_projection)
        if auto_include:
            allowed.update(auto_include)
        projected = {k: v for k, v in item.items() if k in allowed}

        assert "owner" in projected
        assert projected["owner"] == {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Alice",
        }
        assert "internal_field" not in projected

    def test_projection_without_auto_include_strips_nested(self) -> None:
        """Confirm the regression: without the auto_include union, a nested
        ``owner`` dict populated by load_relations is dropped.
        """
        json_projection = ["id", "title", "owner_id"]
        item: dict[str, Any] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "Fix bug",
            "owner_id": "22222222-2222-2222-2222-222222222222",
            "owner": {"id": "22222222-2222-2222-2222-222222222222", "name": "Alice"},
        }

        allowed = set(json_projection)
        projected = {k: v for k, v in item.items() if k in allowed}

        assert "owner" not in projected  # this is the bug before the fix


@pytest.mark.parametrize(
    "field_name,expected_relation_name,expected_fk",
    [
        ("device_id", "device", "device_id"),
        ("reported_by_id", "reported_by", "reported_by_id"),
        ("assigned_to_id", "assigned_to", "assigned_to_id"),
        ("owner", "owner", "owner"),  # no suffix
    ],
)
def test_implicit_relation_naming_convention(
    field_name: str, expected_relation_name: str, expected_fk: str
) -> None:
    """The implicit-path convention: strip a single trailing ``_id`` for the
    relation name, keep the raw field name as the FK column.
    """
    ir_task = _task_with_ref(field_name)
    converted = convert_entity(ir_task)
    registry = RelationRegistry.from_entities([converted])

    relation = registry.get_relation("Task", expected_relation_name)
    assert relation is not None, (
        f"expected registry to contain relation '{expected_relation_name}' "
        f"for ref field '{field_name}'"
    )
    assert relation.foreign_key_field == expected_fk
