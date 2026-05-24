"""#1223 Phase 3a.v — parser + validator for `latest_one EntityName via fk_field`.

Runtime resolution (the actual fetch of the current row) is a follow-up
slice (3a.v.ii). These tests pin only:

1. `latest_one EntityName via fk_field` parses into FieldType(kind=LATEST_ONE).
2. Bare `latest_one EntityName` (no via) raises ParseError.
3. validate_entities catches: unknown target entity, target without
   temporal:, target's via field doesn't exist, via field isn't a ref
   back to self.
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


class TestLatestOneParses:
    def test_with_explicit_via(self) -> None:
        frag = _parse("""\
module test.core
app a "A"

entity Person "Person":
  id: uuid pk
  current_employment: latest_one Employment via person

entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  start_date: date required
  end_date: date

  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
""")
        person = next(e for e in frag.entities if e.name == "Person")
        field = next(f for f in person.fields if f.name == "current_employment")
        assert field.type.kind == ir.FieldTypeKind.LATEST_ONE
        assert field.type.ref_entity == "Employment"
        assert field.type.via_field == "person"

    def test_without_via_raises(self) -> None:
        with pytest.raises(ParseError, match="requires `via"):
            _parse("""\
module test.core
app a "A"

entity Person "Person":
  id: uuid pk
  current_employment: latest_one Employment

entity Employment "Employment":
  id: uuid pk
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


class TestLatestOneValidator:
    def test_unknown_target_entity_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",  # not in appspec
                        via_field="person",
                    ),
                ),
            ],
        )
        errors, _ = validate_entities(_appspec(person))
        assert any("unknown entity 'Employment'" in e for e in errors)

    def test_target_without_temporal_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",
                        via_field="person",
                    ),
                ),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
            ],
            # no temporal block
        )
        errors, _ = validate_entities(_appspec(person, employment))
        assert any("no `temporal:` block" in e for e in errors)

    def test_via_field_not_a_ref_back_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",
                        via_field="start_date",  # not a ref to Person
                    ),
                ),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="start_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
                ir.FieldSpec(
                    name="end_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="id",
            ),
        )
        errors, _ = validate_entities(_appspec(person, employment))
        assert any("not a `ref Person` field" in e for e in errors)

    def test_via_field_missing_errors(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",
                        via_field="nonexistent",
                    ),
                ),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
                ir.FieldSpec(
                    name="start_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
                ir.FieldSpec(
                    name="end_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="person",
            ),
        )
        errors, _ = validate_entities(_appspec(person, employment))
        assert any("via='nonexistent'" in e and "unknown field" in e for e in errors)

    def test_valid_latest_one_passes(self) -> None:
        person = ir.EntitySpec(
            name="Person",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="current_employment",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.LATEST_ONE,
                        ref_entity="Employment",
                        via_field="person",
                    ),
                ),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
                ir.FieldSpec(
                    name="start_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
                ir.FieldSpec(
                    name="end_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="person",
            ),
        )
        errors, _ = validate_entities(_appspec(person, employment))
        latest_one_errors = [e for e in errors if "latest_one" in e]
        assert latest_one_errors == []
