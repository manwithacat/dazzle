"""Parser for aggregate where-clauses — emits ``ScopePredicate`` trees.

Used by ``_fetch_count_metric`` and ``_fetch_scalar_metric`` to translate
``count(StudentProfile where latest_grade >= target_grade and status = "open")``
into a structured predicate the existing predicate compiler can hand to
``QueryBuilder.__scope_predicate`` as parameterised SQL.

The grammar is intentionally minimal — Phase 1 of the reporting predicate
algebra unification (see ``dev_docs/2026-04-27-reporting-predicate-algebra.md``).
No function calls, no arithmetic, no ``IN (...)`` lists, no NULL semantics.
Add when a real consumer asks.

Grammar (informal)::

    expr      := or_expr
    or_expr   := and_expr ('or' and_expr)*
    and_expr  := not_expr ('and' not_expr)*
    not_expr  := 'not' atom | atom
    atom      := '(' expr ')' | comparison
    comparison:= IDENT op (IDENT | LITERAL)
    op        := '=' | '!=' | '>=' | '<=' | '>' | '<'
    LITERAL   := number | quoted_string | 'true' | 'false' | 'null'

When the RHS is a bare identifier AND it appears in ``known_columns`` for
the source entity, emit ``ColumnRefCheck`` (column-vs-column on the same
row). Otherwise emit ``ColumnCheck`` with a typed ``ValueRef.literal``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    ColumnRefCheck,
    CompOp,
    ScopePredicate,
    Tautology,
    ValueRef,
)

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TokenKind = Literal[
    "IDENT", "NUMBER", "STRING", "OP", "LPAREN", "RPAREN", "AND", "OR", "NOT", "EOF"
]


@dataclass(frozen=True)
class _Token:
    kind: _TokenKind
    value: str


_TOKEN_RE = re.compile(
    r"""
    \s+
    | (?P<lparen> \( )
    | (?P<rparen> \) )
    | (?P<op> >= | <= | != | = | > | < )
    | (?P<string> "(?:[^"\\]|\\.)*" | '(?:[^'\\]|\\.)*' )
    | (?P<number> -?\d+(?:\.\d+)? )
    | (?P<ident> [A-Za-z_][A-Za-z0-9_]* )
    """,
    re.VERBOSE,
)

_KEYWORDS = {"and": "AND", "or": "OR", "not": "NOT"}
_OPERATORS = {
    "=": CompOp.EQ,
    "!=": CompOp.NEQ,
    ">": CompOp.GT,
    "<": CompOp.LT,
    ">=": CompOp.GTE,
    "<=": CompOp.LTE,
}


def _tokenise(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ValueError(f"Unexpected character at position {pos}: {text[pos]!r}")
        if m.lastgroup is None:
            # Whitespace match — skip.
            pos = m.end()
            continue
        value = m.group(m.lastgroup)
        if m.lastgroup == "lparen":
            tokens.append(_Token("LPAREN", value))
        elif m.lastgroup == "rparen":
            tokens.append(_Token("RPAREN", value))
        elif m.lastgroup == "op":
            tokens.append(_Token("OP", value))
        elif m.lastgroup == "string":
            tokens.append(_Token("STRING", value))
        elif m.lastgroup == "number":
            tokens.append(_Token("NUMBER", value))
        elif m.lastgroup == "ident":
            kw = _KEYWORDS.get(value.lower())
            if kw is not None:
                tokens.append(_Token(kw, value.lower()))  # type: ignore[arg-type]
            else:
                tokens.append(_Token("IDENT", value))
        pos = m.end()
    tokens.append(_Token("EOF", ""))
    return tokens


# ---------------------------------------------------------------------------
# Parser (recursive descent)
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], known_columns: frozenset[str]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._known_columns = known_columns

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: _TokenKind) -> _Token:
        tok = self._advance()
        if tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok.kind} ({tok.value!r})")
        return tok

    def parse(self) -> ScopePredicate:
        result = self._parse_or()
        if self._peek().kind != "EOF":
            tok = self._peek()
            raise ValueError(f"Unexpected trailing token: {tok.kind} ({tok.value!r})")
        return result

    def _parse_or(self) -> ScopePredicate:
        left = self._parse_and()
        children = [left]
        while self._peek().kind == "OR":
            self._advance()
            children.append(self._parse_and())
        if len(children) == 1:
            return left
        return BoolComposite.make(BoolOp.OR, children)

    def _parse_and(self) -> ScopePredicate:
        left = self._parse_not()
        children = [left]
        while self._peek().kind == "AND":
            self._advance()
            children.append(self._parse_not())
        if len(children) == 1:
            return left
        return BoolComposite.make(BoolOp.AND, children)

    def _parse_not(self) -> ScopePredicate:
        if self._peek().kind == "NOT":
            self._advance()
            return BoolComposite.make(BoolOp.NOT, [self._parse_atom()])
        return self._parse_atom()

    def _parse_atom(self) -> ScopePredicate:
        if self._peek().kind == "LPAREN":
            self._advance()
            inner = self._parse_or()
            self._expect("RPAREN")
            return inner
        return self._parse_comparison()

    def _parse_comparison(self) -> ScopePredicate:
        # LHS is always an identifier (column on the source entity).
        lhs = self._expect("IDENT").value
        op_tok = self._expect("OP")
        op = _OPERATORS[op_tok.value]
        rhs = self._advance()
        # Column-vs-column: RHS is a known column on the source entity.
        if rhs.kind == "IDENT":
            if rhs.value in self._known_columns:
                return ColumnRefCheck(field=lhs, op=op, other_field=rhs.value)
            # Bare identifier that ISN'T a column — treat as a literal
            # ('true' / 'false' / 'null' fall through to here too).
            return ColumnCheck(field=lhs, op=op, value=_literal_value(rhs.value))
        if rhs.kind == "STRING":
            # Strip surrounding quotes; unescape \" / \'.
            quote = rhs.value[0]
            inner = rhs.value[1:-1].replace(f"\\{quote}", quote).replace("\\\\", "\\")
            return ColumnCheck(field=lhs, op=op, value=ValueRef(literal=inner))
        if rhs.kind == "NUMBER":
            return ColumnCheck(field=lhs, op=op, value=_numeric_value(rhs.value))
        raise ValueError(f"Expected literal or identifier on RHS, got {rhs.kind}")


def _numeric_value(text: str) -> ValueRef:
    """Parse a numeric literal, preferring int when possible."""
    try:
        return ValueRef(literal=int(text))
    except ValueError:
        return ValueRef(literal=float(text))


def _literal_value(name: str) -> ValueRef:
    """Resolve a bare identifier to true/false/null/string."""
    lname = name.lower()
    if lname == "true":
        return ValueRef(literal=True)
    if lname == "false":
        return ValueRef(literal=False)
    if lname == "null":
        return ValueRef(literal_null=True)
    # Unknown bare identifier — treat as a string literal so authors can
    # write `count(X where status = open)` without quotes (matches the
    # legacy `_parse_simple_where` behaviour).
    return ValueRef(literal=name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_aggregate_where(text: str, known_columns: Iterable[str] | None = None) -> ScopePredicate:
    """Parse an aggregate where-clause to a ``ScopePredicate`` tree.

    Args:
        text: The clause text (the ``...`` in
            ``count(X where ...)``). Empty / whitespace-only → ``Tautology``.
        known_columns: Field names known to exist on the source entity.
            Used to disambiguate column-vs-column comparisons from
            column-vs-literal. When ``None``, the parser treats every
            bare RHS identifier as a literal (legacy behaviour).

    Returns:
        A ``ScopePredicate`` ready for ``compile_predicate``.

    Raises:
        ValueError: When the input is malformed. Callers should log the
            error and proceed with no aggregate filter (matches the
            pre-existing ``_parse_simple_where`` failure mode of
            "produce zero rather than the wrong number").
    """
    if not text or not text.strip():
        return Tautology()
    cols = frozenset(known_columns) if known_columns is not None else frozenset()
    tokens = _tokenise(text)
    return _Parser(tokens, cols).parse()
