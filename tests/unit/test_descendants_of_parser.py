"""#1227 Phase 3b — parser + validator for `descendants_of` / `ancestors_of`.

Runtime resolution (recursive CTE) lands in slice 3b.ii. This slice pins:

1. `descendants_of self via parent_department` parses into
   FieldType(kind=DESCENDANTS_OF, via_field='parent_department').
2. `descendants_of self via ManagerLink.manager` parses into
   FieldType(kind=DESCENDANTS_OF, via_entity='ManagerLink', via_field='manager').
3. Same shapes for `ancestors_of`.
4. Bare `descendants_of self` (no via) raises ParseError.
5. Non-self anchor raises ParseError.
6. validate_entities catches: via field doesn't exist; via field isn't a
   self-ref; junction missing; junction missing parent FK; junction missing
   second `ref Host` field (needed to name the child set).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.validator import validate_entities


def _parse(dsl: str):
    _, _, _, _, _, frag = parse_dsl(dsl, Path("test.dz"))
    return frag


class TestDescendantsOfParses:
    def test_self_ref_via(self) -> None:
        frag = _parse("""\
module test.core
app a "A"

entity Department "Department":
  id: uuid pk
  parent_department: ref Department
  all_descendants: descendants_of self via parent_department
""")
        dept = next(e for e in frag.entities if e.name == "Department")
        f = next(f for f in dept.fields if f.name == "all_descendants")
        assert f.type.kind == ir.FieldTypeKind.DESCENDANTS_OF
        assert f.type.via_field == "parent_department"
        assert f.type.via_entity is None
        assert f.type.ref_entity is None

    def test_junction_qualified_via(self) -> None:
        frag = _parse("""\
module test.core
app a "A"

entity Person "Person":
  id: uuid pk
  all_reports: descendants_of self via ManagerLink.manager

entity ManagerLink "ManagerLink":
  id: uuid pk
  manager: ref Person required
  report: ref Person required
""")
        person = next(e for e in frag.entities if e.name == "Person")
        f = next(f for f in person.fields if f.name == "all_reports")
        assert f.type.kind == ir.FieldTypeKind.DESCENDANTS_OF
        assert f.type.via_entity == "ManagerLink"
        assert f.type.via_field == "manager"

    def test_ancestors_of_self_ref(self) -> None:
        frag = _parse("""\
module test.core
app a "A"

entity Department "Department":
  id: uuid pk
  parent_department: ref Department
  ancestor_chain: ancestors_of self via parent_department
""")
        dept = next(e for e in frag.entities if e.name == "Department")
        f = next(f for f in dept.fields if f.name == "ancestor_chain")
        assert f.type.kind == ir.FieldTypeKind.ANCESTORS_OF
        assert f.type.via_field == "parent_department"

    def test_without_via_raises(self) -> None:
        with pytest.raises(ParseError, match="requires `via"):
            _parse("""\
module test.core
app a "A"

entity Department "Department":
  id: uuid pk
  all_descendants: descendants_of self
""")

    def test_non_self_anchor_raises(self) -> None:
        with pytest.raises(ParseError, match="requires `self`"):
            _parse("""\
module test.core
app a "A"

entity Department "Department":
  id: uuid pk
  all_descendants: descendants_of root via parent_department
""")


def _appspec(*entities: ir.EntitySpec) -> ir.AppSpec:
    return ir.AppSpec(
        name="test",
        version="1.0.0",
        domain=ir.DomainSpec(entities=list(entities)),
        surfaces=[],
    )


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
    )


class TestDescendantsOfValidator:
    def test_self_ref_via_unknown_field_errors(self) -> None:
        dept = ir.EntitySpec(
            name="Department",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="all_descendants",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_field="parent_dept",  # doesn't exist
                    ),
                ),
            ],
        )
        errors, _ = validate_entities(_appspec(dept))
        assert any("via='parent_dept' is not a field on this entity" in e for e in errors)

    def test_self_ref_via_wrong_target_errors(self) -> None:
        dept = ir.EntitySpec(
            name="Department",
            fields=[
                _id_field(),
                _ref("owner", "Other"),  # FK but not to Department
                ir.FieldSpec(
                    name="all_descendants",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_field="owner",
                    ),
                ),
            ],
        )
        other = ir.EntitySpec(name="Other", fields=[_id_field()])
        errors, _ = validate_entities(_appspec(dept, other))
        assert any("recursive traversal needs a self-referencing FK" in e for e in errors)

    def test_junction_missing_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="all_reports",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_entity="ManagerLink",
                        via_field="manager",
                    ),
                ),
            ],
        )
        errors, _ = validate_entities(_appspec(person))
        assert any("references unknown entity 'ManagerLink'" in e for e in errors)

    def test_junction_missing_parent_fk_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="all_reports",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_entity="ManagerLink",
                        via_field="manager",
                    ),
                ),
            ],
        )
        junction = ir.EntitySpec(
            name="ManagerLink",
            fields=[_id_field(), _ref("report", "Person")],
        )
        errors, _ = validate_entities(_appspec(person, junction))
        assert any("has no field 'manager'" in e for e in errors)

    def test_junction_missing_second_host_ref_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="all_reports",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_entity="ManagerLink",
                        via_field="manager",
                    ),
                ),
            ],
        )
        junction = ir.EntitySpec(
            name="ManagerLink",
            fields=[
                _id_field(),
                _ref("manager", "Person"),
                # no second ref Person — child set has no name
            ],
        )
        errors, _ = validate_entities(_appspec(person, junction))
        assert any("needs a second `ref Person` field" in e for e in errors)

    def test_self_ref_via_valid_passes(self) -> None:
        dept = ir.EntitySpec(
            name="Department",
            fields=[
                _id_field(),
                _ref("parent_department", "Department"),
                ir.FieldSpec(
                    name="all_descendants",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_field="parent_department",
                    ),
                ),
            ],
        )
        errors, _ = validate_entities(_appspec(dept))
        descendants_errors = [e for e in errors if "descendants_of" in e or "ancestors_of" in e]
        assert descendants_errors == []

    def test_junction_via_valid_passes(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="all_reports",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.DESCENDANTS_OF,
                        via_entity="ManagerLink",
                        via_field="manager",
                    ),
                ),
            ],
        )
        junction = ir.EntitySpec(
            name="ManagerLink",
            fields=[
                _id_field(),
                _ref("manager", "Person"),
                _ref("report", "Person"),
            ],
        )
        errors, _ = validate_entities(_appspec(person, junction))
        descendants_errors = [e for e in errors if "descendants_of" in e or "ancestors_of" in e]
        assert descendants_errors == []
