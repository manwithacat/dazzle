"""Aggregate-expression parsing for the DAZZLE DSL.

Produces typed :class:`dazzle.core.ir.AggregateRef` from token streams
matching the call shapes:

- ``count(Entity)`` — row count on an entity
- ``count(Entity where <predicate>)`` — row count with filter
- ``avg(column)`` — source-relative scalar
- ``avg(column where <predicate>)`` — source-relative scalar with filter
- ``avg(Entity.column)`` — cross-entity scalar
- ``avg(Entity.column where <predicate>)`` — cross-entity scalar with filter

Same shapes also apply to ``sum`` / ``min`` / ``max``. ``count`` rejects
a column (caught by :class:`AggregateRef`'s validator).

Replaces the legacy ``_AGGREGATE_RE`` parsing at runtime — see ADR-0024
(no regex for DSL grammar) and
``dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md``.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType

_AGGREGATE_FUNCS: frozenset[str] = frozenset({"count", "sum", "avg", "min", "max"})

# Aggregate function names are reserved keywords in the lexer; each has its
# own TokenType. The helpers below accept either the dedicated token type
# OR a plain IDENTIFIER whose value matches — IDENTIFIER fallback supports
# contexts where the keyword status was not promoted.
_AGGREGATE_TOKEN_TYPES: frozenset[TokenType] = frozenset(
    {
        TokenType.COUNT,
        TokenType.SUM,
        TokenType.AVG,
        TokenType.MIN,
        TokenType.MAX,
    }
)


class AggregateParserMixin:
    """Mixin providing :class:`AggregateRef` parsing.

    Requires the host parser to also include ``ConditionParserMixin``
    (for ``parse_condition_expr``) and ``BaseParser``.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        peek_token: Any
        expect_identifier_or_keyword: Any
        file: Any
        parse_condition_expr: Any  # from ConditionParserMixin

    def parse_aggregate_ref(self) -> ir.AggregateRef:
        """Consume an aggregate call from the token stream.

        Raises a parse error if the current token isn't an aggregate
        function name. Caller is responsible for shape-detecting the
        aggregate form (e.g. via :meth:`peek_is_aggregate_call`) when
        the field accepts both literal and aggregate values.
        """
        func_tok = self.current_token()
        if not self._token_is_aggregate_func(func_tok):
            raise make_parse_error(
                f"expected aggregate function "
                f"(one of: count, sum, avg, min, max), got {func_tok.value!r}",
                self.file,
                func_tok.line,
                func_tok.column,
            )
        func_name = func_tok.value
        self.advance()  # consume the function name identifier

        self.expect(TokenType.LPAREN)

        entity: str | None = None
        column: str | None = None
        where: ir.ConditionExpr | None = None

        # The argument shape: IDENT (`.` IDENT)? — first IDENT is either
        # an entity (count) or a column / entity-prefix (sum/avg/min/max).
        # An immediate `)` after `(` is a parse error: count needs an
        # entity, scalars need a column.
        if self.match(TokenType.RPAREN):
            tok = self.current_token()
            raise make_parse_error(
                f"{func_name}() requires an argument "
                f"(entity name for count, column for sum/avg/min/max)",
                self.file,
                tok.line,
                tok.column,
            )

        first_ident_tok = self.expect_identifier_or_keyword()
        first_ident: str = first_ident_tok.value

        if self.match(TokenType.DOT):
            self.advance()  # consume `.`
            second_ident_tok = self.expect_identifier_or_keyword()
            entity = first_ident
            column = second_ident_tok.value
        else:
            # Bare identifier — disambiguation depends on func:
            #   count(X) → X is an entity
            #   avg(X)   → X is a column on the source entity
            # AggregateRef's validator enforces the shape constraints.
            if func_name == "count":
                entity = first_ident
            else:
                column = first_ident

        # Optional `where <ConditionExpr>` clause inside the parens.
        if self.match(TokenType.WHERE):
            self.advance()  # consume `where`
            where = self.parse_condition_expr()

        self.expect(TokenType.RPAREN)

        return ir.AggregateRef(
            func=func_name,
            entity=entity,
            column=column,
            where=where,
        )

    def peek_is_aggregate_call(self) -> bool:
        """True when the next two tokens look like an aggregate call.

        Shape: IDENTIFIER('count'|'sum'|'avg'|'min'|'max') followed by '('.
        Used by call sites that accept either an aggregate or a literal
        (e.g. ``PipelineStageSpec.value``) so they can dispatch without
        committing tokens.
        """
        cur = self.current_token()
        if not self._token_is_aggregate_func(cur):
            return False
        return bool(self.peek_token().type == TokenType.LPAREN)

    @staticmethod
    def _token_is_aggregate_func(tok: Any) -> bool:
        """True iff ``tok`` is an aggregate-function token.

        Accepts the dedicated lexer token types (``COUNT``, ``SUM``, ``AVG``,
        ``MIN``, ``MAX``) and an IDENTIFIER whose value matches the same
        set (in case a future lexer change demotes one).
        """
        if tok.type in _AGGREGATE_TOKEN_TYPES:
            return True
        return tok.type == TokenType.IDENTIFIER and tok.value in _AGGREGATE_FUNCS
