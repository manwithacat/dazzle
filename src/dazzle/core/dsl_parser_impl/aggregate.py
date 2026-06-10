"""Aggregate-expression parsing for the DAZZLE DSL.

Produces typed :class:`dazzle.core.ir.AggregateRef` from token streams
matching the call shapes:

- ``count(Entity)`` — row count on an entity
- ``count(Entity where <predicate>)`` — row count with filter
- ``avg(column)`` — source-relative scalar
- ``avg(column where <predicate>)`` — source-relative scalar with filter
- ``avg(Entity.column)`` — cross-entity scalar
- ``avg(Entity.column where <predicate>)`` — cross-entity scalar with filter
- ``avg(<expression>)`` — L3 nested arithmetic / casts / function calls
  (#1152). Examples:
      ``avg(score::float / max_score)``
      ``avg(MarkingResult.score::float / nullif(MarkingResult.max_score, 0))``

Same shapes also apply to ``sum`` / ``min`` / ``max``. ``count`` rejects
both column and expression forms (caught by :class:`AggregateRef`'s
validator).

Replaces the legacy ``_AGGREGATE_RE`` parsing at runtime — see ADR-0024
(no regex for DSL grammar) and
``dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md``.
"""

from typing import TYPE_CHECKING, Any, cast

from .. import ir
from ..errors import make_parse_error
from ..ir.aggregates import AggregateBinaryOp, DerivedFunctionName
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

# L3 expression — whitelisted cast target identifiers. Mirrors
# :data:`dazzle.core.ir.aggregates.CastTarget`. Duplicated here so the
# parser can produce a precise error message instead of letting the IR
# validator's ValidationError leak out.
_CAST_TARGETS: frozenset[str] = frozenset({"float", "int", "numeric", "text"})

# L3 expression — whitelisted function names. Mirrors
# :data:`dazzle.core.ir.aggregates.AggregateFunctionName`.
_EXPR_FUNCTIONS: frozenset[str] = frozenset({"nullif", "coalesce", "abs"})

# Derived-metric functions (#1359). Mirrors
# :data:`dazzle.core.ir.aggregates.DerivedFunctionName`.
_DERIVED_FUNCTIONS: frozenset[str] = frozenset({"round", "abs", "nullif", "coalesce"})


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
        expression: ir.AggregateExpr | None = None
        where: ir.ConditionExpr | None = None

        if self.match(TokenType.RPAREN):
            tok = self.current_token()
            raise make_parse_error(
                f"{func_name}() requires an argument "
                f"(entity name for count, column for sum/avg/min/max)",
                self.file,
                tok.line,
                tok.column,
            )

        if func_name == "count":
            # count(Entity [where ...]) — no expression form. The legacy
            # `count(Entity.col)` shape is parsed and rejected by the
            # AggregateRef validator (consistent error surface with the
            # pre-L3 parser).
            first_ident_tok = self.expect_identifier_or_keyword()
            entity = first_ident_tok.value
            if self.match(TokenType.DOT):
                self.advance()
                second_ident_tok = self.expect_identifier_or_keyword()
                column = second_ident_tok.value
        else:
            # sum/avg/min/max — parse the argument as an aggregate
            # expression. If the result is a bare column ref (with or
            # without entity prefix), set the legacy ``entity`` /
            # ``column`` fields and leave ``expression`` empty so simple
            # consumers (the existing scalar runtime path) stay on the
            # fast track. Anything more structured populates
            # ``expression`` and the runtime dispatches via the L3
            # compiler.
            node = self._parse_aggregate_expr()
            if node.is_column_ref and not (
                node.is_cast or node.is_binary_op or node.is_function_call or node.is_number_literal
            ):
                entity = node.column_entity
                column = node.column_name
            else:
                entity = self._extract_expression_entity(node)
                expression = node

        # Optional `where <ConditionExpr>` clause inside the parens.
        if self.match(TokenType.WHERE):
            self.advance()  # consume `where`
            where = self.parse_condition_expr()

        self.expect(TokenType.RPAREN)

        return ir.AggregateRef(
            func=func_name,
            entity=entity,
            column=column,
            expression=expression,
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

    # ─────────────── L3 expression parsing ───────────────

    def _parse_aggregate_expr(self) -> ir.AggregateExpr:
        """Top-level expression entry — lowest precedence."""
        return self._parse_additive_expr()

    def _parse_additive_expr(self) -> ir.AggregateExpr:
        left = self._parse_multiplicative_expr()
        while self.match(TokenType.PLUS) or self.match(TokenType.MINUS):
            op_tok = self.current_token()
            op = op_tok.value
            self.advance()
            right = self._parse_multiplicative_expr()
            left = ir.AggregateExpr(binary_op=op, binary_left=left, binary_right=right)
        return left

    def _parse_multiplicative_expr(self) -> ir.AggregateExpr:
        left = self._parse_cast_expr()
        while self.match(TokenType.STAR) or self.match(TokenType.SLASH):
            op_tok = self.current_token()
            op = op_tok.value
            self.advance()
            right = self._parse_cast_expr()
            left = ir.AggregateExpr(binary_op=op, binary_left=left, binary_right=right)
        return left

    def _parse_cast_expr(self) -> ir.AggregateExpr:
        operand = self._parse_primary_expr()
        # Casts chain left-to-right: ``score::int::float`` is
        # ``cast(cast(score, int), float)`` — same shape as SQL's `::`.
        while self._peek_double_colon():
            self.advance()  # consume first COLON
            self.advance()  # consume second COLON
            target_tok = self.expect_identifier_or_keyword()
            target = target_tok.value
            if target not in _CAST_TARGETS:
                raise make_parse_error(
                    f"unsupported cast target {target!r}; expected one of {sorted(_CAST_TARGETS)}",
                    self.file,
                    target_tok.line,
                    target_tok.column,
                )
            operand = ir.AggregateExpr(cast_target=target, cast_operand=operand)
        return operand

    def _parse_primary_expr(self) -> ir.AggregateExpr:
        tok = self.current_token()

        # Parenthesised sub-expression.
        if tok.type == TokenType.LPAREN:
            self.advance()  # consume '('
            inner = self._parse_aggregate_expr()
            self.expect(TokenType.RPAREN)
            return inner

        # Unary minus before a numeric literal — the only unary form
        # the L3 grammar supports. Compound unary on column refs or
        # function calls is unrepresentable; users can write ``0 - x``.
        if tok.type == TokenType.MINUS:
            self.advance()
            num_tok = self.current_token()
            if num_tok.type != TokenType.NUMBER:
                raise make_parse_error(
                    "unary '-' is only supported before a number literal",
                    self.file,
                    num_tok.line,
                    num_tok.column,
                )
            self.advance()
            return ir.AggregateExpr(number_literal=-_parse_number_literal(num_tok.value))

        # Numeric literal.
        if tok.type == TokenType.NUMBER:
            self.advance()
            return ir.AggregateExpr(number_literal=_parse_number_literal(tok.value))

        # Identifier — column ref or function call.
        ident_tok = self.expect_identifier_or_keyword()
        ident = ident_tok.value

        # Function call: IDENT '(' [arg (',' arg)*] ')'
        if self.match(TokenType.LPAREN):
            if ident not in _EXPR_FUNCTIONS:
                raise make_parse_error(
                    f"unsupported function {ident!r} in aggregate expression; "
                    f"expected one of {sorted(_EXPR_FUNCTIONS)}",
                    self.file,
                    ident_tok.line,
                    ident_tok.column,
                )
            self.advance()  # consume LPAREN
            args: list[ir.AggregateExpr] = []
            if not self.match(TokenType.RPAREN):
                args.append(self._parse_aggregate_expr())
                while self.match(TokenType.COMMA):
                    self.advance()
                    args.append(self._parse_aggregate_expr())
            self.expect(TokenType.RPAREN)
            return ir.AggregateExpr(function_name=ident, function_args=tuple(args))

        # Dotted column ref: IDENT '.' IDENT
        if self.match(TokenType.DOT):
            self.advance()
            col_tok = self.expect_identifier_or_keyword()
            return ir.AggregateExpr(column_entity=ident, column_name=col_tok.value)

        # Bare column ref.
        return ir.AggregateExpr(column_name=ident)

    def _peek_double_colon(self) -> bool:
        """True when the next two tokens are ``COLON COLON`` — the SQL
        cast operator ``::``. The lexer does not emit a dedicated
        ``DOUBLE_COLON`` token; this two-token peek is the canonical
        recognition path.
        """
        if not self.match(TokenType.COLON):
            return False
        return bool(self.peek_token().type == TokenType.COLON)

    def _extract_expression_entity(self, expr: ir.AggregateExpr) -> str | None:
        """Discover the single entity prefix used by all column refs.

        L3 invariant: every column reference inside an :class:`AggregateExpr`
        must either be bare or share the same ``column_entity`` prefix.
        Mixed forms are ambiguous (which entity's repository should the
        runtime dispatch against?) and are rejected at parse time.

        Returns the shared entity name when every column ref carries the
        same prefix, ``None`` when all refs are bare (source-relative).
        Raises :class:`ParseError` on mismatch.
        """
        entities: set[str | None] = set()
        for col_ref in _walk_column_refs(expr):
            entities.add(col_ref.column_entity)
        if len(entities) == 0:
            return None
        if len(entities) == 1:
            return next(iter(entities))
        # Mixed prefixes — surface a parse error against the function
        # token. The current token is RPAREN by the time this runs so
        # we don't have a precise pin; use the file-level position.
        tok = self.current_token()
        present = sorted(str(e) for e in entities if e is not None)
        raise make_parse_error(
            f"aggregate expression mixes column-entity prefixes "
            f"({present!r} plus bare refs); use the same prefix on every "
            f"column or none at all",
            self.file,
            tok.line,
            tok.column,
        )

    # ─────────────── Derived-metric parsing (#1359) ───────────────

    def parse_derived_metric(self, declared_metrics: set[str]) -> "ir.DerivedMetric":
        """Parse arithmetic over previously-declared metric names.

        ``completion_rate: round(done / total * 100)`` — identifiers resolve
        against *declared_metrics* (the names earlier in the same
        ``aggregate:`` block); anything else is a precise parse error.
        Evaluated in Python post-aggregation, never compiled to SQL.
        """
        expression = self._parse_derived_additive(declared_metrics)
        return ir.DerivedMetric(expression=expression)

    def _parse_derived_additive(self, declared: set[str]) -> "ir.DerivedMetricExpr":
        left = self._parse_derived_multiplicative(declared)
        while self.current_token().type in (TokenType.PLUS, TokenType.MINUS):
            op: AggregateBinaryOp = "+" if self.current_token().type == TokenType.PLUS else "-"
            self.advance()
            right = self._parse_derived_multiplicative(declared)
            left = ir.DerivedMetricExpr(binary_op=op, binary_left=left, binary_right=right)
        return left

    def _parse_derived_multiplicative(self, declared: set[str]) -> "ir.DerivedMetricExpr":
        left = self._parse_derived_primary(declared)
        while self.current_token().type in (TokenType.STAR, TokenType.SLASH):
            op: AggregateBinaryOp = "*" if self.current_token().type == TokenType.STAR else "/"
            self.advance()
            right = self._parse_derived_primary(declared)
            left = ir.DerivedMetricExpr(binary_op=op, binary_left=left, binary_right=right)
        return left

    def _parse_derived_primary(self, declared: set[str]) -> "ir.DerivedMetricExpr":
        tok = self.current_token()

        if tok.type == TokenType.NUMBER:
            self.advance()
            return ir.DerivedMetricExpr(number_literal=_parse_number_literal(tok.value))

        if tok.type == TokenType.LPAREN:
            self.advance()
            inner = self._parse_derived_additive(declared)
            self.expect(TokenType.RPAREN)
            return inner

        if tok.type == TokenType.IDENTIFIER or self._token_is_aggregate_func(tok):
            name = str(tok.value)
            # Function call?
            if self.peek_token().type == TokenType.LPAREN:
                if name not in _DERIVED_FUNCTIONS:
                    raise make_parse_error(
                        f"unknown derived-metric function {name!r} — valid: "
                        f"{', '.join(sorted(_DERIVED_FUNCTIONS))}. Aggregate "
                        f"calls (count/sum/avg/min/max) must be declared as "
                        f"their own named metric first, then referenced by "
                        f"name (#1359).",
                        self.file,
                        tok.line,
                        tok.column,
                    )
                self.advance()
                self.expect(TokenType.LPAREN)
                args: list[ir.DerivedMetricExpr] = [self._parse_derived_additive(declared)]
                while self.match(TokenType.COMMA):
                    self.advance()
                    args.append(self._parse_derived_additive(declared))
                self.expect(TokenType.RPAREN)
                return ir.DerivedMetricExpr(
                    function_name=cast(DerivedFunctionName, name),
                    function_args=tuple(args),
                )
            # Metric reference.
            if name not in declared:
                hint = (
                    f"declared so far: {', '.join(sorted(declared))}"
                    if declared
                    else "no metrics declared before this line"
                )
                raise make_parse_error(
                    f"unknown metric {name!r} in derived expression — derived "
                    f"metrics may only reference names declared EARLIER in "
                    f"the same aggregate: block ({hint}). For a plain "
                    f"aggregate use count/sum/avg/min/max(...) (#1359).",
                    self.file,
                    tok.line,
                    tok.column,
                )
            self.advance()
            return ir.DerivedMetricExpr(metric_name=name)

        raise make_parse_error(
            f"expected a metric name, number, function call, or "
            f"parenthesised expression in derived metric, got "
            f"{tok.type.value}",
            self.file,
            tok.line,
            tok.column,
        )


def _parse_number_literal(value: str) -> int | float:
    """Coerce a NUMBER-token string to int when it parses cleanly,
    otherwise float. Mirrors how other DSL number consumers treat
    literals — integer-valued constants stay int so SQL bindings keep
    the right type.
    """
    try:
        return int(value)
    except ValueError:
        return float(value)


def _walk_column_refs(expr: "ir.AggregateExpr") -> "list[ir.AggregateExpr]":
    """Collect every column-ref node reachable from ``expr``.

    Returns a flat list (depth-first, in textual order). Used to validate
    the single-entity-prefix invariant and — at compile time — to discover
    every distinct column the expression depends on.
    """
    out: list[ir.AggregateExpr] = []
    _walk_collect(expr, out)
    return out


def _walk_collect(expr: "ir.AggregateExpr", out: "list[ir.AggregateExpr]") -> None:
    if expr.is_column_ref:
        out.append(expr)
        return
    if expr.is_cast and expr.cast_operand is not None:
        _walk_collect(expr.cast_operand, out)
        return
    if expr.is_binary_op:
        if expr.binary_left is not None:
            _walk_collect(expr.binary_left, out)
        if expr.binary_right is not None:
            _walk_collect(expr.binary_right, out)
        return
    if expr.is_function_call and expr.function_args is not None:
        for arg in expr.function_args:
            _walk_collect(arg, out)
        return
    # Number literal — no children.
