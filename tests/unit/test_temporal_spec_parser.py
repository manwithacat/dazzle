"""#1223 Phase 3a.i — parser + IR tests for the entity-level `temporal:` block.

Runtime consumers (tombstone filter on read paths, as_of URL param,
current-row resolution) land in subsequent slices (3a.ii–3a.v) and are
covered by their own test suites. These tests only pin:

1. The `temporal:` block parses into a `TemporalSpec` on the entity.
2. Required keys (start_field, end_field, key_field) are enforced.
3. Optional keys (default_filter, as_of_param) carry sensible defaults.
4. Unknown keys raise clear parse errors.
5. The validator catches: missing-field references, end_field declared `required`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(dsl: str) -> ir.AppSpec | None:
    """Parse + return the module fragment (or None if parse fails)."""
    _, _, _, _, _, frag = parse_dsl(dsl, Path("test.dz"))
    return frag


def _employment_entity_dsl(temporal_block: str) -> str:
    """Wrap a temporal: block fragment inside a minimal Employment entity."""
    return f"""\
module test.core
app a "A"

entity Person "Person":
  id: uuid pk

entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  start_date: date required
  end_date: date

{temporal_block}
"""


class TestTemporalBlockParses:
    def test_minimal_required_keys(self) -> None:
        dsl = _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
""")
        frag = _parse(dsl)
        employment = next(e for e in frag.entities if e.name == "Employment")
        assert employment.temporal is not None
        assert employment.temporal.start_field == "start_date"
        assert employment.temporal.end_field == "end_date"
        assert employment.temporal.key_field == "person"
        # Defaults
        assert employment.temporal.default_filter == "active"
        assert employment.temporal.as_of_param == "as_of"

    def test_explicit_default_filter_and_as_of_param(self) -> None:
        dsl = _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
    default_filter: none
    as_of_param: snapshot_date
""")
        frag = _parse(dsl)
        employment = next(e for e in frag.entities if e.name == "Employment")
        assert employment.temporal.default_filter == "none"
        assert employment.temporal.as_of_param == "snapshot_date"

    def test_default_filter_active_is_default(self) -> None:
        dsl = _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
""")
        frag = _parse(dsl)
        employment = next(e for e in frag.entities if e.name == "Employment")
        assert employment.temporal.default_filter == "active"


class TestTemporalBlockParseErrors:
    def test_missing_start_field_raises(self) -> None:
        with pytest.raises(ParseError, match="missing required key"):
            _parse(
                _employment_entity_dsl("""\
  temporal:
    end_field: end_date
    key_field: person
""")
            )

    def test_missing_end_field_raises(self) -> None:
        with pytest.raises(ParseError, match="missing required key"):
            _parse(
                _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    key_field: person
""")
            )

    def test_missing_key_field_raises(self) -> None:
        with pytest.raises(ParseError, match="missing required key"):
            _parse(
                _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
""")
            )

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown temporal: key"):
            _parse(
                _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
    bogus_key: nope
""")
            )

    def test_unknown_default_filter_value_raises(self) -> None:
        with pytest.raises(ParseError, match="Unknown temporal default_filter"):
            _parse(
                _employment_entity_dsl("""\
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person
    default_filter: not_a_real_filter
""")
            )


class TestTemporalValidator:
    """The validator rejects temporal: blocks with broken field refs."""

    def test_missing_field_reference_errors(self) -> None:
        # temporal points at a field that doesn't exist on the entity
        from dazzle.core.validator import validate_entities

        person = ir.EntitySpec(
            name="Person",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",  # doesn't exist
                end_field="end_date",  # doesn't exist
                key_field="person",
            ),
        )
        appspec = ir.AppSpec(
            name="test",
            version="1.0.0",
            domain=ir.DomainSpec(entities=[person, employment]),
            surfaces=[],
        )
        errors, _ = validate_entities(appspec)
        assert any("temporal.start_field" in e and "start_date" in e for e in errors)
        assert any("temporal.end_field" in e and "end_date" in e for e in errors)

    def test_required_end_field_errors(self) -> None:
        """end_field carrying `required` defeats the NULL=active sentinel."""
        from dazzle.core.validator import validate_entities

        person = ir.EntitySpec(
            name="Person",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ],
        )
        employment = ir.EntitySpec(
            name="Employment",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
                ir.FieldSpec(
                    name="start_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
                ir.FieldSpec(
                    name="end_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                    modifiers=[ir.FieldModifier.REQUIRED],  # wrong — should be optional
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="person",
            ),
        )
        appspec = ir.AppSpec(
            name="test",
            version="1.0.0",
            domain=ir.DomainSpec(entities=[person, employment]),
            surfaces=[],
        )
        errors, _ = validate_entities(appspec)
        assert any("end_field" in e and "must NOT be `required`" in e for e in errors)
