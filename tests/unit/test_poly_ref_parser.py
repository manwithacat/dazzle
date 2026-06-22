"""#1448: poly_ref lexer token + field-type parsing."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.lexer import Lexer, TokenType


def test_poly_ref_tokenizes_as_keyword():
    toks = Lexer("poly_ref target [A, B]", Path("test.dsl")).tokenize()
    kinds = [t.type for t in toks]
    assert TokenType.POLY_REF in kinds
    assert TokenType.LBRACKET in kinds
    assert TokenType.RBRACKET in kinds


_FIELD_SRC = """module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  name: str(80)

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort, Manuscript]
"""


def test_parse_poly_ref_field():
    from dazzle.core.dsl_parser_impl import parse_dsl

    _, _, _, _, _, fragment = parse_dsl(_FIELD_SRC, Path("test.dsl"))
    aijob = next(e for e in fragment.entities if e.name == "AIJob")
    target = next(f for f in aijob.fields if f.name == "target")
    assert target.type.kind.value == "poly_ref"
    assert target.type.poly_targets == ["Cohort", "Manuscript"]
