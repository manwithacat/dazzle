"""#1448: poly_ref expands to two physical columns (target_type, target_id).

The expansion happens at the core-IR → back-spec boundary (convert_entity),
mirroring how money fields expand to _minor/_currency — so the schema generator
and back-spec never need to know about poly_ref.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Uuid

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata

_SRC = """module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  name: str(80)

entity AIJob "AI Job":
  id: uuid pk
  cost: decimal(10,2)
  target: poly_ref [Cohort] required
"""


def _back_entities():
    _, _, _, _, _, fragment = parse_dsl(_SRC, Path("test.dsl"))
    return convert_entities(fragment.entities)


def test_poly_ref_expands_to_two_back_fields():
    back = _back_entities()
    aijob = next(e for e in back if e.name == "AIJob")
    names = {f.name for f in aijob.fields}
    assert "target_type" in names
    assert "target_id" in names
    assert "target" not in names  # the logical field has no own column


def test_poly_ref_emits_two_columns():
    md = build_metadata(_back_entities())
    table = md.tables["AIJob"]
    assert "target_type" in table.columns
    assert "target_id" in table.columns
    assert "target" not in table.columns
    assert isinstance(table.columns["target_id"].type, Uuid)
    assert table.columns["target_type"].nullable is False
    assert table.columns["target_id"].nullable is False
