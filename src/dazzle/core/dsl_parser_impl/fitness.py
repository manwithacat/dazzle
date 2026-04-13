"""Parser for the `fitness:` block inside an entity declaration.

Part of the Agent-Led Fitness v1 methodology. The block currently supports
one key — `repr_fields: [a, b, c]` — which lists the domain-essential fields
used by the fitness evaluator when recording row changes.

Expected DSL shape:

    fitness:
      repr_fields: [title, status, assignee_id]
"""

from typing import TYPE_CHECKING

from ..errors import make_parse_error
from ..ir.fitness_repr import FitnessSpec
from ..lexer import TokenType

if TYPE_CHECKING:
    from .base import BaseParser


def parse_fitness_block(parser: "BaseParser", declared_field_names: set[str]) -> FitnessSpec:
    """Parse a `fitness:` block body.

    The caller must have already consumed the `fitness` token and its
    trailing `:` colon. This function handles the block body starting at
    the first NEWLINE/INDENT.

    Every name appearing in `repr_fields` must be present in
    ``declared_field_names``; otherwise a parse error is raised.
    """
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    repr_fields: list[str] = []
    saw_repr_fields = False

    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break

        key_token = parser.expect_identifier_or_keyword()
        key = key_token.value
        parser.expect(TokenType.COLON)

        if key == "repr_fields":
            saw_repr_fields = True
            parser.expect(TokenType.LBRACKET)
            while not parser.match(TokenType.RBRACKET):
                name_token = parser.expect_identifier_or_keyword()
                name = name_token.value
                if name not in declared_field_names:
                    raise make_parse_error(
                        f"fitness.repr_fields references undeclared field "
                        f"{name!r} (not found on entity)",
                        parser.file,
                        name_token.line,
                        name_token.column,
                    )
                repr_fields.append(name)
                if parser.match(TokenType.COMMA):
                    parser.advance()
            parser.expect(TokenType.RBRACKET)
            parser.skip_newlines()
        else:
            token = parser.current_token()
            raise make_parse_error(
                f"Unknown key `{key}` in fitness: block (expected: repr_fields)",
                parser.file,
                token.line,
                token.column,
            )

    parser.expect(TokenType.DEDENT)

    if not saw_repr_fields:
        token = parser.current_token()
        raise make_parse_error(
            "fitness: block missing required `repr_fields`",
            parser.file,
            token.line,
            token.column,
        )

    return FitnessSpec(repr_fields=repr_fields)
