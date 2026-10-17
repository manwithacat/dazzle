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
