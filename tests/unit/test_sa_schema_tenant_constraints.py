"""Construction-rule tests for tenant-scoped schema generation (RLS Phase A)."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata


def _e(name: str, *fields: ir.FieldSpec, **kw) -> ir.EntitySpec:
    base = [
        ir.FieldSpec(
            name="id",
            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
            modifiers=[ir.FieldModifier.PK],
        )
    ]
    return ir.EntitySpec(name=name, title=name, fields=base + list(fields), **kw)


def _tid(target: str = "Workspace") -> ir.FieldSpec:
    return ir.FieldSpec(
        name="tenant_id",
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
        modifiers=[ir.FieldModifier.REQUIRED],
    )


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
        modifiers=[ir.FieldModifier.REQUIRED],
    )


def _unique(name: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.STR),
        modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.UNIQUE],
    )


def _md(entities, tenant_scoped):
    conv = convert_entities(entities)
    return build_metadata(conv, partition_key="tenant_id", tenant_scoped=tenant_scoped)


def test_unique_tenant_id_id_emitted() -> None:
    md = _md([_e("Workspace"), _e("Task", _tid())], {"Task"})
    task = md.tables["Task"]
    ucs = [c for c in task.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in uc.columns} == {"tenant_id", "id"} for uc in ucs)


def test_composite_fk_name_matches_engine_render() -> None:
    """#1464: create_all (sa_schema) and the migration engine (schema_render) must
    name the composite tenant-scoped FK IDENTICALLY, so the two provisioning paths
    produce byte-identical constraint names (not just identical structure) — an
    engine DROP/downgrade against a create_all DB would otherwise target a name
    that doesn't exist."""
    from dazzle.db.schema_render import _fk_name

    ents = [_e("Workspace"), _e("Member", _tid()), _e("Project", _tid(), _ref("owner", "Member"))]
    md = _md(ents, {"Member", "Project"})
    project = md.tables["Project"]
    composite = next(fk for fk in project.foreign_key_constraints if len(fk.elements) == 2)
    # sa_schema declares the FK columns as (partition_key, field); the engine snapshot
    # preserves that order, so _fk_name over the same tuple must reproduce the name.
    assert composite.name == _fk_name("Project", ("tenant_id", "owner"))
    assert composite.name == "fk_Project_tenant_id_owner"


def test_intra_tenant_ref_is_composite_fk() -> None:
    ents = [_e("Workspace"), _e("Project", _tid()), _e("Task", _tid(), _ref("project", "Project"))]
    md = _md(ents, {"Project", "Task"})
    task = md.tables["Task"]
    composite = [fk for fk in task.foreign_key_constraints if len(fk.elements) == 2]
    cols = {tuple(e.parent.name for e in fk.elements) for fk in composite}
    assert ("tenant_id", "project") in cols
    # the single-column FK on `project` is suppressed (only the composite remains)
    single = [
        fk
        for fk in task.foreign_key_constraints
        if len(fk.elements) == 1 and fk.elements[0].parent.name == "project"
    ]
    assert not single


def test_ref_to_global_entity_stays_single_column() -> None:
    ents = [_e("Workspace"), _e("Currency"), _e("Task", _tid(), _ref("currency", "Currency"))]
    md = _md(ents, {"Task"})  # Currency NOT tenant-scoped
    task = md.tables["Task"]
    single = [
        fk
        for fk in task.foreign_key_constraints
        if len(fk.elements) == 1 and fk.elements[0].parent.name == "currency"
    ]
    assert single


def test_author_unique_is_tenant_scoped() -> None:
    md = _md([_e("Workspace"), _e("Member", _tid(), _unique("email"))], {"Member"})
    member = md.tables["Member"]
    # the email column is NOT globally unique; a (tenant_id, email) unique exists
    assert not member.c.email.unique
    ucs = [c for c in member.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in uc.columns} == {"tenant_id", "email"} for uc in ucs)


def test_tenant_id_leading_index() -> None:
    md = _md([_e("Workspace"), _e("Task", _tid())], {"Task"})
    task = md.tables["Task"]
    assert any(list(ix.columns)[0].name == "tenant_id" for ix in task.indexes)


def test_non_tenant_app_unchanged() -> None:
    # partition_key/tenant_scoped omitted → identical to today's output.
    md = build_metadata(convert_entities([_e("Thing", _unique("sku"))]))
    thing = md.tables["Thing"]
    assert thing.c.sku.unique  # global uniqueness preserved when not tenant-scoped


def _composite_fk_to(table, target_col: str):
    """Return the 2-element FK constraint on ``table`` whose child cols include
    ``target_col``, or None."""
    for fkc in table.foreign_key_constraints:
        if len(fkc.elements) == 2 and any(e.parent.name == target_col for e in fkc.elements):
            return fkc
    return None


def test_self_ref_composite_fk_uses_alter() -> None:
    # A tenant-scoped entity that references itself: the composite FK must be
    # deferred via use_alter so create_all stays orderable.
    ents = [_e("Workspace"), _e("Category", _tid(), _ref("parent", "Category"))]
    md = _md(ents, {"Category"})
    category = md.tables["Category"]
    fkc = _composite_fk_to(category, "parent")
    assert fkc is not None
    cols = {e.parent.name for e in fkc.elements}
    assert cols == {"tenant_id", "parent"}
    assert fkc.use_alter is True
    # orderable despite the self-ref cycle
    assert [t.name for t in md.sorted_tables]


def test_circular_intra_tenant_pair_uses_alter() -> None:
    # A → B and B → A, both tenant-scoped. Both composite FKs must be deferred
    # and metadata.sorted_tables must not raise (orderable).
    ents = [
        _e("Workspace"),
        _e("A", _tid(), _ref("b", "B")),
        _e("B", _tid(), _ref("a", "A")),
    ]
    md = _md(ents, {"A", "B"})

    fk_a = _composite_fk_to(md.tables["A"], "b")
    fk_b = _composite_fk_to(md.tables["B"], "a")
    assert fk_a is not None and fk_b is not None
    assert {e.parent.name for e in fk_a.elements} == {"tenant_id", "b"}
    assert {e.parent.name for e in fk_b.elements} == {"tenant_id", "a"}
    assert fk_a.use_alter is True
    assert fk_b.use_alter is True

    # The cycle must not deadlock topological sort.
    assert [t.name for t in md.sorted_tables]
