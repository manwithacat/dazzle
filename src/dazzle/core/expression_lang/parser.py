"""
Recursive descent parser for Dazzle expression language.

Grammar (precedence low to high):
    expr        → if_expr | or_expr
    if_expr     → "if" or_expr ":" or_expr ("elif" or_expr ":" or_expr)* "else" ":" or_expr
    or_expr     → and_expr ("or" and_expr)*
    and_expr    → not_expr ("and" not_expr)*
    not_expr    → "not" not_expr | comparison
    comparison  → addition (comp_op addition)?
                | addition ("in" | "not" "in") list_literal
                | addition ("is" "not"? "null")
    addition    → multiply (("+"|"-") multiply)*
    multiply    → unary (("*"|"/"|"%") unary)*
    unary       → "-" unary | primary
    primary     → literal | duration | func_call | field_ref | "(" expr ")" | list_literal
    literal     → INT | FLOAT | STRING | "true" | "false" | "null"
    duration    → DURATION
    func_call   → IDENT "(" (expr ("," expr)*)? ")"
    field_ref   → IDENT (("." | "->") IDENT)*
    list_literal → "[" (expr ("," expr)*)? "]"
"""

from __future__ import annotations

from dazzle.core.expression_lang.tokenizer import (
    ExpressionTokenError,
    Token,
    TokenKind,
    tokenize,
)
from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    Expr,
    FieldRef,
    FuncCall,
    IfExpr,
    InExpr,
    Literal,
    UnaryExpr,
    UnaryOp,
)


class ExpressionParseError(Exception):
    """Error during expression parsing."""

    def __init__(self, message: str, pos: int = 0) -> None:
        super().__init__(message)
        self.pos = pos


class _Parser:
    """Recursive descent parser for expressions."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def expect(self, kind: TokenKind) -> Token:
        tok = self.current
        if tok.kind != kind:
            raise ExpressionParseError(
                f"Expected {kind}, got {tok.kind} ({tok.value!r})",
                tok.pos,
            )
        return self.advance()

    def match(self, *kinds: TokenKind) -> Token | None:
        if self.current.kind in kinds:
            return self.advance()
        return None

    # -- Grammar rules --

    def parse_expr(self) -> Expr:
        """Top-level: if_expr or or_expr."""
        if self.current.kind == TokenKind.IF:
            return self.parse_if_expr()
        return self.parse_or_expr()

    def parse_if_expr(self) -> IfExpr:
        """if cond: val (elif cond: val)* else: val"""
        self.expect(TokenKind.IF)
        condition = self.parse_or_expr()
        self.expect(TokenKind.COLON)
        then_expr = self.parse_or_expr()

        elif_branches: list[tuple[Expr, Expr]] = []
        while self.match(TokenKind.ELIF):
            elif_cond = self.parse_or_expr()
            self.expect(TokenKind.COLON)
            elif_val = self.parse_or_expr()
            elif_branches.append((elif_cond, elif_val))

        self.expect(TokenKind.ELSE)
        self.expect(TokenKind.COLON)
        else_expr = self.parse_or_expr()

        return IfExpr(
            condition=condition,
            then_expr=then_expr,
            elif_branches=elif_branches,
            else_expr=else_expr,
        )

    def parse_or_expr(self) -> Expr:
        """and_expr ("or" and_expr)*"""
        left = self.parse_and_expr()
        while self.match(TokenKind.OR):
            right = self.parse_and_expr()
            left = BinaryExpr(op=BinaryOp.OR, left=left, right=right)
        return left

    def parse_and_expr(self) -> Expr:
        """not_expr ("and" not_expr)*"""
        left = self.parse_not_expr()
        while self.match(TokenKind.AND):
            right = self.parse_not_expr()
            left = BinaryExpr(op=BinaryOp.AND, left=left, right=right)
        return left

    def parse_not_expr(self) -> Expr:
        """'not' not_expr | comparison"""
        if self.match(TokenKind.NOT):
            operand = self.parse_not_expr()
            return UnaryExpr(op=UnaryOp.NOT, operand=operand)
        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        """addition (comp_op addition | 'in'/'not in' list | 'is' ['not'] 'null')?"""
        left = self.parse_addition()

        # "is" null / "is not" null
        if self.current.kind == TokenKind.IS:
            self.advance()
            negated = bool(self.match(TokenKind.NOT))
            self.expect(TokenKind.NULL)
            null_check = BinaryExpr(
                op=BinaryOp.NE if negated else BinaryOp.EQ,
                left=left,
                right=Literal(value=None),
            )
            return null_check

        # "in" / "not in"
        if self.current.kind == TokenKind.IN:
            self.advance()
            items = self._parse_list_items()
            return InExpr(value=left, items=items, negated=False)
        if self.current.kind == TokenKind.NOT and self.peek(1).kind == TokenKind.IN:
            self.advance()  # not
            self.advance()  # in
            items = self._parse_list_items()
            return InExpr(value=left, items=items, negated=True)

        # Comparison operators
        comp_ops: dict[TokenKind, BinaryOp] = {
            TokenKind.EQ: BinaryOp.EQ,
            TokenKind.NE: BinaryOp.NE,
            TokenKind.LT: BinaryOp.LT,
            TokenKind.GT: BinaryOp.GT,
            TokenKind.LE: BinaryOp.LE,
            TokenKind.GE: BinaryOp.GE,
        }
        if self.current.kind in comp_ops:
            op = comp_ops[self.current.kind]
            self.advance()
            right = self.parse_addition()
            return BinaryExpr(op=op, left=left, right=right)

        return left

    def parse_addition(self) -> Expr:
        """multiply (('+' | '-') multiply)*"""
        left = self.parse_multiply()
        while self.current.kind in (TokenKind.PLUS, TokenKind.MINUS):
            op = BinaryOp.ADD if self.current.kind == TokenKind.PLUS else BinaryOp.SUB
            self.advance()
            right = self.parse_multiply()
            left = BinaryExpr(op=op, left=left, right=right)
        return left

    def parse_multiply(self) -> Expr:
        """unary (('*' | '/' | '%') unary)*"""
        left = self.parse_unary()
        while self.current.kind in (TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT):
            if self.current.kind == TokenKind.STAR:
                op = BinaryOp.MUL
            elif self.current.kind == TokenKind.SLASH:
                op = BinaryOp.DIV
            else:
                op = BinaryOp.MOD
            self.advance()
            right = self.parse_unary()
            left = BinaryExpr(op=op, left=left, right=right)
        return left

    def parse_unary(self) -> Expr:
        """'-' unary | primary"""
        if self.match(TokenKind.MINUS):
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.NEG, operand=operand)
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        """literal | duration | func_call | field_ref | '(' expr ')' | list"""
        tok = self.current

        # Parenthesized expression
        if tok.kind == TokenKind.LPAREN:
            self.advance()
            expr = self.parse_expr()
            self.expect(TokenKind.RPAREN)
            return expr

        # List literal
        if tok.kind == TokenKind.LBRACKET:
            return self._parse_list_literal_as_first_item()

        # Literals
        if tok.kind == TokenKind.INT:
            self.advance()
            return Literal(value=int(tok.value))
        if tok.kind == TokenKind.FLOAT:
            self.advance()
            return Literal(value=float(tok.value))
        if tok.kind == TokenKind.STRING:
            self.advance()
            return Literal(value=tok.value)
        if tok.kind == TokenKind.TRUE:
            self.advance()
            return Literal(value=True)
        if tok.kind == TokenKind.FALSE:
            self.advance()
            return Literal(value=False)
        if tok.kind == TokenKind.NULL:
            self.advance()
            return Literal(value=None)

        # Duration literal
        if tok.kind == TokenKind.DURATION:
            self.advance()
            return _parse_duration(tok)

        # Identifier: could be function call or field reference
        if tok.kind == TokenKind.IDENT:
            # Look ahead for function call
            if self.peek(1).kind == TokenKind.LPAREN:
                return self._parse_func_call()
            return self._parse_field_ref()

        raise ExpressionParseError(
            f"Unexpected token: {tok.kind} ({tok.value!r})",
            tok.pos,
        )

    def _parse_func_call(self) -> FuncCall:
        """IDENT '(' (expr (',' expr)*)? ')'"""
        name_tok = self.expect(TokenKind.IDENT)
        self.expect(TokenKind.LPAREN)

        args: list[Expr] = []
        if self.current.kind != TokenKind.RPAREN:
            args.append(self.parse_expr())
            while self.match(TokenKind.COMMA):
                args.append(self.parse_expr())

        self.expect(TokenKind.RPAREN)
        return FuncCall(name=name_tok.value, args=args)

    def _parse_field_ref(self) -> FieldRef:
        """IDENT (('.' | '->') IDENT)*"""
        first = self.expect(TokenKind.IDENT)
        path = [first.value]

        while self.current.kind in (TokenKind.DOT, TokenKind.ARROW):
            self.advance()
            segment = self.expect(TokenKind.IDENT)
            path.append(segment.value)

        return FieldRef(path=path)

    def _parse_list_items(self) -> list[Expr]:
        """'[' (expr (',' expr)*)? ']'"""
        self.expect(TokenKind.LBRACKET)
        items: list[Expr] = []
        if self.current.kind != TokenKind.RBRACKET:
            items.append(self.parse_expr())
            while self.match(TokenKind.COMMA):
                items.append(self.parse_expr())
        self.expect(TokenKind.RBRACKET)
        return items

    def _parse_list_literal_as_first_item(self) -> Expr:
        """Parse [a, b, c] as a standalone list — returns first item for now.

        Lists as standalone expressions are used in 'in' operator context.
        As a primary expression, we parse but wrap as InExpr is handled at
        comparison level. For standalone list literals, we return a FuncCall
        to __list__ as a representation.
        """
        items = self._parse_list_items()
        # Wrap as a function call to a synthetic __list__ function
        return FuncCall(name="__list__", args=items)


def _parse_duration(tok: Token) -> DurationLiteral:
    """Parse a duration token like '7d', '9m', '24h'."""
    value_str = ""
    unit_str = ""
    for c in tok.value:
        if c.isdigit():
            value_str += c
        else:
            unit_str += c
    return DurationLiteral(value=int(value_str), unit=unit_str)


def parse_expr(source: str) -> Expr:
    """Parse an expression string into an AST.

    Args:
        source: Expression string (e.g., "box1 + box2 * 1.2")

    Returns:
        Parsed expression AST.

    Raises:
        ExpressionParseError: If the expression is invalid.
        ExpressionTokenError: If tokenization fails.
    """
    try:
        tokens = tokenize(source)
    except ExpressionTokenError as e:
        raise ExpressionParseError(str(e), e.pos) from e

    parser = _Parser(tokens)
    expr = parser.parse_expr()

    # Ensure all tokens consumed
    if parser.current.kind != TokenKind.EOF:
        raise ExpressionParseError(
            f"Unexpected token after expression: {parser.current.value!r}",
            parser.current.pos,
        )

    return expr
