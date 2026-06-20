"""
Tests for composite (scope, default-sort) index emission on list surfaces.

Covers #1202 — the schema builder now accepts the AppSpec's surfaces and
emits one composite b-tree index per ``list``-mode surface that declares
a ``ux.sort``. The index is named ``ix_list_<entity>_<scope>_<sort>`` and
covers ``(scope_column, sort_column)``.

The benchmark in ``benchmarks/`` measured single-column ``tenant_id`` and
FK indexes as noise; the composite is the lever the schema builder ought
to be turning. These tests pin the emission behaviour so it does not
regress.
"""

from __future__ import annotations

from dazzle.core.access import AccessOperationKind, ScopeRuleSpec
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.ux import SortSpec, UXSpec
from dazzle.http.runtime.sa_schema import _list_index_specs, build_metadata
from dazzle.http.specs.entity import (
    EntityAccessSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

# =============================================================================
# Helpers
# =============================================================================


def _field(name: str, scalar: ScalarType = ScalarType.STR, required: bool = False) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=FieldType(kind="scalar", scalar_type=scalar),
        required=required,
    )


def _scope_rule(predicate: object) -> ScopeRuleSpec:
    return ScopeRuleSpec(
        operation=AccessOperationKind.READ,
        condition=None,
        personas=["*"],
        predicate=predicate,
    )


def _entity_with_tenant_scope(name: str = "Invoice") -> EntitySpec:
    """Entity with a tenant_id-scoped read rule (UserAttrCheck)."""
    return EntitySpec(
        name=name,
        fields=[
            _field("id", ScalarType.UUID),
            _field("tenant_id", ScalarType.UUID, required=True),
            _field("created_at", ScalarType.DATETIME, required=True),
            _field("status", ScalarType.STR),
        ],
        access=EntityAccessSpec(
            scopes=[_scope_rule(UserAttrCheck(field="tenant_id", op=CompOp.EQ, user_attr="tenant"))]
        ),
    )


def _list_surface(
    name: str,
    entity_ref: str,
    sort_field: str | None = "created_at",
    sort_direction: str = "desc",
) -> SurfaceSpec:
    ux_kwargs: dict[str, object] = {}
    if sort_field is not None:
        ux_kwargs["sort"] = [SortSpec(field=sort_field, direction=sort_direction)]
    return SurfaceSpec(
        name=name,
        entity_ref=entity_ref,
        mode=SurfaceMode.LIST,
        ux=UXSpec(**ux_kwargs),
    )


# =============================================================================
# Index name & column emission
# =============================================================================


def test_tenant_scope_with_created_at_sort_emits_composite_index() -> None:
    """The headline #1202 case — tenant_id scope + created_at sort."""
    entity = _entity_with_tenant_scope("Invoice")
    surface = _list_surface("invoice_list", "Invoice", sort_field="created_at")

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["Invoice"]

    index_names = {idx.name for idx in table.indexes}
    assert "ix_list_Invoice_tenant_id_created_at" in index_names

    target = next(
        idx for idx in table.indexes if idx.name == "ix_list_Invoice_tenant_id_created_at"
    )
    cols = [c.name for c in target.columns]
    assert cols == ["tenant_id", "created_at"]


def test_column_check_scope_extracted_correctly() -> None:
    """ColumnCheck (e.g. `status = "active"` as the first scope branch)
    yields the column anchor when it's the first scope rule.
    """
    entity = EntitySpec(
        name="Task",
        fields=[
            _field("id", ScalarType.UUID),
            _field("status", ScalarType.STR, required=True),
            _field("created_at", ScalarType.DATETIME),
        ],
        access=EntityAccessSpec(
            scopes=[
                _scope_rule(
                    ColumnCheck(
                        field="status",
                        op=CompOp.EQ,
                        value=ValueRef(literal="active"),
                    )
                )
            ]
        ),
    )
    surface = _list_surface("task_list", "Task", sort_field="created_at")

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["Task"]
    names = {idx.name for idx in table.indexes}
    assert "ix_list_Task_status_created_at" in names


# =============================================================================
# Negative paths — silently skipped
# =============================================================================


def test_no_list_surface_no_extra_index() -> None:
    """Entity without any list surface gets no list indexes — only PK."""
    entity = _entity_with_tenant_scope("Invoice")

    metadata = build_metadata([entity], surfaces=[])
    table = metadata.tables["Invoice"]

    list_indexes = [idx for idx in table.indexes if idx.name.startswith("ix_list_")]
    assert list_indexes == []


def test_surface_without_ux_sort_is_skipped() -> None:
    """A list surface that declares no ``ux.sort`` produces no list index."""
    entity = _entity_with_tenant_scope("Invoice")
    surface = _list_surface("invoice_list", "Invoice", sort_field=None)

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["Invoice"]

    list_indexes = [idx for idx in table.indexes if idx.name.startswith("ix_list_")]
    assert list_indexes == []


def test_non_list_surface_skipped() -> None:
    """An edit/create/view surface — even with ``ux.sort`` — is skipped."""
    entity = _entity_with_tenant_scope("Invoice")
    surface = SurfaceSpec(
        name="invoice_edit",
        entity_ref="Invoice",
        mode=SurfaceMode.EDIT,
        ux=UXSpec(sort=[SortSpec(field="created_at", direction="desc")]),
    )

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["Invoice"]
    list_indexes = [idx for idx in table.indexes if idx.name.startswith("ix_list_")]
    assert list_indexes == []


def test_tautology_scope_is_skipped() -> None:
    """An entity whose only scope is Tautology has no column anchor."""
    entity = EntitySpec(
        name="PublicNote",
        fields=[
            _field("id", ScalarType.UUID),
            _field("created_at", ScalarType.DATETIME),
        ],
        access=EntityAccessSpec(scopes=[_scope_rule(Tautology())]),
    )
    surface = _list_surface("note_list", "PublicNote", sort_field="created_at")

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["PublicNote"]
    list_indexes = [idx for idx in table.indexes if idx.name.startswith("ix_list_")]
    assert list_indexes == []


# =============================================================================
# De-duplication & multi-surface cases
# =============================================================================


def test_two_surfaces_with_same_scope_sort_pair_deduped() -> None:
    """Two list surfaces sharing the same (scope, sort) pair emit one index."""
    entity = _entity_with_tenant_scope("Invoice")
    surface_a = _list_surface("invoice_list", "Invoice", sort_field="created_at")
    surface_b = _list_surface("invoice_recent", "Invoice", sort_field="created_at")

    metadata = build_metadata([entity], surfaces=[surface_a, surface_b])
    table = metadata.tables["Invoice"]

    matching = [idx for idx in table.indexes if idx.name == "ix_list_Invoice_tenant_id_created_at"]
    assert len(matching) == 1


def test_bool_composite_scope_extracts_first_column_anchor() -> None:
    """AND composite with a tenant_id branch and a status branch.

    The first column-anchored child wins. The composite shape is the
    common one for multi-tenancy + status gating.
    """
    entity = EntitySpec(
        name="Ticket",
        fields=[
            _field("id", ScalarType.UUID),
            _field("tenant_id", ScalarType.UUID, required=True),
            _field("status", ScalarType.STR),
            _field("created_at", ScalarType.DATETIME),
        ],
        access=EntityAccessSpec(
            scopes=[
                _scope_rule(
                    BoolComposite(
                        op=BoolOp.AND,
                        children=[
                            UserAttrCheck(field="tenant_id", op=CompOp.EQ, user_attr="tenant"),
                            ColumnCheck(
                                field="status",
                                op=CompOp.NEQ,
                                value=ValueRef(literal="archived"),
                            ),
                        ],
                    )
                )
            ]
        ),
    )
    surface = _list_surface("ticket_list", "Ticket", sort_field="created_at")

    metadata = build_metadata([entity], surfaces=[surface])
    table = metadata.tables["Ticket"]
    names = {idx.name for idx in table.indexes}
    assert "ix_list_Ticket_tenant_id_created_at" in names


# =============================================================================
# Default-None preserves prior behaviour
# =============================================================================


def test_default_none_surfaces_arg_emits_no_list_indexes() -> None:
    """build_metadata(entities) without surfaces — historical call shape —
    must produce zero list indexes."""
    entity = _entity_with_tenant_scope("Invoice")
    metadata = build_metadata([entity])
    table = metadata.tables["Invoice"]
    list_indexes = [idx for idx in table.indexes if idx.name.startswith("ix_list_")]
    assert list_indexes == []


# =============================================================================
# _list_index_specs helper — direct shape checks
# =============================================================================


def test_list_index_specs_returns_tuples_keyed_by_entity() -> None:
    entity = _entity_with_tenant_scope("Invoice")
    surface = _list_surface("invoice_list", "Invoice", sort_field="created_at")
    result = _list_index_specs([entity], [surface])
    assert "Invoice" in result
    assert result["Invoice"] == [
        ("ix_list_Invoice_tenant_id_created_at", "tenant_id", "created_at"),
    ]


def test_list_index_specs_none_surfaces_returns_empty() -> None:
    entity = _entity_with_tenant_scope("Invoice")
    assert _list_index_specs([entity], None) == {}


def test_list_index_specs_skips_unknown_entity_ref() -> None:
    """Surface referencing an entity that isn't in the entities list."""
    entity = _entity_with_tenant_scope("Invoice")
    surface = _list_surface("orphan_list", "DoesNotExist", sort_field="created_at")
    assert _list_index_specs([entity], [surface]) == {}
