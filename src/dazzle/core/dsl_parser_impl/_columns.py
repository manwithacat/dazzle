"""Shared list-column grammar for regions and list surfaces (#1792).

One modifier vocabulary, two homes:

    region:   columns: title(width: 34%), mark_scheme(truncate), status
    surface:  field title "Title" width: 34%
              field mark_scheme "Mark scheme" truncate
    both:     page_size: 25

Modifiers: ``width: <n>%|<n>rem|<n>ch``, ``truncate`` (on), ``truncate: true``
or ``truncate: false``. This module owns the token-consuming parse so the two
parser surfaces produce the same :class:`ir.ColumnSpec` data and the same
diagnostics.
"""

from __future__ import annotations

from typing import Any, Protocol

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


def _fail(parser: Any, message: str, token: Any) -> Any:
    raise make_parse_error(message, parser.file, token.line, token.column)


def parse_column_width(parser: Any) -> str:
    """Parse the value of ``width:`` (the caller consumed ``width`` and ``:``).

    ``34%`` lexes as NUMBER PERCENT; ``12rem`` / ``20ch`` as NUMBER IDENTIFIER.
    """
    num_tok = parser.expect(TokenType.NUMBER)
    if parser.match(TokenType.PERCENT):
        parser.advance()
        width = f"{num_tok.value}%"
    elif parser.match(TokenType.IDENTIFIER):
        width = f"{num_tok.value}{parser.advance().value}"
    else:
        width = str(num_tok.value)
    err = ir.column_width_error(width)
    if err is not None:
        _fail(parser, err, num_tok)
    return width


def is_column_modifier(parser: Any) -> bool:
    """True when the current token starts a column modifier (``width`` / ``truncate``)."""
    if parser.match(TokenType.WIDTH):
        peek = parser.peek_token()
        return bool(peek and peek.type == TokenType.COLON)
    tok = parser.current_token()
    return bool(tok.type == TokenType.IDENTIFIER and tok.value == "truncate")


def parse_column_modifier(parser: Any, hints: dict[str, Any]) -> None:
    """Consume one modifier into ``hints`` (keys ``width`` / ``truncate``)."""
    if parser.match(TokenType.WIDTH):
        parser.advance()
        parser.expect(TokenType.COLON)
        hints["width"] = parse_column_width(parser)
        return
    tok = parser.current_token()
    if tok.type != TokenType.IDENTIFIER or tok.value != "truncate":
        _fail(
            parser,
            f"Unknown column modifier {tok.value!r} — expected `width: <n>%|rem|ch` "
            "or `truncate` / `truncate: false`",
            tok,
        )
    parser.advance()
    if not parser.match(TokenType.COLON):
        hints["truncate"] = True
        return
    parser.advance()
    if parser.match(TokenType.TRUE):
        parser.advance()
        hints["truncate"] = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        hints["truncate"] = False
    else:
        bad = parser.current_token()
        _fail(parser, f"`truncate:` takes true or false, got {bad.value!r}", bad)


def _parse_column_entry(parser: Any) -> ir.ColumnSpec:
    """One ``name`` or ``name(mod, mod)`` entry of a ``columns:`` list."""
    name_tok = parser.expect_identifier_or_keyword()
    if parser.match(TokenType.DOT):
        _fail(
            parser,
            f"columns: entry '{name_tok.value}.…' — dotted paths are not supported; "
            "name a field on the region's source entity (a ref field shows the "
            "related record's display name)",
            name_tok,
        )
    hints: dict[str, Any] = {}
    if parser.match(TokenType.LPAREN):
        parser.advance()
        parse_column_modifier(parser, hints)
        while parser.match(TokenType.COMMA):
            parser.advance()
            parse_column_modifier(parser, hints)
        parser.expect(TokenType.RPAREN)
    return ir.ColumnSpec(field=str(name_tok.value), **hints)


def parse_columns_list(parser: Any) -> list[ir.ColumnSpec]:
    """Parse the value of ``columns:`` (the caller consumed ``columns`` and ``:``)."""
    columns = [_parse_column_entry(parser)]
    while parser.match(TokenType.COMMA):
        parser.advance()
        columns.append(_parse_column_entry(parser))
    return columns


class _HasPageSize(Protocol):
    page_size: int | None


def kw_page_size(parser: Any, state: _HasPageSize) -> None:
    """``page_size: <int 1..MAX_PAGE_SIZE>`` — rows per page with a pager (#1792)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    num_tok = parser.expect(TokenType.NUMBER)
    try:
        value = int(num_tok.value)
    except (TypeError, ValueError):
        value = 0
    if not 1 <= value <= ir.MAX_PAGE_SIZE:
        _fail(
            parser,
            f"page_size must be a whole number from 1 to {ir.MAX_PAGE_SIZE}, got {num_tok.value}",
            num_tok,
        )
    state.page_size = value
    parser.skip_newlines()
