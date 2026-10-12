"""`BaseParser.enum_from_token` + end-to-end ParseError for migrated enum sites (#1342).

The helper is the single guarded "token → IR enum" path; an invalid value must surface as
a ParseError (never a raw ValueError) at the parser boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl.base import BaseParser
from dazzle.core.errors import ParseError
from dazzle.core.lexer import Token, TokenType


def _tok(value: str) -> Token:
    return Token(type=TokenType.IDENTIFIER, value=value, line=1, column=1)


def test_enum_from_token_valid() -> None:
    parser = BaseParser([], Path("x.dsl"))
    assert parser.enum_from_token(ir.BusinessPriority, _tok(ir.BusinessPriority.HIGH.value)) is (
        ir.BusinessPriority.HIGH
    )


def test_enum_from_token_invalid_raises_parse_error() -> None:
    parser = BaseParser([], Path("x.dsl"))
    with pytest.raises(ParseError, match="Invalid BusinessPriority"):
        parser.enum_from_token(ir.BusinessPriority, _tok("not_a_priority"))


def test_enum_from_token_label_override() -> None:
    parser = BaseParser([], Path("x.dsl"))
    with pytest.raises(ParseError, match="Invalid widget kind"):
        parser.enum_from_token(ir.BusinessPriority, _tok("nope"), label="widget kind")
