"""Shared STRING → :class:`ir.TextTemplate` helper (#1815, #1810)."""

from typing import Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


def parse_text_template_token(parser: Any) -> ir.TextTemplate:
    """Consume a STRING token and parse it as a row-interpolating text template.

    Shared by the surface ``title:`` line (#1815) and ``ux: breadcrumb:``
    crumbs (#1810). A malformed template is a parse error carrying its
    ``E_TEMPLATE_*`` code.
    """
    tok = parser.expect(TokenType.STRING)
    try:
        return ir.parse_text_template(tok.value)
    except ir.TextTemplateError as exc:
        raise make_parse_error(str(exc), parser.file, tok.line, tok.column) from exc


def parse_row_path_argument(parser: Any) -> tuple[str, ...]:
    """Consume ``({ref.ref})`` — a row-bound breadcrumb link's id path (#1825).

    The braced path uses the placeholder path grammar; as an id path every
    segment is a hop, so it is at most :data:`ir.MAX_TEMPLATE_HOPS` long
    (``E_TEMPLATE_PATH_TOO_DEEP``). Ref-ness is checked at validate time.
    """
    open_tok = parser.expect(TokenType.LPAREN)
    parser.expect(TokenType.LBRACE)
    parts = [parser.expect_identifier_or_keyword().value]
    while parser.match(TokenType.DOT):
        parser.advance()
        parts.append(parser.expect_identifier_or_keyword().value)
    parser.expect(TokenType.RBRACE)
    parser.expect(TokenType.RPAREN)
    dotted = ".".join(parts)
    if len(parts) > ir.MAX_TEMPLATE_HOPS:
        raise make_parse_error(
            f"E_TEMPLATE_PATH_TOO_DEEP: row link `({{{dotted}}})` hops more than "
            f"{ir.MAX_TEMPLATE_HOPS} times; name at most {ir.MAX_TEMPLATE_HOPS} ref fields "
            f"(`ref_field.ref_field`).",
            parser.file,
            open_tok.line,
            open_tok.column,
        )
    return tuple(parts)
